"""素材领域服务：标记 / 编辑 / 列表 / 统计。

对外统一输出「素材 + 资讯摘要 + 批注摘要」的复合结构，
让前端在资讯中心一屏内就能渲染徽标，不必二次请求（docs/06 §4.1）。
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material import Annotation, Material
from app.models.news import NewsItem
from app.repositories.annotation_repo import AnnotationRepository
from app.repositories.material_repo import MaterialRepository, TopicRepository
from app.repositories.review_repo import ReviewRepository


def news_brief(n: NewsItem) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "summary": n.summary,
        "source_name": n.source_name,
        "url": n.url,
        "content_type": n.content_type.value,
        "published_at": n.published_at,
        "importance": float(n.importance) if n.importance is not None else None,
        "industries": n.industries or [],
        "market_scope": n.market_scope or [],
        "source_count": len(n.source_refs or []) or 1,
        "cluster_id": n.cluster_id,
    }


def annotation_brief(
    a: Annotation | None, report=None, open_findings: int = 0
) -> dict | None:
    if a is None:
        return None
    return {
        "id": a.id,
        "status": a.status.value,
        # verdict 来自最近一次报告；没有报告时按 status 兜底
        "verdict": report.verdict.value if report else None,
        "body": a.body,
        "version_no": a.current_version_no,
        "open_findings": open_findings,
        "last_report_id": report.id if report else None,
        "last_checked_at": a.last_checked_at,
        "updated_at": a.updated_at,
    }


def material_brief(
    m: Material, topics: list[str] | None = None, news: NewsItem | None = None,
    annotation: Annotation | None = None, report=None, open_findings: int = 0,
) -> dict:
    return {
        "id": m.id,
        "news_id": m.news_item_id,
        "material_date": m.material_date,
        "score": m.score,
        "status": m.status.value,
        "note": m.note,
        "topics": topics or [],
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "news": news_brief(news) if news else None,
        "annotation": annotation_brief(annotation, report, open_findings),
    }


class MaterialService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.materials = MaterialRepository(session)
        self.topics = TopicRepository(session)
        self.annotations = AnnotationRepository(session)
        self.reviews = ReviewRepository(session)

    # ---------------- 写 ----------------

    async def mark(
        self,
        user_id: uuid.UUID,
        news_item_id: uuid.UUID,
        *,
        score: int,
        topic_names: list[str],
        material_date: date | None,
        note: str | None,
    ) -> dict:
        material, created = await self.materials.upsert(
            user_id,
            news_item_id,
            score=score,
            material_date=material_date,
            note=note,
        )
        if topic_names:
            topics = await self.topics.ensure(user_id, topic_names)
            await self.materials.set_topics(material.id, [t.id for t in topics])
        news = await self.session.get(NewsItem, news_item_id)
        topic_map = await self.materials.topics_of([material.id])
        return {
            "created": created,
            "material": material_brief(material, topic_map.get(material.id), news),
        }

    async def update(
        self,
        user_id: uuid.UUID,
        material_id: uuid.UUID,
        *,
        score: int | None,
        topic_names: list[str] | None,
        material_date: date | None,
        note: str | None,
    ) -> dict | None:
        material = await self.materials.get(material_id, user_id)
        if material is None:
            return None
        if score is not None:
            material.score = score
        if material_date is not None:
            material.material_date = material_date
        if note is not None:
            material.note = note
        await self.session.flush()
        await self.session.refresh(material)  # updated_at 在 SQL 侧生成，读前回读
        if topic_names is not None:
            topics = await self.topics.ensure(user_id, topic_names) if topic_names else []
            await self.materials.set_topics(material.id, [t.id for t in topics])
        news = await self.session.get(NewsItem, material.news_item_id)
        topic_map = await self.materials.topics_of([material.id])
        return material_brief(material, topic_map.get(material.id), news)

    async def remove(self, user_id: uuid.UUID, material_id: uuid.UUID) -> bool:
        material = await self.materials.get(material_id, user_id)
        if material is None:
            return False
        await self.materials.soft_delete(material)
        return True

    # ---------------- 读 ----------------

    async def list_items(
        self,
        user_id: uuid.UUID,
        *,
        material_date: date | None = None,
        min_score: int | None = None,
        max_score: int | None = None,
        topic_names: list[str] | None = None,
        has_annotation: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        hydrate_annotation_body: bool = False,
    ) -> list[dict]:
        stmt = self.materials.list_query(
            user_id,
            material_date=material_date,
            min_score=min_score,
            max_score=max_score,
            topics=topic_names,
            has_annotation=has_annotation,
        )
        rows = (await self.session.execute(stmt.limit(limit).offset(offset))).all()
        material_ids = [m.id for m, _, _ in rows]
        topic_map = await self.materials.topics_of(material_ids)

        annotations = [a for _, _, a in rows if a is not None]
        reports = await self.reviews.latest_reports([a.id for a in annotations])
        open_findings = await self.reviews.open_findings([r.id for r in reports.values()])
        open_count: dict[uuid.UUID, int] = {}
        for f in open_findings:
            open_count[f.report_id] = open_count.get(f.report_id, 0) + 1

        out: list[dict] = []
        for material, news, ann in rows:
            report = reports.get(ann.id) if ann is not None else None
            item = material_brief(
                material,
                topic_map.get(material.id),
                news,
                ann,
                report,
                open_count.get(report.id, 0) if report else 0,
            )
            if not hydrate_annotation_body and item["annotation"] is not None:
                body = item["annotation"]["body"]
                item["annotation"]["excerpt"] = body[:120]
                item["annotation"]["body"] = body
            out.append(item)
        return out

    async def detail(self, user_id: uuid.UUID, material_id: uuid.UUID) -> dict | None:
        material = await self.materials.get(material_id, user_id)
        if material is None:
            return None
        news = await self.session.get(NewsItem, material.news_item_id)
        ann = await self.annotations.get_by_material(material.id)
        report = await self.reviews.latest_report_of(ann.id) if ann else None
        topic_map = await self.materials.topics_of([material.id])
        return material_brief(material, topic_map.get(material.id), news, ann, report)

    async def stats(self, user_id: uuid.UUID, day: date) -> dict:
        items = await self.list_items(user_id, material_date=day, limit=500)
        total = len(items)
        with_ann = sum(1 for i in items if i["annotation"])
        avg = round(sum(i["score"] for i in items) / total, 1) if total else 0.0
        by_topic: dict[str, int] = {}
        for i in items:
            for t in i["topics"]:
                by_topic[t] = by_topic.get(t, 0) + 1
        buckets = {
            "ge8": sum(1 for i in items if i["score"] >= 8),
            "6_7": sum(1 for i in items if 6 <= i["score"] <= 7),
            "le5": sum(1 for i in items if i["score"] <= 5),
        }
        return {
            "date": day,
            "total": total,
            "with_annotation": with_ann,
            "without_annotation": total - with_ann,
            "avg_score": avg,
            "by_topic": by_topic,
            "score_buckets": buckets,
            "dates": await self.materials.dates(user_id),
        }


async def decorate_news(
    session: AsyncSession, user_id: uuid.UUID, news_items: list[NewsItem]
) -> dict[uuid.UUID, dict]:
    """给资讯列表挂上「是否素材 / 是否已批注」的徽标数据（docs/06 §4.6）。

    一次批量查询，避免前端逐条再请求。
    """
    from sqlalchemy import select

    from app.models.material import Material

    ids = [n.id for n in news_items]
    out: dict[uuid.UUID, dict] = {i: {"material": None, "annotation": None} for i in ids}
    if not ids:
        return out

    materials = (
        await session.execute(
            select(Material).where(
                Material.user_id == user_id,
                Material.news_item_id.in_(ids),
                Material.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    if not materials:
        return out

    material_ids = [m.id for m in materials]
    topics = await MaterialRepository(session).topics_of(material_ids)
    anns = await AnnotationRepository(session).list_by_materials(material_ids)
    reports = await ReviewRepository(session).latest_reports([a.id for a in anns.values()])
    findings = await ReviewRepository(session).open_findings([r.id for r in reports.values()])
    open_count: dict[uuid.UUID, int] = {}
    for f in findings:
        open_count[f.report_id] = open_count.get(f.report_id, 0) + 1

    for m in materials:
        ann = anns.get(m.id)
        report = reports.get(ann.id) if ann else None
        out[m.news_item_id] = {
            "material": {
                "id": m.id,
                "score": m.score,
                "topics": topics.get(m.id, []),
                "material_date": m.material_date,
            },
            "annotation": annotation_brief(
                ann, report, open_count.get(report.id, 0) if report else 0
            ),
        }
    return out


__all__ = [
    "MaterialService",
    "material_brief",
    "news_brief",
    "annotation_brief",
    "decorate_news",
]
