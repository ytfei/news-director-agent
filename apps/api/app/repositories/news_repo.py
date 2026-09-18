"""资讯仓储（DWD）。

★ 跨源去重的关键实现：命中 content_hash 时**不丢弃**，而是追加 source_refs +
duplicate 关联 + 维护簇 source_count（docs/05-database-schema.md §4.9）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import Select, cast, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import NewsDraft
from app.lib.hash import content_hash, hamming_distance, payload_hash, simhash64
from app.models.ingest import RawDocument
from app.models.news import NewsCluster, NewsItem, NewsItemRelation, NewsItemSymbol

SIMHASH_WINDOW = timedelta(days=7)
SIMHASH_MAX_DISTANCE = 3


class NewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_raw(self, connector_id: uuid.UUID, raw) -> uuid.UUID:
        """ODS 幂等写入。"""
        stmt = (
            insert(RawDocument)
            .values(
                connector_id=connector_id,
                external_id=raw.external_id,
                content_type=raw.content_type,
                payload=raw.payload,
                source_ref=raw.source_ref,
                # sha256(canonical_json(payload))，见 05 §4.8
                content_hash=payload_hash(raw.payload),
                fetched_at=raw.fetched_at,
            )
            .on_conflict_do_update(
                constraint="uq_raw_documents_connector_external",
                set_={"payload": raw.payload, "fetched_at": raw.fetched_at},
            )
            .returning(RawDocument.id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def mark_raw_normalized(self, raw_id: uuid.UUID) -> None:
        await self.session.execute(
            text("UPDATE raw_documents SET normalized_at = now() WHERE id = :id"),
            {"id": raw_id},
        )

    async def upsert_draft(
        self,
        draft: NewsDraft,
        connector_id: uuid.UUID,
        raw_document_id: uuid.UUID | None = None,
    ) -> tuple[uuid.UUID, bool]:
        """返回 (news_id, is_new)。

        is_new=False 表示命中已有条目（同源重复或跨源重复），调用方必须走 link_duplicate。
        """
        # 1) 同源同 external_id：直接更新，不算新条目
        if draft.external_id:
            existing = await self.session.execute(
                select(NewsItem.id).where(
                    NewsItem.connector_id == connector_id,
                    NewsItem.external_id == draft.external_id,
                )
            )
            found = existing.scalar_one_or_none()
            if found is not None:
                return found, False

        chash = content_hash(draft.title, draft.content)
        shash = simhash64(f"{draft.title}\n{draft.content or ''}")

        values = {
            "raw_document_id": raw_document_id,
            "connector_id": connector_id,
            "external_id": draft.external_id,
            "content_type": draft.content_type,
            "title": draft.title,
            "summary": draft.summary,
            "content": draft.content,
            "content_length": len(draft.content or ""),
            "author": draft.author,
            "source_name": draft.source_name,
            "url": draft.url,
            "published_at": draft.published_at,
            "lang": draft.lang,
            "content_hash": chash,
            "simhash": shash,
            "market_scope": draft.market_scope,
            "industries": draft.industries,
            "entities": draft.entities,
            "source_refs": [
                {
                    "connector_id": str(connector_id),
                    "external_id": draft.external_id,
                    "source_name": draft.source_name,
                    "url": draft.url,
                }
            ],
            "raw_meta": draft.extra,
        }

        stmt = (
            insert(NewsItem)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_news_items_content_hash",
                # ★ 追加来源，绝不清空或丢弃
                #   asyncpg 不能直接绑 list 给 jsonb，必须序列化后 CAST
                set_={
                    "source_refs": NewsItem.source_refs.op("||")(
                        cast(json.dumps(values["source_refs"]), JSONB)
                    ),
                    "updated_at": func.now(),
                },
            )
            .returning(NewsItem.id, text("(xmax = 0) AS inserted"))
        )
        row = (await self.session.execute(stmt)).one()
        news_id, inserted = row[0], bool(row[1])

        if inserted:
            await self._attach_symbols(news_id, draft)
            await self._assign_cluster(news_id, draft, shash)

        return news_id, inserted

    async def _attach_symbols(self, news_id: uuid.UUID, draft: NewsDraft) -> None:
        for code in draft.symbols:
            stmt = (
                insert(NewsItemSymbol)
                .values(news_item_id=news_id, ts_code=code, relation="mention")
                .on_conflict_do_nothing(constraint="uq_news_item_symbols")
            )
            await self.session.execute(stmt)

    async def _assign_cluster(self, news_id: uuid.UUID, draft: NewsDraft, shash: int) -> None:
        """规则版归簇（M1）：7 天内 simhash 汉明距离 <= 3 视为同一事件。

        ScoutAgent 上线后替换为模型判定；表结构不变。
        """
        candidates = (
            await self.session.execute(
                select(NewsItem.id, NewsItem.simhash, NewsItem.cluster_id).where(
                    NewsItem.published_at >= draft.published_at - SIMHASH_WINDOW,
                    NewsItem.id != news_id,
                    NewsItem.simhash.is_not(None),
                )
            )
        ).all()

        cluster_id: uuid.UUID | None = None
        for cid, other_simhash, existing_cluster in candidates:
            if other_simhash is None:
                continue
            if hamming_distance(int(shash), int(other_simhash)) <= SIMHASH_MAX_DISTANCE:
                cluster_id = existing_cluster
                # 记录 duplicate 关系，供"另有 N 家报道"展示
                if cid != news_id:
                    await self.session.execute(
                        insert(NewsItemRelation)
                        .values(from_news_id=news_id, to_news_id=cid, relation="duplicate")
                        .on_conflict_do_nothing(constraint="uq_news_item_relations")
                    )
                break

        if cluster_id is None:
            cluster = NewsCluster(
                title=draft.title[:200],
                first_seen_at=draft.published_at,
                last_seen_at=draft.published_at,
                member_count=1,
                source_count=1,
            )
            self.session.add(cluster)
            await self.session.flush()
            cluster_id = cluster.id
        else:
            await self.session.execute(
                text(
                    "UPDATE news_clusters SET member_count = member_count + 1, "
                    "last_seen_at = GREATEST(last_seen_at, :ts) WHERE id = :id"
                ),
                {"id": cluster_id, "ts": draft.published_at},
            )

        await self.session.execute(
            text("UPDATE news_items SET cluster_id = :cid WHERE id = :id"),
            {"cid": cluster_id, "id": news_id},
        )
        await self._refresh_source_count(cluster_id)

    async def _refresh_source_count(self, cluster_id: uuid.UUID) -> None:
        await self.session.execute(
            text(
                "UPDATE news_clusters SET source_count = ("
                "  SELECT COUNT(DISTINCT n.source_name) FROM news_items n WHERE n.cluster_id = :id"
                ") WHERE id = :id"
            ),
            {"id": cluster_id},
        )

    async def link_duplicate(
        self, news_id: uuid.UUID, connector_id: uuid.UUID, draft: NewsDraft | None = None
    ) -> None:
        """跨源命中：登记来源并刷新簇的 source_count。"""
        if draft is not None:
            ref = json.dumps(
                [
                    {
                        "connector_id": str(connector_id),
                        "external_id": draft.external_id,
                        "source_name": draft.source_name,
                        "url": draft.url,
                    }
                ]
            )
            await self.session.execute(
                text(
                    "UPDATE news_items SET source_refs = source_refs || CAST(:ref AS jsonb) WHERE id = :id"
                ),
                {"id": news_id, "ref": ref},
            )
        row = (
            await self.session.execute(
                select(NewsItem.cluster_id).where(NewsItem.id == news_id)
            )
        ).scalar_one_or_none()
        if row:
            await self._refresh_source_count(row)

    def list_query(
        self,
        *,
        content_type: str | None = None,
        industry: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Select:
        stmt = select(NewsItem).where(NewsItem.deleted_at.is_(None))
        if content_type:
            stmt = stmt.where(NewsItem.content_type == content_type)
        if industry:
            stmt = stmt.where(NewsItem.industries.contains([industry]))
        if since:
            stmt = stmt.where(NewsItem.published_at >= since)
        if until:
            stmt = stmt.where(NewsItem.published_at <= until)
        return stmt.order_by(NewsItem.published_at.desc())


__all__ = ["NewsRepository"]
