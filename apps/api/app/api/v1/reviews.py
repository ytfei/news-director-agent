"""体检报告 API：读取报告 + 处置 finding。

处置语义（docs/03 §3 步骤⑦）：
- accepted：用 suggestion 替换原文 → 生成新的 annotation_version（source=ai_adopt），需要复检
- dismissed：必填理由，记入历史用于降低误报，同一问题不再重复报
- ignored：不改正文，仅关闭
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, get_session
from app.api.v1.annotations import finding_out
from app.core.config import settings
from app.models.agent import AgentRun
from app.models.enums import AnnotationVersionSource, FindingStatus, RunGraph, RunStatus
from app.models.material import Annotation, Material
from app.models.news import NewsItem
from app.models.review import ReviewReport
from app.repositories.annotation_repo import AnnotationRepository
from app.repositories.review_repo import ReviewRepository
from app.services.queue import enqueue_job

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ResolveIn(BaseModel):
    action: FindingStatus
    reason: str | None = None


class ReviewRunIn(BaseModel):
    material_ids: list[uuid.UUID]
    mode: str | None = None  # rules / llm / hybrid；空 = 用配置默认值


@router.post("/runs", status_code=202)
async def create_review_run(
    payload: ReviewRunIn,
    sync: bool = False,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """★ 异步三轨检查入口：入队后立刻返回 run_id 供轮询。

    为什么必须异步：核查类任务实测单条 48~108 秒（turbo 3613 tokens / 56s），
    同步等在请求里用户会以为服务挂了。

    降级：Redis 不可用（job_id=None）或显式 `?sync=true` 时就地执行，
    保证开发机不启 worker 也能跑通链路。
    """
    if not payload.material_ids:
        raise HTTPException(status_code=422, detail="material_ids 不能为空")

    ids = payload.material_ids[: settings.REVIEW_MAX_ITEMS_PER_RUN]
    owned = list(
        (
            await session.execute(
                select(Material.id).where(
                    Material.id.in_(ids),
                    Material.user_id == user_id,
                    Material.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    )
    if not owned:
        raise HTTPException(status_code=404, detail="没有可检查的素材")

    mode = payload.mode or settings.REVIEW_MODE
    run = AgentRun(
        user_id=user_id,
        graph=RunGraph.review,
        status=RunStatus.queued,
        thread_id=str(uuid.uuid4()),
        input={"material_ids": [str(i) for i in owned], "mode": mode},
        model=mode,
    )
    session.add(run)
    await session.commit()

    job_id = await enqueue_job(
        "review_annotations",
        str(user_id),
        [str(i) for i in owned],
        mode,
        str(run.id),
    )

    if job_id is None or sync:
        from app.services.review_service import review_materials

        result = await review_materials(user_id, owned, mode=mode, run_id=run.id)
        return {**result, "status": RunStatus.succeeded.value, "async": False}

    return {
        "run_id": str(run.id),
        "job_id": job_id,
        "status": RunStatus.queued.value,
        "async": True,
        "material_count": len(owned),
        "mode": mode,
    }


@router.get("/runs/{run_id}")
async def get_review_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """轮询检查进度。前端拿 POST /runs 返回的 run_id 定时查这里。"""
    run = await session.get(AgentRun, run_id)
    if run is None or run.user_id != user_id:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "mode": (run.input or {}).get("mode"),
        "model": run.model,
        "token_input": run.token_input,
        "token_output": run.token_output,
        "output": run.output,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


@router.get("")
async def list_reports(
    annotation_id: uuid.UUID | None = None,
    material_id: uuid.UUID | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[dict]:
    """按点评或素材查报告（工作台/体检页的入口）。"""
    if annotation_id is None and material_id is None:
        raise HTTPException(status_code=422, detail="annotation_id or material_id is required")
    if annotation_id is None:
        material = (
            await session.execute(
                select(Material).where(
                    Material.id == material_id,
                    Material.user_id == user_id,
                    Material.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if material is None:
            raise HTTPException(status_code=404, detail="material not found")
        ann = await AnnotationRepository(session).get_by_material(material.id)
        if ann is None:
            return []
        annotation_id = ann.id

    stmt = (
        select(ReviewReport)
        .where(ReviewReport.annotation_id == annotation_id, ReviewReport.user_id == user_id)
        .order_by(ReviewReport.created_at.desc())
        .limit(limit)
    )
    reports = list((await session.execute(stmt)).scalars().all())
    return [await _report_out(session, r) for r in reports]


@router.get("/{report_id}")
async def get_report(
    report_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    got = await ReviewRepository(session).get_report(report_id, user_id)
    if got is None:
        raise HTTPException(status_code=404, detail="report not found")
    report, findings = got
    return await _report_out(session, report, findings)


@router.post("/findings/{finding_id}/resolve")
async def resolve_finding(
    finding_id: uuid.UUID,
    payload: ResolveIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    if payload.action == FindingStatus.open:
        raise HTTPException(status_code=422, detail="action must be accepted/dismissed/ignored")
    if payload.action == FindingStatus.dismissed and not (payload.reason or "").strip():
        raise HTTPException(status_code=422, detail="驳回必须填写理由")

    repo = ReviewRepository(session)
    finding = await repo.get_finding(finding_id, user_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")

    needs_recheck = False
    if payload.action == FindingStatus.accepted and finding.suggestion and finding.quote:
        # 采纳：替换正文并生成新版本（保持可回溯）
        report_row = await session.get(ReviewReport, finding.report_id)
        ann = await session.get(Annotation, report_row.annotation_id) if report_row else None
        material = await session.get(Material, ann.material_id) if ann else None
        if ann is not None and material is not None and finding.quote in ann.body:
            new_body = ann.body.replace(finding.quote, finding.suggestion)
            await AnnotationRepository(session).upsert(
                user_id,
                material,
                new_body,
                source=AnnotationVersionSource.ai_adopt,
            )
            needs_recheck = True

    await repo.resolve_finding(finding, payload.action, payload.reason)
    report = await session.get(ReviewReport, finding.report_id)
    await repo.refresh_verdict(report)
    await session.commit()

    return {
        "finding": finding_out(finding),
        "report_verdict": report.verdict.value,
        "needs_recheck": needs_recheck,
    }


async def _report_out(session: AsyncSession, report: ReviewReport, findings=None) -> dict:
    repo = ReviewRepository(session)
    findings = findings if findings is not None else await repo.findings_of(report.id)
    ann = await session.get(Annotation, report.annotation_id)
    material = await session.get(Material, ann.material_id) if ann else None
    news = await session.get(NewsItem, material.news_item_id) if material else None
    return {
        "id": report.id,
        "annotation_id": report.annotation_id,
        "annotation_version_no": report.annotation_version_no,
        "verdict": report.verdict.value,
        "summary": report.summary,
        "findings_count": report.findings_count,
        "created_at": report.created_at,
        "annotation": {
            "id": ann.id,
            "body": ann.body,
            "status": ann.status.value,
            "version_no": ann.current_version_no,
        } if ann else None,
        "material": {
            "id": material.id,
            "score": material.score,
            "material_date": material.material_date,
        } if material else None,
        "news": {
            "id": news.id,
            "title": news.title,
            "source_name": news.source_name,
        } if news else None,
        "findings": [finding_out(f) for f in findings],
    }


__all__ = ["router"]
