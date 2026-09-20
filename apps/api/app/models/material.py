"""素材层（M2 中枢）：topics / materials / material_topics / annotations / annotation_versions

设计依据：`docs/06-prototype-to-impl.md` §2、§5.1、§5.2。

为什么素材要独立成表，而不是复用 `user_news_actions`：
- 行为流（read/star/rate）是**信号**，素材是**意图**（我打算写它）；
- 素材需要承载三个维度的编辑态（评分 1~10 / 主题多值 / 日期），并成为点评与选题的外键锚点。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin
from app.models.enums import (
    AnnotationStatus,
    AnnotationVersionSource,
    MaterialStatus,
    sa_enum,
)

MATERIAL_ALIVE = text("deleted_at IS NULL")
TOPIC_USER_UNIQ = text("deleted_at IS NULL AND user_id IS NOT NULL")
TOPIC_SYSTEM_UNIQ = text("deleted_at IS NULL AND user_id IS NULL")


class Topic(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """主题标签。`user_id IS NULL` 表示系统预设，用户可另建同名主题互不干扰。"""

    __tablename__ = "topics"
    __table_args__ = (
        Index("uq_topics_user_slug", "user_id", "slug", unique=True, postgresql_where=TOPIC_USER_UNIQ),
        Index("uq_topics_system_slug", "slug", unique=True, postgresql_where=TOPIC_SYSTEM_UNIQ),
        Index("ix_topics_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Material(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """素材 = 被用户标记的资讯 + 三维编辑态（评分 / 日期 / 主题）。"""

    __tablename__ = "materials"
    __table_args__ = (
        # 一条资讯在同一用户下最多一个素材（部分唯一：软删后可重新标记）
        Index(
            "uq_materials_user_news",
            "user_id",
            "news_item_id",
            unique=True,
            postgresql_where=MATERIAL_ALIVE,
        ),
        # 工作台 / 选题的一级排序：日期降序 + 评分降序
        Index("ix_materials_user_date", "user_id", "material_date"),
        Index("ix_materials_user_score", "user_id", "score"),
        Index("ix_materials_news", "news_item_id"),
        CheckConstraint("score BETWEEN 1 AND 10", name="score_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    news_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False
    )
    # 「每天一个素材组」的天然归档键
    material_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    # 想写的程度。1~10 而非 1~5：主理人实际只会用 7~10，5 级区分度不够
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="5")
    status: Mapped[MaterialStatus] = mapped_column(
        sa_enum(MaterialStatus, "material_status"), nullable=False, server_default="active"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class MaterialTopic(Base):
    """素材 ↔ 主题（多值标签）。复合主键，无独立 id。"""

    __tablename__ = "material_topics"
    __table_args__ = (Index("ix_material_topics_topic", "topic_id", "created_at"),)

    material_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class Annotation(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """点评。★ 可选：素材可以没有点评（走「素材综述模式」）。

    `news_item_id` 是刻意的冗余——按资讯反查点评（详情页、FactCard 补查）不必回表 materials。
    """

    __tablename__ = "annotations"
    __table_args__ = (
        Index("uq_annotations_material", "material_id", unique=True, postgresql_where=MATERIAL_ALIVE),
        Index("ix_annotations_user_status", "user_id", "status"),
        Index("ix_annotations_news", "news_item_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    news_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AnnotationStatus] = mapped_column(
        sa_enum(AnnotationStatus, "annotation_status"), nullable=False, server_default="draft"
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    current_version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnnotationVersion(UUIDPkMixin, Base):
    """点评版本快照。采纳 AI 建议也生成新版本（source=ai_adopt），保证可回溯。"""

    __tablename__ = "annotation_versions"
    __table_args__ = (
        UniqueConstraint("annotation_id", "version_no", name="uq_annotation_versions"),
        Index("ix_annotation_versions_annotation", "annotation_id", "version_no"),
    )

    annotation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[AnnotationVersionSource] = mapped_column(
        sa_enum(AnnotationVersionSource, "annotation_version_source"),
        nullable=False,
        server_default="manual",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


__all__ = ["Topic", "Material", "MaterialTopic", "Annotation", "AnnotationVersion"]
