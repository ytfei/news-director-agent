"""Alembic 环境。

要点（docs/05-database-schema.md §1.1）：
- naming_convention 避免 autogenerate 噪声
- pgvector 的 Vector 类型、自定义 ENUM 变更需手写迁移，不盲信 autogenerate
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models.agent import AgentRun, AgentStep, Notification, UsageRecord  # noqa: F401
from app.models.base import Base
from app.models.ingest import RawDocument, SourceConnector, SyncRun  # noqa: F401
from app.models.material import (  # noqa: F401
    Annotation,
    AnnotationVersion,
    Material,
    MaterialTopic,
    Topic,
)
from app.models.news import (  # noqa: F401
    NewsCluster,
    NewsItem,
    NewsItemRelation,
    NewsItemSymbol,
    NewsItemTag,
    Tag,
)
from app.models.project import (  # noqa: F401
    Article,
    ArticleVersion,
    Project,
    ProjectMaterial,
    PromptTemplate,
)
from app.models.review import FactCard, FactCardClaim, ReviewFinding, ReviewReport  # noqa: F401
from app.models.user import User, UserInterest, UserNewsAction  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
