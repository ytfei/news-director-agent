"""事实基线 + 体检报告：fact_cards / fact_card_claims / review_reports / review_findings

设计依据：`docs/06-prototype-to-impl.md` §5.3、§5.4，以及 `docs/01` §4.2 B/C。

两条硬约束：
1. **没有 evidence 的 claim 不允许标 verified**，只能标 unverifiable；
2. finding 必须可定位（span_start/span_end），否则前端无法划词高亮与一键采纳。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import (
    FactStatus,
    FindingSeverity,
    FindingStatus,
    FindingTrack,
    ReportVerdict,
    sa_enum,
)

OPEN_FINDINGS = text("status = 'open'")


class FactCard(UUIDPkMixin, TimestampMixin, Base):
    """资讯级事实基线。ingest 阶段异步预生成，review 时只读缓存。"""

    __tablename__ = "fact_cards"
    __table_args__ = (Index("ix_fact_cards_news", "news_item_id", unique=True),)

    news_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False
    )
    context_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_symbols: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    # 还没查清的问题 → 决定"哪些话不能说死"
    open_questions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="ready")
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FactCardClaim(UUIDPkMixin, Base):
    """原子化事实断言 + 状态 + 证据 + 置信度。"""

    __tablename__ = "fact_card_claims"
    __table_args__ = (
        UniqueConstraint("card_id", "seq", name="uq_fact_card_claims"),
        Index("ix_fact_card_claims_card", "card_id", "seq"),
    )

    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fact_cards.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[FactStatus] = mapped_column(
        sa_enum(FactStatus, "fact_status"), nullable=False, server_default="unverifiable"
    )
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, server_default="0.50")
    # [{src, date, snippet}]
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class ReviewReport(UUIDPkMixin, TimestampMixin, Base):
    """一次检查的产物。绑定「点评 + 版本号」，这样复检的 diff 才可比较。"""

    __tablename__ = "review_reports"
    __table_args__ = (
        Index("ix_review_reports_annotation", "annotation_id", "created_at"),
        Index("ix_review_reports_user", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    annotation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False
    )
    annotation_version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[ReportVerdict] = mapped_column(
        sa_enum(ReportVerdict, "report_verdict"), nullable=False, server_default="passed"
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ReviewFinding(UUIDPkMixin, TimestampMixin, Base):
    """结构化发现项。三轨（fact/logic/compliance）阈值取向不同，因此 track 与 severity 分开存。"""

    __tablename__ = "review_findings"
    __table_args__ = (
        Index("ix_review_findings_report", "report_id", "severity"),
        Index("ix_review_findings_open", "status", postgresql_where=OPEN_FINDINGS),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("review_reports.id", ondelete="CASCADE"), nullable=False
    )
    track: Mapped[FindingTrack] = mapped_column(sa_enum(FindingTrack, "finding_track"), nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(
        sa_enum(FindingSeverity, "finding_severity"), nullable=False
    )
    status: Mapped[FindingStatus] = mapped_column(
        sa_enum(FindingStatus, "finding_status"), nullable=False, server_default="open"
    )
    # 划词定位：缺省 0/0 表示整条点评
    span_start: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    span_end: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["FactCard", "FactCardClaim", "ReviewReport", "ReviewFinding"]
