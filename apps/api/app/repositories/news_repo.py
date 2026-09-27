"""资讯仓储（DWD）。

★ 跨源去重的关键实现：命中 content_hash 时**不丢弃**，而是追加 source_refs +
duplicate 关联 + 维护簇 source_count（docs/05-database-schema.md §4.9）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import Select, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import NormalizedItem
from app.core.config import settings
from app.lib.dedupe import (
    EventCandidate,
    dedupe_text,
    event_score,
    jaccard_from_signatures,
    minhash_bucket,
    minhash_signature,
    normalize_text,
    shingles,
)
from app.lib.hash import content_hash, payload_hash, simhash64
from app.models.ingest import RawDocument
from app.models.news import NewsCluster, NewsItem, NewsItemSymbol

SIMHASH_WINDOW = timedelta(days=7)
SIMHASH_MAX_DISTANCE = 3


def _entity_names(entities) -> list[str]:
    """entities 是 [{name,type,code}]，也可能直接是字符串列表。"""
    if not entities:
        return []
    out: list[str] = []
    for e in entities:
        if isinstance(e, dict):
            if e.get("name"):
                out.append(str(e["name"]))
        elif isinstance(e, str):
            out.append(e)
    return out


def _source_ref(connector_id: uuid.UUID, draft: NormalizedItem) -> dict:
    """跨源登记里的一条来源。带 channel 才能回答"这条是被哪家先报的"。"""
    ref = {
        "connector_id": str(connector_id),
        "external_id": draft.external_id,
        "source_name": draft.source_name,
        "url": draft.url,
    }
    if draft.provenance.channel:
        ref["channel"] = draft.provenance.channel
    return ref


def _raw_meta(draft: NormalizedItem) -> dict:
    """`news_items.raw_meta` 是既有 jsonb 列（本期不新增列）。

    把两个扩展通道里"值得留住"的部分收进来：
    - attributes：渠道元信息（如 tushare 的 channels 分类）
    - provenance：这一条从哪个连接器/接口/渠道来
    """
    meta = dict(draft.extra)
    if draft.attributes:
        meta["attributes"] = draft.attributes
    provenance = draft.provenance.model_dump(mode="json", exclude_none=True)
    if provenance:
        meta["provenance"] = provenance
    return meta


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
        draft: NormalizedItem,
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

        # ★ title 可空：数值型条目没有标题，统一走 display_title 兜底（列是 NOT NULL）
        title = draft.display_title
        # content_hash 保持原语义（完全相同才命中），改写稿交给 L3 的 MinHash，
        # 这样存量 15982 条的 hash 不会失配。
        chash = content_hash(title, draft.content)
        shash = simhash64(f"{title}\n{draft.content or ''}")
        # L3 转载判定：3-gram shingle 的 MinHash，对渠道改写鲁棒
        sig = minhash_signature(shingles(dedupe_text(title, draft.content)))
        bucket = minhash_bucket(sig)

        # ---- L3 转载：命中则不新增条目，只登记来源 ----
        dup_of = await self._find_duplicate(draft, sig, bucket)
        if dup_of is not None:
            await self._register_duplicate(dup_of, connector_id, draft)
            return dup_of, False

        values = {
            "raw_document_id": raw_document_id,
            "connector_id": connector_id,
            "external_id": draft.external_id,
            "content_type": draft.content_type,
            "title": title,
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
            "normalized_title": normalize_text(title)[:500],
            "minhash": sig,
            "minhash_bucket": bucket,
            "market_scope": draft.market_scope,
            "industries": draft.industries,
            "entities": draft.entities,
            "source_refs": [_source_ref(connector_id, draft)],
            "raw_meta": _raw_meta(draft),
        }

        stmt = (
            insert(NewsItem)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_news_items_content_hash",
                # 命中已有条目时**不在这里追加来源**：追加必须幂等（见 _append_source_ref），
                # 而 ON CONFLICT 的 SET 里做"不存在才追加"既难写又难测。
                set_={"updated_at": func.now()},
            )
            .returning(NewsItem.id, text("(xmax = 0) AS inserted"))
        )
        row = (await self.session.execute(stmt)).one()
        news_id, inserted = row[0], bool(row[1])

        if not inserted:
            # ★ 命中已有条目（完全相同的稿子）：幂等登记来源，绝不清空或丢弃
            await self._append_source_ref(news_id, _source_ref(connector_id, draft))

        if inserted:
            await self._attach_symbols(news_id, draft)
            await self._assign_cluster(news_id, draft)

        return news_id, inserted

    async def _attach_symbols(self, news_id: uuid.UUID, draft: NormalizedItem) -> None:
        for code in draft.symbols:
            stmt = (
                insert(NewsItemSymbol)
                .values(news_item_id=news_id, ts_code=code, relation="mention")
                .on_conflict_do_nothing(constraint="uq_news_item_symbols")
            )
            await self.session.execute(stmt)

    async def _find_duplicate(
        self, draft: NormalizedItem, sig: bytes, bucket: int
    ) -> uuid.UUID | None:
        """L3 转载判定：同 bucket 内，MinHash Jaccard ≥ 阈值视为"同一篇的不同转载"。

        精确率优先 —— 误合并会丢掉一条独立报道。
        bucket 是简化 LSH：只比同桶候选，避免和窗口内全部条目算 Jaccard。
        """
        since = draft.published_at - timedelta(days=settings.DEDUPE_WINDOW_DAYS)
        rows = (
            await self.session.execute(
                select(NewsItem.id, NewsItem.minhash)
                .where(
                    NewsItem.minhash_bucket == bucket,
                    NewsItem.published_at >= since,
                    NewsItem.deleted_at.is_(None),
                )
                .limit(settings.DEDUPE_CANDIDATE_LIMIT)
            )
        ).all()

        best_id: uuid.UUID | None = None
        best_score = 0.0
        for rid, rminhash in rows:
            if not rminhash:
                continue
            score = jaccard_from_signatures(sig, bytes(rminhash))
            if score >= settings.DUP_JACCARD_THRESHOLD and score > best_score:
                best_id, best_score = rid, score
        return best_id

    async def _append_source_ref(self, news_id: uuid.UUID, ref: dict) -> None:
        """幂等登记来源。

        ★ 直接 `source_refs || 新来源` 是不幂等的：同一个来源每次同步都会再追加一条，
        实测出现过 `source_refs` 长度 25 的条目，让「另有 N 家报道」彻底失真。
        这里按 (connector_id, external_id) 判重 —— 相同来源只登记一次。
        """
        await self.session.execute(
            text(
                "UPDATE news_items SET source_refs = source_refs || CAST(:ref AS jsonb) "
                "WHERE id = :id AND NOT EXISTS ("
                "  SELECT 1 FROM jsonb_array_elements(source_refs) x "
                "  WHERE x->>'connector_id' = :cid AND x->>'external_id' = :eid"
                ")"
            ),
            {
                "id": news_id,
                "ref": json.dumps([ref]),
                "cid": str(ref.get("connector_id") or ""),
                "eid": str(ref.get("external_id") or ""),
            },
        )

    async def _register_duplicate(
        self, existing_id: uuid.UUID, connector_id: uuid.UUID, draft: NormalizedItem
    ) -> None:
        """转载：不新增条目，只登记来源 + 累加 duplicate_count。"""
        await self._append_source_ref(existing_id, _source_ref(connector_id, draft))
        cid = (
            await self.session.execute(
                select(NewsItem.cluster_id).where(NewsItem.id == existing_id)
            )
        ).scalar_one_or_none()
        if cid:
            await self.session.execute(
                text("UPDATE news_clusters SET duplicate_count = duplicate_count + 1 WHERE id = :id"),
                {"id": cid},
            )

    async def _assign_cluster(self, news_id: uuid.UUID, draft: NormalizedItem) -> None:
        """L4 事件聚类：同事件的不同角度报道 → 同一簇，**各条都保留**。

        与 L3 的区别：L3 是"同一篇稿子的转载"（合并展示，只留一条）；
        L4 是"同一事件的不同报道"（都要留着 —— 信息互补，正是交叉验证的素材）。

        只与**簇代表**比较而不是簇内所有条目：这是性能关键，
        否则每次入库都要和窗口内全部条目算分。
        """
        since = draft.published_at - timedelta(hours=settings.EVENT_WINDOW_HOURS)
        reps = (
            await self.session.execute(
                select(
                    NewsItem.id,
                    NewsItem.cluster_id,
                    NewsItem.title,
                    NewsItem.entities,
                    NewsItem.keywords,
                    NewsItem.published_at,
                    NewsItem.embedding,
                )
                .where(
                    NewsItem.is_cluster_rep.is_(True),
                    NewsItem.published_at >= since,
                    NewsItem.id != news_id,
                    NewsItem.cluster_id.is_not(None),
                    NewsItem.deleted_at.is_(None),
                )
                .limit(1000)
            )
        ).all()

        # 不同 connector 的 NormalizedItem 字段可能不齐（如数值事实没有 keywords），
        # 一律用 getattr 安全取，避免"接了新数据源就崩"
        cand = EventCandidate.from_item(
            draft.display_title,
            entities=_entity_names(getattr(draft, "entities", None)),
            keywords=getattr(draft, "keywords", None),
            published_at=draft.published_at,
        )

        cluster_id: uuid.UUID | None = None
        best_score = 0.0
        for _rid, cid, rtitle, ents, kws, ts, emb in reps:
            other = EventCandidate.from_item(
                rtitle,
                entities=_entity_names(ents),
                keywords=kws,
                published_at=ts,
                embedding=emb,
            )
            score, _parts = event_score(
                cand, other, window_hours=settings.EVENT_WINDOW_HOURS
            )
            if score >= settings.EVENT_SCORE_THRESHOLD and score > best_score:
                cluster_id, best_score = cid, score

        is_rep = False
        if cluster_id is None:
            cluster = NewsCluster(
                title=draft.display_title[:200],
                first_seen_at=draft.published_at,
                last_seen_at=draft.published_at,
                member_count=1,
                source_count=1,
            )
            self.session.add(cluster)
            await self.session.flush()
            cluster_id = cluster.id
            is_rep = True
        else:
            await self.session.execute(
                text(
                    "UPDATE news_clusters SET member_count = member_count + 1, "
                    "last_seen_at = GREATEST(last_seen_at, :ts) WHERE id = :id"
                ),
                {"id": cluster_id, "ts": draft.published_at},
            )

        await self.session.execute(
            text(
                "UPDATE news_items SET cluster_id = :cid, is_cluster_rep = :rep WHERE id = :id"
            ),
            {"cid": cluster_id, "rep": is_rep, "id": news_id},
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
        self, news_id: uuid.UUID, connector_id: uuid.UUID, draft: NormalizedItem | None = None
    ) -> None:
        """跨源命中：登记来源并刷新簇的 source_count。"""
        if draft is not None:
            await self._append_source_ref(news_id, _source_ref(connector_id, draft))
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
