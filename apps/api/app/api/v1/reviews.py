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
from app.models.enums import AnnotationVersionSource, FindingStatus
from app.models.material import Annotation, Material
from app.models.news import NewsItem
from app.models.review import ReviewReport
from app.repositories.annotation_repo import AnnotationRepository
from app.repositories.review_repo import ReviewRepository

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ResolveIn(BaseModel):
    action: FindingStatus
    reason: str | None = None


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
