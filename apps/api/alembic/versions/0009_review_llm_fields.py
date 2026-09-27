"""检查引擎接模型：报告元信息 + finding 溯源字段（B1 前置）

`review_reports` 新增：
- `mode`            rules / llm / hybrid —— 这份报告是怎么产出的
- `prompt_version`  ★ 参与缓存键。改 prompt 后旧报告必须失效，
                    否则用户永远命中旧结论（docs/05 §3.4 已指出该风险）
- `model`           实际档位，便于复现与成本归因

`review_findings` 新增：
- `rule_code`       命中的红线规则码（compliance 轨），统计哪条最常命中
- `claim_id`        回指 fact_card_claims，让 finding 能追到事实基线的哪条断言
- `confidence`      模型置信度 —— 三轨用不同阈值过滤的依据
                    （fact 高精度要高分、compliance 高召回可放低，见 docs/01 §4.2 C）

★ 索引说明：`ix_review_reports_cache` **不是唯一索引**。
报告要保留历史（用户可回看每次检查），缓存命中由应用层判断，不由数据库约束。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_review_llm_fields"
down_revision: str | None = "0008_embedding_dim_1024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "review_reports",
        sa.Column("mode", sa.Text(), nullable=False, server_default="rules"),
    )
    op.add_column(
        "review_reports",
        sa.Column("prompt_version", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("review_reports", sa.Column("model", sa.Text(), nullable=True))

    op.add_column("review_findings", sa.Column("rule_code", sa.Text(), nullable=True))
    op.add_column(
        "review_findings",
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "review_findings",
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=True),
    )

    op.create_index(
        "ix_review_reports_cache",
        "review_reports",
        ["annotation_id", "annotation_version_no", "prompt_version"],
    )
    op.create_index("ix_review_findings_claim", "review_findings", ["claim_id"])
    op.create_index("ix_review_findings_rule", "review_findings", ["rule_code"])
    op.create_foreign_key(
        "fk_review_findings_claim",
        "review_findings",
        "fact_card_claims",
        ["claim_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_review_findings_claim", "review_findings", type_="foreignkey")
    op.drop_index("ix_review_findings_rule", table_name="review_findings")
    op.drop_index("ix_review_findings_claim", table_name="review_findings")
    op.drop_index("ix_review_reports_cache", table_name="review_reports")

    op.drop_column("review_findings", "confidence")
    op.drop_column("review_findings", "claim_id")
    op.drop_column("review_findings", "rule_code")

    op.drop_column("review_reports", "model")
    op.drop_column("review_reports", "prompt_version")
    op.drop_column("review_reports", "mode")
