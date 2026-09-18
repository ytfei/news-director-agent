"""Agent 执行与治理：agent_runs / agent_steps / usage_records / notifications"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPkMixin
from app.models.enums import RunGraph, RunStatus, sa_enum

ACTIVE_RUNS = text("status IN ('queued','running','waiting_human')")


class AgentRun(UUIDPkMixin, Base):
    """每次 Agent 执行（成本、可追溯、可恢复的核心）。"""

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_user_time", "user_id", "created_at"),
        Index("ix_agent_runs_status", "status", postgresql_where=ACTIVE_RUNS),
        Index("ix_agent_runs_thread", "thread_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    graph: Mapped[RunGraph] = mapped_column(sa_enum(RunGraph, "run_graph"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        sa_enum(RunStatus, "run_status"), nullable=False, server_default="queued"
    )
    # LangGraph checkpointer thread_id（= 本行 id 字符串）
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )

    input: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    output: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # HITL：等待人工时的断点数据（resume 时清空）
    interrupt_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_input: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    token_output: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentStep(UUIDPkMixin, Base):
    """步骤级 trace，用于"Agent 正在做什么"的可视化与调试。"""

    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_agent_steps"),
        Index("ix_agent_steps_run", "run_id", "seq"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    node: Mapped[str] = mapped_column(Text, nullable=False)
    # node / tool / llm / handoff / interrupt
    step_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    output: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    token_input: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    token_output: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class UsageRecord(UUIDPkMixin, Base):
    """用量与计费台账。★ M1 就要有：成本可见性 + 硬配额的基础。"""

    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_records_user_day", "user_id", "occurred_on"),
        Index("ix_usage_records_category", "category", "occurred_on"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    # review / compose / research / enrich
    category: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_input: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    token_output: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, server_default="0")
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class Notification(UUIDPkMixin, Base):
    """站内通知：检查完成 / 写作完成 / 同步异常 / 配额。"""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_user_unread",
            "user_id",
            "created_at",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


__all__ = ["AgentRun", "AgentStep", "UsageRecord", "Notification", "String"]
