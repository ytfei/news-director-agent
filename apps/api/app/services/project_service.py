"""选题领域服务：可写作性判定 + 详情组装。

★ 与早期设计的差异（docs/06 §1 R4）：点评**不是**写作的前置条件。
- 有 passed 点评 → `opinion` 模式（观点驱动）
- 全无点评 → `digest` 模式（素材综述），仍可写作，但前端强提示
- 存在未处置的 blocker → 直接不可写作（合规红线）
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import FindingSeverity, FindingStatus, ProjectStatus
from app.models.material import Annotation
from app.models.project import Project, ProjectMaterial, PromptTemplate
from app.repositories.project_repo import ProjectRepository, PromptRepository
from app.repositories.review_repo import ReviewRepository
from app.services.material_service import material_brief, news_brief


def prompt_brief(p: PromptTemplate) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "category": p.category.value,
        "version_no": p.version_no,
        "description": p.description,
        "is_official": p.is_official,
    }


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.prompts = PromptRepository(session)
        self.reviews = ReviewRepository(session)

    async def materials_with_context(self, project_id: uuid.UUID) -> list[dict]:
        rows = await self.projects.materials_of(project_id)
        anns = [a for _, _, _, a in rows if a is not None]
        reports = await self.reviews.latest_reports([a.id for a in anns])
        open_findings = await self.reviews.open_findings([r.id for r in reports.values()])
        blockers: set[uuid.UUID] = {
            f.report_id
            for f in open_findings
            if f.severity == FindingSeverity.blocker and f.status == FindingStatus.open
        }
        open_count: dict[uuid.UUID, int] = {}
        for f in open_findings:
            open_count[f.report_id] = open_count.get(f.report_id, 0) + 1

        out: list[dict] = []
        for link, material, news, ann in rows:
            report = reports.get(ann.id) if ann is not None else None
            item = material_brief(
                material, None, news, ann, report, open_count.get(report.id, 0) if report else 0
            )
            item["role"] = link.role.value
            item["sort"] = link.sort
            item["has_blocker"] = bool(report and report.id in blockers)
            out.append(item)
        return out

    async def assess(self, project_id: uuid.UUID) -> dict:
        """可写作性判定。前端据此决定按钮状态与提示文案。"""
        materials = await self.materials_with_context(project_id)
        total = len(materials)
        with_ann = sum(1 for m in materials if m["annotation"])
        blockers = [m for m in materials if m["has_blocker"]]

        reasons: list[str] = []
        if total == 0:
            reasons.append("还没有素材：先去素材库挑一组")
        if blockers:
            reasons.append(f"{len(blockers)} 条素材的点评命中合规红线，需先处理")

        writable = total > 0 and not blockers
        mode = "opinion" if with_ann else "digest"
        return {
            "writable": writable,
            "mode": mode,
            "blocking_reasons": reasons,
            "stats": {
                "materials": total,
                "with_annotation": with_ann,
                "without_annotation": total - with_ann,
                "with_blocker": len(blockers),
            },
        }

    async def detail(self, project: Project) -> dict:
        materials = await self.materials_with_context(project.id)
        prompts = await self.prompts.by_ids([uuid.UUID(str(x)) for x in (project.prompt_ids or [])])
        return {
            "id": project.id,
            "title": project.title,
            "status": project.status.value,
            "platform": project.platform,
            "target_words": project.target_words,
            "require_note": project.require_note,
            "prompt_ids": [str(x) for x in (project.prompt_ids or [])],
            "prompts": [prompt_brief(p) for p in prompts],
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "materials": materials,
            "assessment": await self.assess(project.id),
        }

    async def bulk_assess(self, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
        """列表页专用：4 条批量查询算出每个选题的统计，避免 N+1。"""
        if not project_ids:
            return {}
        links = (
            await self.session.execute(
                select(ProjectMaterial.project_id, ProjectMaterial.material_id).where(
                    ProjectMaterial.project_id.in_(project_ids)
                )
            )
        ).all()
        mat_ids = [mid for _, mid in links]
        ann_rows = (
            await self.session.execute(
                select(Annotation.id, Annotation.material_id).where(
                    Annotation.material_id.in_(mat_ids), Annotation.deleted_at.is_(None)
                )
            )
        ).all() if mat_ids else []
        ann_by_material = {mid: aid for aid, mid in ann_rows}
        reports = await self.reviews.latest_reports(list(ann_by_material.values()))
        open_findings = await self.reviews.open_findings([r.id for r in reports.values()])
        blocker_reports = {
            f.report_id
            for f in open_findings
            if f.severity == FindingSeverity.blocker and f.status == FindingStatus.open
        }

        out: dict[uuid.UUID, dict] = {pid: {"materials": 0, "with_annotation": 0,
                                            "with_blocker": 0} for pid in project_ids}
        for pid, mid in links:
            out[pid]["materials"] += 1
            aid = ann_by_material.get(mid)
            if aid:
                out[pid]["with_annotation"] += 1
                report = reports.get(aid)
                if report and report.id in blocker_reports:
                    out[pid]["with_blocker"] += 1
        for stat in out.values():
            stat["writable"] = stat["materials"] > 0 and stat["with_blocker"] == 0
            stat["mode"] = "opinion" if stat["with_annotation"] else "digest"
        return out

    async def sync_status(self, project: Project) -> ProjectStatus:
        """素材/点评变化后回写选题状态（collecting ↔ ready）。"""
        if project.status in {ProjectStatus.composing, ProjectStatus.drafting,
                              ProjectStatus.completed, ProjectStatus.archived,
                              ProjectStatus.cancelled}:
            return project.status
        assess = await self.assess(project.id)
        if assess["writable"] and assess["stats"]["with_annotation"]:
            project.status = ProjectStatus.ready
        elif assess["stats"]["with_blocker"]:
            project.status = ProjectStatus.reviewing
        else:
            project.status = ProjectStatus.collecting
        await self.session.flush()
        await self.session.refresh(project)
        return project.status


__all__ = ["ProjectService", "prompt_brief", "news_brief"]
