"""0007 · 分层去重所需字段

配合 `app/lib/dedupe.py` 的四层方案：
- `normalized_title`：归一化后的标题（去来源前缀 / 全半角 / 标点），用于可比性
- `minhash` / `minhash_bucket`：MinHash 签名与 LSH 粗筛桶（L3 转载判定）
- `news_clusters.duplicate_count`：转载条数（与 `member_count` 区分开）

为什么要分开 member_count 与 duplicate_count：
  member_count    = 簇内**独立报道**数（不同角度，都要保留）
  duplicate_count = 被判定为"同一篇转载"的条数（合并展示，不单独出现）
混在一起会让前端「另有 N 家报道」显示不准。

Revision ID: 0007_dedupe_fields
Revises: 0006_ensure_extensions
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_dedupe_fields"
down_revision: str | None = "0006_ensure_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("news_items", sa.Column("normalized_title", sa.Text(), nullable=True))
    op.add_column("news_items", sa.Column("minhash", sa.LargeBinary(), nullable=True))
    op.add_column("news_items", sa.Column("minhash_bucket", sa.BigInteger(), nullable=True))
    op.create_index(
        "ix_news_items_minhash_bucket", "news_items", ["minhash_bucket", "published_at"]
    )
    op.add_column(
        "news_clusters",
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("news_clusters", "duplicate_count")
    op.drop_index("ix_news_items_minhash_bucket", table_name="news_items")
    op.drop_column("news_items", "minhash_bucket")
    op.drop_column("news_items", "minhash")
    op.drop_column("news_items", "normalized_title")
