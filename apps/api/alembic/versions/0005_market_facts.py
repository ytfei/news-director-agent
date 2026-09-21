"""0005 · 数值事实表（market_facts）

数值型市场信息（行情 / 资金流 / 宏观指标）与文本资讯分流存储：
"某标的价格 = 7.4 万元/吨"是可核查、可对齐时间轴的结构化数值，
塞进 news_items 会让文本表长出一堆只在少数行有值的列，事实核对也只能在正文里正则撒网。

长表建模（一行一个指标）：新增指标只插数据，不改表结构。

本期只接 tushare 快讯（不产出数值事实），因此**这张表当前没有数据源在写**；
写入路径由 MarketFactRepository + 单测覆盖，确保接行情源时链路是通的。

Revision ID: 0005_market_facts
Revises: 0004_system_topics
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_market_facts"
down_revision: str | None = "0004_system_topics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "market_facts",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # ---- 事实本身 ----
        sa.Column("name", sa.Text(), nullable=False, comment="指标名"),
        # 24 位总长、6 位小数：覆盖 75000000000（元）这类大额与 0.000125 这类比率
        sa.Column("value", sa.Numeric(24, 6), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("period", sa.Text(), nullable=True, comment="2026Q2 / 2026-08"),
        sa.Column("ts_code", sa.Text(), nullable=True, comment="标准码；宏观指标为空"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        # ---- 溯源（与新闻条目一样必须能回溯到原始层） ----
        sa.Column(
            "source_connector_id",
            UUID,
            sa.ForeignKey("source_connectors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_document_id",
            UUID,
            sa.ForeignKey("raw_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "news_item_id",
            UUID,
            sa.ForeignKey("news_items.id", ondelete="SET NULL"),
            nullable=True,
            comment="该数值来自哪条资讯（如正文里的「产能利用率 85%」）",
        ),
        sa.Column("external_id", sa.Text(), nullable=False),
        # ---- 扩展 ----
        sa.Column("attributes", JSONB, nullable=False, server_default="{}"),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        # ---- 时间戳 ----
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 幂等：同一连接器的同一条事实只落一次（部分唯一索引，不把 deleted_at 写进约束）
    op.create_index(
        "uq_market_facts_source_external",
        "market_facts",
        ["source_connector_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # 主查询路径：按标的取某指标的时间序列
    op.create_index(
        "ix_market_facts_symbol_name_time", "market_facts", ["ts_code", "name", "observed_at"]
    )
    # 宏观类指标没有标的：按指标名取时间序列
    op.create_index("ix_market_facts_name_time", "market_facts", ["name", "observed_at"])
    op.create_index("ix_market_facts_news", "market_facts", ["news_item_id"])

    # updated_at 触发器（函数由迁移 0002 创建）
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_market_facts_updated_at ON market_facts;
        CREATE TRIGGER trg_market_facts_updated_at
            BEFORE UPDATE ON market_facts
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_market_facts_updated_at ON market_facts;")
    op.drop_table("market_facts")
