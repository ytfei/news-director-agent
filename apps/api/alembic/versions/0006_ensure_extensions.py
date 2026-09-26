"""0006 · 确保扩展存在（幂等）

为什么需要它：
扩展此前只在 `infra/initdb/00-extensions.sql` 里创建，而那段 SQL 只在 **容器首次
初始化**时对默认库执行一次。于是任何"新建的库"直接跑 `alembic upgrade head`
都会在第一个 VECTOR 列上失败（type "vector" does not exist）——全新环境部署、
CI 建临时库、以及本次新建的 nda_test 都会踩到。

放在迁移里才能保证"任意空库 + upgrade head"都成立。IF NOT EXISTS 保证幂等。

Revision ID: 0006_ensure_extensions
Revises: 0005_market_facts
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_ensure_extensions"
down_revision: str | None = "0005_market_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXTENSIONS = ("pgcrypto", "vector", "pg_trgm")


def upgrade() -> None:
    for ext in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")


def downgrade() -> None:
    # 不删除扩展：其他对象可能依赖，且误删的风险远大于收益
    pass
