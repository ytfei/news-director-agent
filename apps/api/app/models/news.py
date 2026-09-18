"""资讯层（DWD）主表：tags / news_clusters / news_items"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin
from app.models.enums import ClusterStatus, ContentType, sa_enum

DIM = settings.EMBEDDING_DIM
NOT_DELETED = text("deleted_at IS NULL")


class Tag(UUIDPkMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (Index("ix_tags_dimension", "dimension"),)

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tags.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class NewsCluster(UUIDPkMixin, TimestampMixin, Base):
    """事件簇：同一事件的多源报道归一。"""

    __tablename__ = "news_clusters"
    __table_args__ = (
        Index("ix_news_clusters_last_seen", "last_seen_at"),
        Index(
            "ix_news_clusters_centroid",
            "centroid",
            postgresql_using="hnsw",
            postgresql_ops={"centroid": "vector_cosine_ops"},
        ),
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ClusterStatus] = mapped_column(
        sa_enum(ClusterStatus, "cluster_status"), nullable=False, server_default="open"
    )
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # 多少家媒体报道 → 交叉验证强度。★ 由跨源登记维护，不能因去重丢失（05 §4.9）
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    importance: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    centroid: Mapped[list[float] | None] = mapped_column(Vector(DIM), nullable=True)


class NewsItem(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """统一资讯实体（归一化后的 DWD 主表）。"""

    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("connector_id", "external_id", name="uq_news_items_connector_external"),
        UniqueConstraint("content_hash", name="uq_news_items_content_hash"),
        Index("ix_news_items_published", "published_at", postgresql_where=NOT_DELETED),
        Index("ix_news_items_type_published", "content_type", "published_at", postgresql_where=NOT_DELETED),
        Index("ix_news_items_importance", "importance", "published_at"),
        Index("ix_news_items_cluster", "cluster_id"),
        Index("ix_news_items_market_scope", "market_scope", postgresql_using="gin"),
        Index("ix_news_items_industries", "industries", postgresql_using="gin"),
        Index("ix_news_items_keywords", "keywords", postgresql_using="gin"),
        Index("ix_news_items_entities", "entities", postgresql_using="gin"),
        # v1 中文检索靠 trgm + 向量；不建 tsv 索引（'simple' 对中文不分词，见 05 §4.8）
        Index("ix_news_items_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index(
            "ix_news_items_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_news_items_enrich", "enrich_status", postgresql_where=text("enrich_status <> 'done'")),
        Index("ix_news_items_simhash", "simhash"),
    )

    raw_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("raw_documents.id", ondelete="SET NULL"), nullable=True
    )
    connector_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_connectors.id"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[ContentType] = mapped_column(
        sa_enum(ContentType, "content_type"), nullable=False
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="zh")

    # 去重：content_hash 精确 + simhash 近似
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    simhash: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # ★ 跨源重复来源：[{connector_id, external_id, source_name, url, raw_document_id}]
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("news_clusters.id", ondelete="SET NULL"), nullable=True
    )
    is_cluster_rep: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    importance: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    sentiment: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)

    market_scope: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    industries: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    entities: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")

    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIM), nullable=True)
    search_tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    raw_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    enrich_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class NewsItemSymbol(UUIDPkMixin, Base):
    """资讯 ↔ 标的（标准码）。"""

    __tablename__ = "news_item_symbols"
    __table_args__ = (
        UniqueConstraint("news_item_id", "ts_code", "relation", name="uq_news_item_symbols"),
        Index("ix_news_item_symbols_ts_code", "ts_code", "created_at"),
        Index("ix_news_item_symbols_news", "news_item_id"),
    )

    news_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False
    )
    ts_code: Mapped[str] = mapped_column(Text, nullable=False)  # 600519.SH / 000001.SZ
    symbol_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="stock")
    # mention / subject / supplier / competitor / customer
    relation: Mapped[str] = mapped_column(Text, nullable=False, server_default="mention")
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, server_default="1.00")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class NewsItemRelation(UUIDPkMixin, Base):
    """资讯之间的关联：followup / context / contradiction / cause / duplicate"""

    __tablename__ = "news_item_relations"
    __table_args__ = (
        UniqueConstraint("from_news_id", "to_news_id", "relation", name="uq_news_item_relations"),
        Index("ix_news_item_relations_to", "to_news_id"),
    )

    from_news_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False
    )
    to_news_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class NewsItemTag(UUIDPkMixin, Base):
    __tablename__ = "news_item_tags"
    __table_args__ = (
        UniqueConstraint("news_item_id", "tag_id", name="uq_news_item_tags"),
        Index("ix_news_item_tags_tag", "tag_id", "created_at"),
    )

    news_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, server_default="1.00")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="model")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


__all__ = [
    "Tag",
    "NewsCluster",
    "NewsItem",
    "NewsItemSymbol",
    "NewsItemRelation",
    "NewsItemTag",
]
