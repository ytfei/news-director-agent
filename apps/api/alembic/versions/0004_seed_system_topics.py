"""0004 · 预置系统主题（素材标签的起步词表）

为什么需要：素材的主题是多值标签，如果让用户从零开始打，
前几次标记会退化成"想到什么写什么"，跨日期的聚类价值就没了。
预置一批财经/科技场景的高频主题（与原型 `DB.topics` 一致），
用户仍可另建同名主题（`topics` 的双部分唯一索引支持）。

Revision ID: 0004_system_topics
Revises: 0003_materials
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_system_topics"
down_revision: str | None = "0003_materials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TOPICS = [
    "扩产",
    "半导体",
    "业绩",
    "白酒",
    "政策",
    "算力",
    "订单",
    "新能源",
    "宏观",
    "美联储",
    "出口",
    "机械",
    "AI",
    "回购",
    "传闻",
]


def upgrade() -> None:
    values = ", ".join(f"(NULL, lower('{t}'), '{t}', true)" for t in TOPICS)
    op.execute(
        f"""
        INSERT INTO topics (user_id, slug, name, is_system)
        VALUES {values}
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    names = ", ".join(f"'{t}'" for t in TOPICS)
    op.execute(f"DELETE FROM topics WHERE user_id IS NULL AND is_system AND name IN ({names});")
