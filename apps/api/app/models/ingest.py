"""采集层（ODS）：source_connectors / raw_documents / sync_runs"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin
from app.models.enums import (
    ConnectorStatus,
    ConnectorType,
    ContentType,
    SyncStatus,
    sa_enum,
)


class SourceConnector(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """数据源实例。owner_id IS NULL = 平台公共源。"""

    __tablename__ = "source_connectors"
    __table_args__ = (
        # ★ 不能把 deleted_at 放进 UNIQUE：软删两次即失效，且 PG 中 NULL 互不相等
        Index(
            "uq_source_connectors_owner_key",
            "owner_id",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND owner_id IS NOT NULL"),
        ),
        Index(
            "uq_source_connectors_platform_key",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND owner_id IS NULL"),
        ),
        Index(
            "ix_source_connectors_next_run",
            "status",
            "next_run_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    connector_type: Mapped[ConnectorType] = mapped_column(
        sa_enum(ConnectorType, "connector_type"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)  # 注册表 key，如 'tushare.news'
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ConnectorStatus] = mapped_column(
        sa_enum(ConnectorStatus, "connector_status"), nullable=False, server_default="active"
    )

    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # 只存引用，真实密钥加密后放 KMS / Fernet
    credentials_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    capability: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    schedule_cron: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RawDocument(UUIDPkMixin, Base):
    """ODS 原始层，全量留档，永不覆盖。价值：归一化规则可"重放"。"""

    __tablename__ = "raw_documents"
    __table_args__ = (
        UniqueConstraint("connector_id", "external_id", name="uq_raw_documents_connector_external"),
        Index(
            "ix_raw_documents_normalized",
            "normalized_at",
            postgresql_where=text("normalized_at IS NULL"),
        ),
        Index("ix_raw_documents_published", "published_at"),
    )

    connector_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_connectors.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[ContentType] = mapped_column(
        sa_enum(ContentType, "content_type"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    # sha256(canonical_json(payload))，见 05 §4.8
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class SyncRun(UUIDPkMixin, Base):
    """每次同步运行的可观测记录。"""

    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sync_runs_connector_started", "connector_id", "started_at"),
        Index(
            "ix_sync_runs_running",
            "status",
            postgresql_where=text("status = 'running'"),
        ),
    )

    connector_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_connectors.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[SyncStatus] = mapped_column(
        sa_enum(SyncStatus, "sync_status"), nullable=False, server_default="running"
    )
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    deduped_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duplicated_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_segments: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["SourceConnector", "RawDocument", "SyncRun", "TSVECTOR"]
