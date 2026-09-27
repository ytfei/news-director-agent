"""批注 API。

路径按「素材」组织（`/materials/{id}/annotation`），因为点评在用户心智里
就是素材的附属物（docs/06 §2）；检查入口按批（`/annotations/check`）。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, ensure_user, get_session
from app.models.enums import FindingStatus, ReportVerdict
from app.models.material import Annotation, Material
from app.repositories.annotation_repo import AnnotationRepository
from app.repositories.material_repo import MaterialRepository
from app.repositories.review_repo import ReviewRepository
from app.services.material_service import annotation_brief
from app.services.review_service import run_review

router = APIRouter(tags=["annotations"])


class AnnotationIn(BaseModel):
    body: str = ""
    source: str = "manual"


class CheckIn(BaseModel):
    material_ids: list[uuid.UUID] = Field(default_factory=list)
    # ★ 同步入口默认 rules（毫秒级）。模型版单条 48~108 秒，
    #   需要深度检查请走异步接口 POST /reviews/runs（返回 202 + run_id 轮询）。
    mode: str | None = None


@router.get("/materials/{material_id}/annotation")
async def get_annotation(
    material_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    material = await MaterialRepository(session).get(material_id, user_id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    ann = await AnnotationRepository(session).get_by_material(material.id)
    if ann is None:
        return {"material_id": material.id, "annotation": None, "findings": []}
    reviews = ReviewRepository(session)
    report = await reviews.latest_report_of(ann.id)
    findings = await reviews.findings_of(report.id) if report else []
    return {
        "material_id": material.id,
        "annotation": annotation_brief(ann, report, sum(
            1 for f in findings if f.status == FindingStatus.open
        )),
        "findings": [finding_out(f) for f in findings],
    }


@router.put("/materials/{material_id}/annotation")
async def put_annotation(
    material_id: uuid.UUID,
    payload: AnnotationIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """upsert 点评。正文变化会生成新版本，并把状态退回 draft（此前结论失效）。"""
    await ensure_user(session, user_id)
    material = await MaterialRepository(session).get(material_id, user_id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")

    repo = AnnotationRepository(session)
    ann, version_created = await repo.upsert(user_id, material, payload.body)
    await session.commit()
    return {
        "annotation": annotation_brief(ann),
        "version_created": version_created,
        "version_no": ann.current_version_no,
    }


@router.get("/annotations/{annotation_id}/versions")
async def list_versions(
    annotation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[dict]:
    if await AnnotationRepository(session).get(annotation_id, user_id) is None:
        raise HTTPException(status_code=404, detail="annotation not found")
    rows = await AnnotationRepository(session).versions(annotation_id)
    return [
        {
            "id": v.id,
            "version_no": v.version_no,
            "body": v.body,
            "source": v.source.value,
            "created_at": v.created_at,
        }
        for v in rows
    ]


@router.post("/annotations/check")
async def check_annotations(
    payload: CheckIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """提交检查（同步）。

    ★ 默认 rules（毫秒级即时反馈）；模型深度检查请走 `POST /reviews/runs`（异步）。
    这不是偷懒 —— 实测核查类任务单条 48~108 秒，同步等在请求里用户会以为服务挂了。
    """
    await ensure_user(session, user_id)
    if not payload.material_ids:
        raise HTTPException(status_code=422, detail="material_ids is required")

    rows = (
        await session.execute(
            select(Material, Annotation)
            .join(Annotation, Annotation.material_id == Material.id)
            .where(
                Material.id.in_(payload.material_ids),
                Material.user_id == user_id,
                Material.deleted_at.is_(None),
                Annotation.deleted_at.is_(None),
            )
        )
    ).all()
    if not rows:
        raise HTTPException(
            status_code=422, detail="这些素材还没有点评，先在资讯中心或工作台写一条"
        )

    result = await run_review(
        session,
        user_id,
        [(m, a) for m, a in rows],
        # 同步路径默认规则版，保证毫秒级返回
        mode=payload.mode or "rules",
    )
    reports = result["reports"]
    return {
        "run_id": result["run_id"],
        "skipped_material_ids": result["skipped_material_ids"],
        "verdict_summary": {
            v.value: sum(1 for r in reports if r.verdict == v) for v in ReportVerdict
        },
        "reports": [
            {
                "id": r.id,
                "annotation_id": r.annotation_id,
                "verdict": r.verdict.value,
                "summary": r.summary,
                "findings_count": r.findings_count,
            }
            for r in reports
        ],
    }


def finding_out(f) -> dict:
    return {
        "id": f.id,
        "report_id": f.report_id,
        "track": f.track.value,
        "severity": f.severity.value,
        "status": f.status.value,
        "span_start": f.span_start,
        "span_end": f.span_end,
        "quote": f.quote,
        "message": f.message,
        "suggestion": f.suggestion,
        "evidence": f.evidence or [],
        "reason": f.reason,
    }


__all__ = ["router", "finding_out"]
