"""数值事实表（市场信息）。

## 为什么要独立建表，而不是塞进 `news_items`

"某标的价格 = 7.4 万元/吨"和"某公司发了一篇公告"是两种东西：
前者是**可核查、可计算、可对齐时间轴**的数值，后者是文本。塞进同一张表的后果：
- 文本表要长出 metric/unit/period/ts_code 一堆只在少数行有值的列
- 事实核对（FactCard）要在正文里正则撒网，而不是查结构化数据
- 将来的行情 / 资金流 / 宏观指标会持续膨胀这张表的列

## 长表建模

**一行一个指标**（而不是一行多个指标列）：
新指标只需插数据，不改表结构。这是"接任意数据源"的前提。

## 本期状态

本期只接 tushare 快讯，快讯不产出数值事实 → **这张表当前没有数据源在写**。
但它不是死代码：`MarketFactRepository.upsert_from_item()` 是真实可用的写入路径，
由单测覆盖（含幂等），读取接口也已打通。
接行情数据源时的下一步：写一个产出 `Metric` 的连接器 + 一个 `ChannelSpec.metric_specs`，
落库链路不需要改（见 TODO）。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class MarketFact(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """一条数值事实：某个标的/某个指标，在某个时点，等于某个值。"""

    __tablename__ = "market_facts"
    __table_args__ = (
        # 幂等：同一连接器的同一条事实只落一次。
        # external_id 由"来源幂等键 + 指标名 + 时点"派生（见 MarketFactRepository），
        # 所以同一个 payload 重复拉取不会产生重复事实。
        Index(
            "uq_market_facts_source_external",
            "source_connector_id",
            "external_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # 主查询路径：按标的看某指标的时间序列
        Index("ix_market_facts_symbol_name_time", "ts_code", "name", "observed_at"),
        # 宏观类指标没有标的：按指标名取时间序列
        Index("ix_market_facts_name_time", "name", "observed_at"),
        Index("ix_market_facts_news", "news_item_id"),
    )

    # ---- 事实本身 ----
    # 注释与迁移 0005 保持一致：不一致会让 alembic check 报出多余的 modify_comment 差异
    name: Mapped[str] = mapped_column(Text, nullable=False, comment="指标名")
    # 24 位总长、6 位小数：覆盖"75000000000（元）"这类大额与"0.000125"这类比率
    value: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    period: Mapped[str | None] = mapped_column(Text, nullable=True, comment="2026Q2 / 2026-08")
    ts_code: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="标准码；宏观指标为空"
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- 溯源（和资讯条目一样必须能回溯到原始层） ----
    source_connector_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_connectors.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("raw_documents.id", ondelete="SET NULL"), nullable=True
    )
    # 该数值来自哪条资讯（若它本来就附带在文本里，如"产能利用率 85%"）
    news_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("news_items.id", ondelete="SET NULL"),
        nullable=True,
        comment="该数值来自哪条资讯（如正文里的「产能利用率 85%」）",
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)

    # ---- 扩展 ----
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # 该指标的原始片段（便于排查"这个数字到底怎么算出来的"）
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


__all__ = ["MarketFact"]
