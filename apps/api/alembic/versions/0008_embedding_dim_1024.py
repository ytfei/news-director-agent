"""embedding 2048 → 1024 维（Matryoshka 降维），并建 HNSW 索引

背景（2026-09-28 定案）：
- doubao-embedding-vision 原生 2048 维；
- pgvector 的 HNSW / IVFFlat 索引**硬上限 2000 维** → 2048 时索引建不了，
  语义检索退化为 O(n) 全表扫描（0001 迁移因此是条件化建索引，实际被跳过）；
- 该模型支持 `dimensions` 参数，由模型端直接输出 1024 维
  （Matryoshka 表征：前 N 维本身即有效的低维表示，不是简单截断）。

本迁移做三件事：
1. 清空存量向量 —— 维度变更意味着旧向量作废，**不可沿用**，需由 enrich 全量重算；
2. `vector(2048)` → `vector(1024)`；
3. 建 HNSW 索引 —— 1024 ≤ 2000，这次终于能建了（O(n) → O(log n)）。

幂等：全新环境从 0001 起跑时列已是 1024 且索引已建，本迁移全部跳过。
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op
from app.core.config import settings

revision: str = "0008_embedding_dim_1024"
down_revision: str | None = "0007_dedupe_fields"
branch_labels = None
depends_on = None


TARGET_DIM = settings.EMBEDDING_DIM
VECTOR_INDEX_MAX_DIM = 2000
PREVIOUS_DIM = 2048  # 仅用于 downgrade

# 项目中全部向量列（app/models/news.py）
COLUMNS = (
    ("news_items", "embedding"),
    ("news_clusters", "centroid"),
)


def _current_dim(conn, table: str, column: str) -> int | None:
    """读取列当前的 vector(N) 维度；列不存在或不是 vector 时返回 None。"""
    # 表名来自 COLUMNS 常量（代码内硬编码，非用户输入）→ 可直接拼接；
    # 它出现在 ::regclass 的位置，不能走参数绑定（SQLAlchemy 的 text() 会被 `::` 干扰）。
    val = conn.execute(
        sa.text(
            f"SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            f"WHERE a.attrelid = '{table}'::regclass AND a.attname = :c AND a.attnum > 0"
        ),
        {"c": column},
    ).scalar()
    if not val:
        return None
    m = re.search(r"\((\d+)\)", val or "")
    return int(m.group(1)) if m else None


def upgrade() -> None:
    conn = op.get_bind()

    for table, column in COLUMNS:
        current = _current_dim(conn, table, column)
        if current is None or current == TARGET_DIM:
            continue
        # 维度变更 → 存量全部作废，交由 enrich 重算（不能保留旧值）
        op.execute(sa.text(f"UPDATE {table} SET {column} = NULL WHERE {column} IS NOT NULL"))
        op.execute(
            sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE vector({TARGET_DIM})")
        )

    if TARGET_DIM <= VECTOR_INDEX_MAX_DIM:
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_news_items_embedding ON news_items "
                "USING hnsw (embedding vector_cosine_ops)"
            )
        )
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_news_clusters_centroid ON news_clusters "
                "USING hnsw (centroid vector_cosine_ops)"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()

    op.execute(sa.text("DROP INDEX IF EXISTS ix_news_items_embedding"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_news_clusters_centroid"))

    for table, column in COLUMNS:
        current = _current_dim(conn, table, column)
        if current is None or current == PREVIOUS_DIM:
            continue
        op.execute(sa.text(f"UPDATE {table} SET {column} = NULL WHERE {column} IS NOT NULL"))
        op.execute(
            sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE vector({PREVIOUS_DIM})")
        )
