"""0002 · 触发器：updated_at 统一维护 + search_tsv 自动维护

docs/05-database-schema.md §4.11 / §3.2

Revision ID: 0002_triggers
Revises: c6fca63ba48f
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_triggers"
down_revision: str | None = "c6fca63ba48f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 含 updated_at 的业务表（新增表时同步维护此列表）
TABLES_WITH_UPDATED_AT = [
    "users",
    "source_connectors",
    "news_clusters",
    "news_items",
    "user_interests",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END $$ LANGUAGE plpgsql;
        """
    )
    for table in TABLES_WITH_UPDATED_AT:
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};
            CREATE TRIGGER trg_{table}_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )

    # search_tsv：v1 不建 GIN 索引（'simple' 对中文不分词），保留列与触发器，
    # 待镜像装 zhparser 后把配置切为 'zhcfg' 再补建索引（见 §4.8）
    op.execute(
        """
        CREATE OR REPLACE FUNCTION news_items_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_tsv :=
                setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.summary, '')), 'B') ||
                setweight(to_tsvector('simple', left(coalesce(NEW.content, ''), 20000)), 'C');
            RETURN NEW;
        END $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_news_items_tsv ON news_items;
        CREATE TRIGGER trg_news_items_tsv
            BEFORE INSERT OR UPDATE OF title, summary, content
            ON news_items FOR EACH ROW EXECUTE FUNCTION news_items_tsv_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_news_items_tsv ON news_items;")
    op.execute("DROP FUNCTION IF EXISTS news_items_tsv_update();")
    for table in TABLES_WITH_UPDATED_AT:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
