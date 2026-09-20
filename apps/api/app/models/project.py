"""选题 / 提示词 / 稿件：projects / project_materials / prompt_templates / articles / article_versions

设计依据：`docs/06-prototype-to-impl.md` §5.5。

★ 关键差异（相对 01 §3.2 早期设计）：选题聚合的是**素材**而不是「资讯 + 点评」。
点评挂在素材上，因此"有点评"与"没点评"的素材走同一个关联表，写作门槛只需校验素材数量。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin
from app.models.enums import (
    ArticleStatus,
    ArticleVersionSource,
    ProjectMaterialRole,
    ProjectStatus,
    PromptCategory,
    sa_enum,
)

ALIVE = text("deleted_at IS NULL")
PROMPT_USER_UNIQ = text("deleted_at IS NULL AND user_id IS NOT NULL")
PROMPT_SYSTEM_UNIQ = text("deleted_at IS NULL AND user_id IS NULL")


class Project(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """选题 = 一组素材 + 写作配置。"""

    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_user_status", "user_id", "status"),
        Index("ix_projects_user_updated", "user_id", "updated_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[ProjectStatus] = mapped_column(
        sa_enum(ProjectStatus, "project_status"), nullable=False, server_default="collecting"
    )
    # 公众号 / 雪球 / 微博 / 小红书 —— 影响字数与结构
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    require_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 提示词组合（人格 + 结构 + 禁忌）
    prompt_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    compose_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )


class ProjectMaterial(Base):
    """选题 ↔ 素材。role=primary 走观点层，background 只作背景事实。复合主键，无独立 id。"""

    __tablename__ = "project_materials"
    # (project_id, material_id) 已是复合主键，无需额外唯一约束
    __table_args__ = (Index("ix_project_materials_material", "material_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ProjectMaterialRole] = mapped_column(
        sa_enum(ProjectMaterialRole, "project_material_role"),
        nullable=False,
        server_default="primary",
    )
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class PromptTemplate(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """提示词 = 可版本化、可按需加载进 Agent 的技能包。user_id IS NULL 为官方模板库。"""

    __tablename__ = "prompt_templates"
    __table_args__ = (
        Index(
            "uq_prompt_templates_user_name_ver",
            "user_id",
            "name",
            "version_no",
            unique=True,
            postgresql_where=PROMPT_USER_UNIQ,
        ),
        Index(
            "uq_prompt_templates_system_name_ver",
            "name",
            "version_no",
            unique=True,
            postgresql_where=PROMPT_SYSTEM_UNIQ,
        ),
        Index("ix_prompt_templates_category", "category"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[PromptCategory] = mapped_column(
        sa_enum(PromptCategory, "prompt_category"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    variables: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Article(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "articles"
    __table_args__ = (Index("ix_articles_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[ArticleStatus] = mapped_column(
        sa_enum(ArticleStatus, "article_status"), nullable=False, server_default="draft"
    )
    current_version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)


class ArticleVersion(UUIDPkMixin, Base):
    """稿件版本。citation_map 承载「段落 → 资讯/证据」的可追溯链路。"""

    __tablename__ = "article_versions"
    __table_args__ = (
        UniqueConstraint("article_id", "version_no", name="uq_article_versions"),
        Index("ix_article_versions_article", "article_id", "version_no"),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    citation_map: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    source: Mapped[ArticleVersionSource] = mapped_column(
        sa_enum(ArticleVersionSource, "article_version_source"),
        nullable=False,
        server_default="ai",
    )
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


__all__ = [
    "Project",
    "ProjectMaterial",
    "PromptTemplate",
    "Article",
    "ArticleVersion",
]
