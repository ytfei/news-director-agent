"""用户与兴趣层：users / user_interests / user_news_actions"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin
from app.models.enums import ActionType, sa_enum


class User(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    # 团队版多租户预留，v1 恒 NULL（= 个人）
    org_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    email: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
    quota: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserInterest(UUIDPkMixin, TimestampMixin, Base):
    """兴趣画像（驱动收件箱召回与排序）。"""

    __tablename__ = "user_interests"
    __table_args__ = (
        UniqueConstraint("user_id", "dimension", "value", name="uq_user_interests"),
        Index("ix_user_interests_user", "user_id", "dimension"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # market / content_type / industry / source / keyword / ts_code
    dimension: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    # include / exclude（屏蔽词）
    polarity: Mapped[str] = mapped_column(Text, nullable=False, server_default="include")
    weight: Mapped[float] = mapped_column(nullable=False, server_default="1.000")
    # user / learned / template
    origin: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")


class UserNewsAction(UUIDPkMixin, Base):
    """行为流。★ 同时承载"状态类"与"行为流"两种语义，用部分唯一索引区分。"""

    __tablename__ = "user_news_actions"
    __table_args__ = (
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="ck_user_news_actions_rating"),
        # 状态类动作（star/unstar/hide/rate）只保留最新；read 属行为流，需保留多次
        Index(
            "uq_user_news_actions_state",
            "user_id",
            "news_item_id",
            "action",
            unique=True,
            postgresql_where=text("action <> 'read'"),
        ),
        Index("ix_user_news_actions_user_time", "user_id", "created_at"),
        Index("ix_user_news_actions_news", "news_item_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    news_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[ActionType] = mapped_column(sa_enum(ActionType, "action_type"), nullable=False)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    dwell_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


__all__ = ["User", "UserInterest", "UserNewsAction"]
