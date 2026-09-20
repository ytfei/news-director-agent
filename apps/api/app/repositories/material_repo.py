"""素材与主题仓储。

素材是 M2 的中枢对象（docs/06 §2）：`materials` 承载三维编辑态，
`material_topics` 承载多值标签，读取时统一聚合，避免前端 N+1。
"""

from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material import Annotation, Material, MaterialTopic, Topic
from app.models.news import NewsItem

_SLUG_CLEAN = re.compile(r"\s+")


def slugify(name: str) -> str:
    """中文标签直接用去除空白后的原文作 slug（PG 唯一索引按字节比较，够用）。"""
    return _SLUG_CLEAN.sub("", name.strip()).lower()[:64]


class TopicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[Topic]:
        stmt = (
            select(Topic)
            .where(
                Topic.deleted_at.is_(None),
                (Topic.user_id == user_id) | (Topic.user_id.is_(None)),
            )
            .order_by(Topic.is_system.desc(), Topic.name.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def ensure(self, user_id: uuid.UUID, names: list[str]) -> list[Topic]:
        """按名称 upsert 主题：先找系统预设，再找用户自建，都没有才新建。"""
        out: list[Topic] = []
        for raw in names:
            name = (raw or "").strip()
            if not name:
                continue
            slug = slugify(name)
            found = (
                await self.session.execute(
                    select(Topic).where(
                        Topic.slug == slug,
                        Topic.deleted_at.is_(None),
                        (Topic.user_id == user_id) | (Topic.user_id.is_(None)),
                    )
                )
            ).scalars().first()
            if found is None:
                found = Topic(user_id=user_id, slug=slug, name=name, is_system=False)
                self.session.add(found)
                await self.session.flush()
            out.append(found)
        return out


class MaterialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------- 读 ----------------

    async def get(self, material_id: uuid.UUID, user_id: uuid.UUID) -> Material | None:
        return (
            await self.session.execute(
                select(Material).where(
                    Material.id == material_id,
                    Material.user_id == user_id,
                    Material.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def get_by_news(self, user_id: uuid.UUID, news_item_id: uuid.UUID) -> Material | None:
        return (
            await self.session.execute(
                select(Material).where(
                    Material.user_id == user_id,
                    Material.news_item_id == news_item_id,
                    Material.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    def list_query(
        self,
        user_id: uuid.UUID,
        *,
        material_date: date | None = None,
        min_score: int | None = None,
        max_score: int | None = None,
        topics: list[str] | None = None,
        has_annotation: bool | None = None,
    ) -> Select:
        """返回 (Material, NewsItem, Annotation) 三元组。

        ★ 工作台与选题都走这一个查询：按 日期 / 评分 / 主题 / 有无点评 四维筛选。
        """
        stmt = (
            select(Material, NewsItem, Annotation)
            .join(NewsItem, NewsItem.id == Material.news_item_id)
            .outerjoin(
                Annotation,
                and_(
                    Annotation.material_id == Material.id,
                    Annotation.deleted_at.is_(None),
                ),
            )
            .where(Material.user_id == user_id, Material.deleted_at.is_(None))
        )
        if material_date:
            stmt = stmt.where(Material.material_date == material_date)
        if min_score is not None:
            stmt = stmt.where(Material.score >= min_score)
        if max_score is not None:
            stmt = stmt.where(Material.score <= max_score)
        if has_annotation is True:
            stmt = stmt.where(Annotation.id.is_not(None))
        elif has_annotation is False:
            stmt = stmt.where(Annotation.id.is_(None))
        if topics:
            sub = (
                select(MaterialTopic.material_id)
                .join(Topic, Topic.id == MaterialTopic.topic_id)
                .where((Topic.name.in_(topics)) | (Topic.slug.in_(topics)))
            )
            stmt = stmt.where(Material.id.in_(sub))
        return stmt.order_by(
            Material.material_date.desc(), Material.score.desc(), Material.created_at.desc()
        )

    async def topics_of(self, material_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not material_ids:
            return {}
        rows = (
            await self.session.execute(
                select(MaterialTopic.material_id, Topic.name)
                .join(Topic, Topic.id == MaterialTopic.topic_id)
                .where(MaterialTopic.material_id.in_(material_ids))
                .order_by(Topic.name.asc())
            )
        ).all()
        out: dict[uuid.UUID, list[str]] = {}
        for mid, name in rows:
            out.setdefault(mid, []).append(name)
        return out

    async def dates(self, user_id: uuid.UUID, limit: int = 30) -> list[date]:
        rows = (
            await self.session.execute(
                select(Material.material_date)
                .where(Material.user_id == user_id, Material.deleted_at.is_(None))
                .group_by(Material.material_date)
                .order_by(Material.material_date.desc())
                .limit(limit)
            )
        ).scalars().all()
        return list(rows)

    # ---------------- 写 ----------------

    async def upsert(
        self,
        user_id: uuid.UUID,
        news_item_id: uuid.UUID,
        *,
        score: int,
        material_date: date | None,
        note: str | None,
    ) -> tuple[Material, bool]:
        existing = await self.get_by_news(user_id, news_item_id)
        if existing is not None:
            existing.score = score
            if material_date:
                existing.material_date = material_date
            existing.note = note
            await self.session.flush()
            # updated_at 走的是 onupdate=func.now()（SQL 侧生成）→ 需要回读
            await self.session.refresh(existing)
            return existing, False

        from datetime import date as _date

        row = Material(
            user_id=user_id,
            news_item_id=news_item_id,
            score=score,
            note=note,
            # 显式给值，避免依赖 server_default 后再去读它（异步下会触发隐式 IO）
            material_date=material_date or _date.today(),
        )
        self.session.add(row)
        await self.session.flush()
        # created_at / updated_at / status 由服务端默认值产生，读之前必须回读一次
        await self.session.refresh(row)
        return row, True

    async def set_topics(self, material_id: uuid.UUID, topic_ids: list[uuid.UUID]) -> None:
        """整体替换（先删后插），保证多选面板的语义一致。"""
        from sqlalchemy import delete

        await self.session.execute(
            delete(MaterialTopic).where(MaterialTopic.material_id == material_id)
        )
        for tid in dict.fromkeys(topic_ids):
            self.session.add(MaterialTopic(material_id=material_id, topic_id=tid))
        await self.session.flush()

    async def soft_delete(self, material: Material) -> None:
        from datetime import datetime

        material.deleted_at = datetime.now()
        await self.session.flush()

    async def count_by_date(self, user_id: uuid.UUID, material_date: date) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Material)
                    .where(
                        Material.user_id == user_id,
                        Material.material_date == material_date,
                        Material.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
        )


__all__ = ["MaterialRepository", "TopicRepository", "slugify"]
