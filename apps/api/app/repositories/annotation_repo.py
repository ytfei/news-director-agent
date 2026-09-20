"""点评与版本仓储。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AnnotationStatus, AnnotationVersionSource
from app.models.material import Annotation, AnnotationVersion, Material


class AnnotationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_material(self, material_id: uuid.UUID) -> Annotation | None:
        return (
            await self.session.execute(
                select(Annotation).where(
                    Annotation.material_id == material_id,
                    Annotation.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def get(self, annotation_id: uuid.UUID, user_id: uuid.UUID) -> Annotation | None:
        return (
            await self.session.execute(
                select(Annotation).where(
                    Annotation.id == annotation_id,
                    Annotation.user_id == user_id,
                    Annotation.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def upsert(
        self,
        user_id: uuid.UUID,
        material: Material,
        body: str,
        *,
        source: AnnotationVersionSource = AnnotationVersionSource.manual,
    ) -> tuple[Annotation, bool]:
        """写入点评正文；正文发生变化时生成新版本。

        返回 (annotation, version_created)。
        """
        ann = await self.get_by_material(material.id)
        changed = ann is None or ann.body != body
        if ann is None:
            ann = Annotation(
                user_id=user_id,
                material_id=material.id,
                news_item_id=material.news_item_id,
                status=AnnotationStatus.draft,
                body=body,
                current_version_no=0,
            )
            self.session.add(ann)
            await self.session.flush()
            # created_at / updated_at 来自服务端默认值 → 回读后再返回给上层
            await self.session.refresh(ann)
        elif changed:
            ann.body = body
            # 正文被改动 → 之前通过的检查结论失效，回到 draft（可复检）
            if ann.status in {AnnotationStatus.passed, AnnotationStatus.needs_revision,
                              AnnotationStatus.blocked}:
                ann.status = AnnotationStatus.draft
        if changed:
            ann.current_version_no += 1
            self.session.add(
                AnnotationVersion(
                    annotation_id=ann.id,
                    version_no=ann.current_version_no,
                    body=body,
                    source=source,
                )
            )
            await self.session.flush()
            await self.session.refresh(ann)
        return ann, changed

    async def set_status(
        self, ann: Annotation, status: AnnotationStatus, *, checked_at: datetime | None = None
    ) -> None:
        ann.status = status
        if checked_at is not None:
            ann.last_checked_at = checked_at
        await self.session.flush()

    async def versions(self, annotation_id: uuid.UUID, limit: int = 50) -> list[AnnotationVersion]:
        stmt = (
            select(AnnotationVersion)
            .where(AnnotationVersion.annotation_id == annotation_id)
            .order_by(AnnotationVersion.version_no.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_by_materials(
        self, material_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Annotation]:
        if not material_ids:
            return {}
        rows = (
            await self.session.execute(
                select(Annotation).where(
                    Annotation.material_id.in_(material_ids),
                    Annotation.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        return {a.material_id: a for a in rows}


__all__ = ["AnnotationRepository"]
