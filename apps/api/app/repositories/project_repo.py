"""选题 / 提示词仓储。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProjectStatus
from app.models.material import Annotation, Material
from app.models.news import NewsItem
from app.models.project import Project, ProjectMaterial, PromptTemplate


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, project_id: uuid.UUID, user_id: uuid.UUID) -> Project | None:
        return (
            await self.session.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.user_id == user_id,
                    Project.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID, limit: int = 100) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.user_id == user_id, Project.deleted_at.is_(None))
            .order_by(Project.updated_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        title: str,
        platform: str | None,
        target_words: int | None,
        require_note: str | None,
        prompt_ids: list,
        material_ids: list[uuid.UUID],
    ) -> Project:
        project = Project(
            user_id=user_id,
            title=title,
            platform=platform,
            target_words=target_words,
            require_note=require_note,
            prompt_ids=prompt_ids,
            status=ProjectStatus.collecting,
        )
        self.session.add(project)
        await self.session.flush()
        await self.session.refresh(project)  # created_at / updated_at 回读
        if material_ids:
            await self.add_materials(project.id, material_ids)
        return project

    async def update(self, project: Project, fields: dict) -> Project:
        for k, v in fields.items():
            if v is not None and hasattr(project, k):
                setattr(project, k, v)
        await self.session.flush()
        await self.session.refresh(project)
        return project

    async def set_status(self, project: Project, status: ProjectStatus) -> Project:
        project.status = status
        await self.session.flush()
        await self.session.refresh(project)
        return project

    # ---------------- 素材关联 ----------------

    async def add_materials(
        self, project_id: uuid.UUID, material_ids: list[uuid.UUID]
    ) -> int:
        existing = set(await self.material_ids(project_id))
        sort = len(existing)
        added = 0
        for mid in dict.fromkeys(material_ids):
            if mid in existing:
                continue
            self.session.add(ProjectMaterial(project_id=project_id, material_id=mid, sort=sort))
            sort += 1
            added += 1
        await self.session.flush()
        return added

    async def remove_material(self, project_id: uuid.UUID, material_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(ProjectMaterial).where(
                ProjectMaterial.project_id == project_id,
                ProjectMaterial.material_id == material_id,
            )
        )
        await self.session.flush()

    async def material_ids(self, project_id: uuid.UUID) -> list[uuid.UUID]:
        rows = (
            await self.session.execute(
                select(ProjectMaterial.material_id)
                .where(ProjectMaterial.project_id == project_id)
                .order_by(ProjectMaterial.sort.asc())
            )
        ).scalars().all()
        return list(rows)

    async def materials_of(
        self, project_id: uuid.UUID
    ) -> list[tuple[ProjectMaterial, Material, NewsItem, Annotation | None]]:
        """选题详情用：素材 + 资讯 + 点评（一次 join，避免 N+1）。"""
        stmt = (
            select(ProjectMaterial, Material, NewsItem, Annotation)
            .join(Material, Material.id == ProjectMaterial.material_id)
            .join(NewsItem, NewsItem.id == Material.news_item_id)
            .outerjoin(
                Annotation,
                and_(
                    Annotation.material_id == Material.id,
                    Annotation.deleted_at.is_(None),
                ),
            )
            .where(ProjectMaterial.project_id == project_id)
            .order_by(ProjectMaterial.sort.asc())
        )
        return list((await self.session.execute(stmt)).all())

    async def material_counts(self, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not project_ids:
            return {}
        rows = (
            await self.session.execute(
                select(ProjectMaterial.project_id, ProjectMaterial.material_id).where(
                    ProjectMaterial.project_id.in_(project_ids)
                )
            )
        ).all()
        out: dict[uuid.UUID, int] = {}
        for pid, _ in rows:
            out[pid] = out.get(pid, 0) + 1
        return out

    async def touch(self, project: Project) -> None:
        project.updated_at = datetime.now()
        await self.session.flush()


class PromptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[PromptTemplate]:
        stmt = (
            select(PromptTemplate)
            .where(
                PromptTemplate.deleted_at.is_(None),
                (PromptTemplate.user_id == user_id) | (PromptTemplate.user_id.is_(None)),
            )
            .order_by(PromptTemplate.category.asc(), PromptTemplate.version_no.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def by_ids(self, ids: list[uuid.UUID]) -> list[PromptTemplate]:
        if not ids:
            return []
        stmt = select(PromptTemplate).where(PromptTemplate.id.in_(ids))
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        name: str,
        category: str,
        body: str,
        description: str | None,
        variables: list[str],
    ) -> PromptTemplate:
        latest = (
            await self.session.execute(
                select(PromptTemplate.version_no)
                .where(PromptTemplate.user_id == user_id, PromptTemplate.name == name)
                .order_by(PromptTemplate.version_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        row = PromptTemplate(
            user_id=user_id,
            name=name,
            category=category,
            version_no=(latest or 0) + 1,
            body=body,
            description=description,
            variables=variables,
            is_official=False,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row


__all__ = ["ProjectRepository", "PromptRepository"]
