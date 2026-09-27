"""存量回填 + 用分层算法重建事件簇。

    uv run python scripts/backfill_dedupe.py               # 只回填字段
    uv run python scripts/backfill_dedupe.py --recluster   # 回填 + 重建簇
    uv run python scripts/backfill_dedupe.py --days 7      # 只处理最近 7 天

为什么要它：新加的字段（normalized_title / minhash / bucket）对存量是空的，
而事件簇此前是用"simhash 汉明距离 <= 3"建的 —— 实测多源簇只占 0.20%，
等于没聚。用新算法重建才能真正看出效果。

★ --recluster 会重排范围内条目的 cluster_id，只影响资讯的分组，不删任何数据。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.lib.dedupe import (  # noqa: E402
    EventCandidate,
    dedupe_text,
    event_score,
    minhash_bucket,
    minhash_signature,
    normalize_text,
    shingles,
)
from app.models.news import NewsCluster, NewsItem  # noqa: E402
from sqlalchemy import select, text, update  # noqa: E402

OK, WARN = "\033[32m✓\033[0m", "\033[33m!\033[0m"

# 事件聚类时保留的最近簇代表数（滚动窗口，控制 O(N×R) 的规模）
MAX_REPS = 500


def _entity_names(entities) -> list[str]:
    if not entities:
        return []
    out = []
    for e in entities:
        if isinstance(e, dict) and e.get("name"):
            out.append(str(e["name"]))
        elif isinstance(e, str):
            out.append(e)
    return out


async def backfill_fields(session, since: datetime, limit: int) -> int:
    rows = (
        await session.execute(
            select(NewsItem.id, NewsItem.title, NewsItem.content)
            .where(
                NewsItem.published_at >= since,
                NewsItem.minhash.is_(None),
            )
            .order_by(NewsItem.published_at.desc())
            .limit(limit)
        )
    ).all()

    for nid, title, content in rows:
        norm = normalize_text(title)[:500]
        sig = minhash_signature(shingles(dedupe_text(title, content)))
        await session.execute(
            update(NewsItem)
            .where(NewsItem.id == nid)
            .values(
                normalized_title=norm,
                minhash=sig,
                minhash_bucket=minhash_bucket(sig),
            )
        )
    await session.commit()
    return len(rows)


async def recluster(session, since: datetime, limit: int) -> dict:
    """按时间顺序重建：只与"簇代表"比较，代表按时间滚动淘汰。"""
    rows = (
        await session.execute(
            select(
                NewsItem.id,
                NewsItem.title,
                NewsItem.entities,
                NewsItem.keywords,
                NewsItem.published_at,
            )
            .where(NewsItem.published_at >= since)
            .order_by(NewsItem.published_at.asc())
            .limit(limit)
        )
    ).all()

    # 先解绑范围内条目，稍后重新分配
    ids = [r[0] for r in rows]
    if ids:
        await session.execute(
            text("UPDATE news_items SET cluster_id = NULL, is_cluster_rep = false WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        await session.commit()

    reps: list[tuple[object, EventCandidate]] = []  # (cluster_id, 代表特征)
    changed = 0
    new_clusters = 0

    for nid, title, ents, kws, ts in rows:
        cand = EventCandidate.from_item(
            title,
            entities=_entity_names(ents),
            keywords=kws,
            published_at=ts,
        )
        # 淘汰窗口外的代表
        reps = [
            (cid, rc)
            for cid, rc in reps
            if abs((ts - rc.published_at).total_seconds()) / 3600.0
            <= settings.EVENT_WINDOW_HOURS
        ]

        best_cid, best_score = None, 0.0
        for cid, rc in reps:
            score, _ = event_score(cand, rc, window_hours=settings.EVENT_WINDOW_HOURS)
            if score >= settings.EVENT_SCORE_THRESHOLD and score > best_score:
                best_cid, best_score = cid, score

        if best_cid is None:
            cluster = NewsCluster(
                title=(title or "")[:200],
                first_seen_at=ts,
                last_seen_at=ts,
                member_count=1,
                source_count=1,
            )
            session.add(cluster)
            await session.flush()
            best_cid = cluster.id
            is_rep = True
            new_clusters += 1
            reps.append((best_cid, cand))
            if len(reps) > MAX_REPS:
                reps.pop(0)
        else:
            is_rep = False
            await session.execute(
                text(
                    "UPDATE news_clusters SET member_count = member_count + 1, "
                    "last_seen_at = GREATEST(last_seen_at, :ts) WHERE id = :id"
                ),
                {"id": best_cid, "ts": ts},
            )

        await session.execute(
            text("UPDATE news_items SET cluster_id = :cid, is_cluster_rep = :rep WHERE id = :id"),
            {"cid": best_cid, "rep": is_rep, "id": nid},
        )
        changed += 1

    await session.commit()

    # 刷新 source_count
    await session.execute(
        text(
            "UPDATE news_clusters nc SET source_count = ("
            "  SELECT COUNT(DISTINCT n.source_name) FROM news_items n WHERE n.cluster_id = nc.id"
            ") WHERE nc.id IN (SELECT cluster_id FROM news_items WHERE id = ANY(:ids))"
        ),
        {"ids": ids},
    )
    await session.commit()
    return {"processed": changed, "new_clusters": new_clusters}


async def clean_source_refs(session, limit: int) -> int:
    """存量 `source_refs` 去重。

    早期版本是"无脑追加"，同一来源每同步一次就多一条，出现过长度 25 的数组，
    让前端「另有 N 家报道」彻底失真。按 (connector_id, external_id) 去重，保留首条。
    """
    rows = (
        await session.execute(
            select(NewsItem.id, NewsItem.source_refs)
            .where(NewsItem.source_refs.is_not(None))
            .limit(limit)
        )
    ).all()

    changed = 0
    for nid, refs in rows:
        if not isinstance(refs, list) or len(refs) < 2:
            continue
        seen: set[tuple[str, str]] = set()
        uniq: list = []
        for r in refs:
            if isinstance(r, dict):
                # ★ 按**来源名**去重，而不是 (connector_id, external_id)：
                #   库里存在多个 tushare.news 实例（connector_id 不同）拉同一条新闻，
                #   按 connector 去重会让「另有 N 家报道」虚高到 77。
                #   产品的语义是"多少家媒体报道"，所以媒体名才是正确的判重键。
                # 无媒体名的历史记录无法区分是谁报的，全部合并成一条（否则虚高到 39）
                name = str(r.get("source_name") or "").strip()
                key = ("src", name) if name else ("unknown",)
            else:
                key = ("raw", str(r))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(r)
        if len(uniq) != len(refs):
            await session.execute(
                text("UPDATE news_items SET source_refs = CAST(:refs AS jsonb) WHERE id = :id"),
                {"id": nid, "refs": json.dumps(uniq)},
            )
            changed += 1
    await session.commit()
    return changed


async def stats(session) -> None:
    total = (
        await session.execute(text("select count(*) from news_clusters"))
    ).scalar_one()
    multi = (
        await session.execute(text("select count(*) from news_clusters where source_count >= 2"))
    ).scalar_one()
    nonempty = (
        await session.execute(
            text("select count(*) from news_clusters where member_count >= 2")
        )
    ).scalar_one()
    print(f"  · 簇总数 {total} · 多源簇 {multi} · 多条簇 {nonempty}")
    if total:
        print(f"  · 多源簇占比 {multi / total:.2%}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recluster", action="store_true", help="重建事件簇")
    ap.add_argument("--clean-refs", action="store_true", help="存量 source_refs 去重")
    ap.add_argument("--days", type=int, default=7, help="处理最近 N 天")
    ap.add_argument("--limit", type=int, default=5000)
    args = ap.parse_args()

    since = datetime.now() - timedelta(days=args.days)
    print(f"\n\033[1m去重字段回填\033[0m  范围: 最近 {args.days} 天\n")

    async with SessionLocal() as session:
        n = await backfill_fields(session, since, args.limit)
        print(f"  {OK} 回填 {n} 条")

        await stats(session)

        if args.clean_refs:
            n = await clean_source_refs(session, args.limit)
            print(f"  {OK} source_refs 去重 {n} 条")

        if args.recluster:
            print(f"\n\033[1m重建事件簇\033[0m（阈值 {settings.EVENT_SCORE_THRESHOLD}，"
                  f"窗口 {settings.EVENT_WINDOW_HOURS}h）")
            r = await recluster(session, since, args.limit)
            print(f"  {OK} 处理 {r['processed']} 条，新建簇 {r['new_clusters']} 个")
            await stats(session)

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
