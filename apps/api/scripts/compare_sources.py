"""多来源对比测试：tushare 快讯各渠道的数据量与重叠情况。

    uv run python scripts/compare_sources.py
    uv run python scripts/compare_sources.py --hours 24 --srcs sina,wallstreetcn,eastmoney,cls

**只读取、不落库**，用于回答三个问题：
1. 每个源在同一时间窗内到底有多少条？字段完整性如何？
2. 不同源之间有多少是**同一条新闻**（跨源转载）？—— 这是"多源交叉验证"的原料
3. 我们的 MinHash 能否把它们认出来（重叠率）

为什么需要它：加了新来源后，如果只看到"同步了 N 条"，无法判断这些来源是真的互补，
还是互相重复。这个脚本把"互补 vs 重复"量化出来。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.connectors.spec import DEFAULT_TZ  # noqa: E402
from app.connectors.tushare.flash import (  # noqa: E402
    TushareFlashConnector,
)
from app.connectors.tushare.specs import SRC_LABELS, src_label  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.lib.dedupe import jaccard_text  # noqa: E402

# 判定"同一条新闻"的标题重合阈值
SAME_NEWS_THRESHOLD = 0.60
# 单段窗口：1500 条上限下按小时切
SEG_HOURS = 1


async def fetch_src(conn: TushareFlashConnector, src: str, start: datetime, end: datetime):
    """按小时分段拉取，合并结果。"""
    rows: list[dict] = []
    cursor = start
    while cursor < end:
        seg_end = min(cursor + timedelta(hours=SEG_HOURS), end)
        try:
            rows.extend(await conn._query_flash(src, cursor, seg_end))
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)[:160]
        cursor = seg_end
    return rows, None


def summarize(src: str, rows: list[dict]) -> dict:
    def non_empty(field: str) -> float:
        if not rows:
            return 0.0
        n = sum(1 for r in rows if str(r.get(field) or "").strip())
        return n / len(rows)

    times = [str(r.get("datetime") or "") for r in rows if r.get("datetime")]
    titles = {str(r.get("title") or "").strip() for r in rows if r.get("title")}
    contents = [str(r.get("content") or r.get("text") or "") for r in rows]

    return {
        "src": src,
        "label": src_label(src),
        "rows": len(rows),
        "unique_titles": len(titles),
        "dup_rate": (1 - len(titles) / len(rows)) if rows else 0.0,
        "title_fill": non_empty("title"),
        "content_fill": non_empty("content") or non_empty("text"),
        "time_fill": non_empty("datetime"),
        "channels_fill": non_empty("channels"),
        "avg_title_len": sum(len(t) for t in titles) / len(titles) if titles else 0,
        "avg_content_len": sum(len(c) for c in contents) / len(contents) if contents else 0,
        "time_range": f"{min(times)[:16]} ~ {max(times)[:16]}" if times else "—",
        "samples": [t for t in list(titles)[:2]],
    }


def overlap_matrix(data: dict[str, list[dict]]) -> list[tuple[str, str, int]]:
    """两两源之间的"同一条新闻"配对数。"""
    pairs: list[tuple[str, str, int]] = []
    keys = [k for k in data if data[k]]
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            ta = [str(r.get("title") or "") for r in data[a]]
            tb = [str(r.get("title") or "") for r in data[b]]
            if not ta or not tb:
                pairs.append((a, b, 0))
                continue
            # 控制计算量：任一侧超过 800 条时截断
            ta, tb = ta[:800], tb[:800]
            hits = 0
            for x in ta:
                for y in tb:
                    if jaccard_text(x, y) >= SAME_NEWS_THRESHOLD:
                        hits += 1
                        break
            pairs.append((a, b, hits))
    return pairs


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=12, help="探测最近 N 小时")
    ap.add_argument("--srcs", default="", help="逗号分隔；留空则用全部已知来源")
    ap.add_argument("--threshold", type=float, default=SAME_NEWS_THRESHOLD)
    args = ap.parse_args()

    srcs = [s.strip() for s in args.srcs.split(",") if s.strip()] or list(SRC_LABELS)
    zone = ZoneInfo(DEFAULT_TZ)
    end = datetime.now(tz=zone)
    start = end - timedelta(hours=args.hours)

    print("\n\033[1mtushare 快讯 · 多来源对比\033[0m")
    print(f"  窗口：{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}（{args.hours}h）\n")

    conn = TushareFlashConnector(
        config={"srcs": srcs}, credentials={"token": settings.TUSHARE_TOKEN}
    )

    data: dict[str, list[dict]] = {}
    errors: dict[str, str] = {}
    for src in srcs:
        rows, err = await fetch_src(conn, src, start, end)
        if err:
            errors[src] = err
            data[src] = []
        else:
            data[src] = rows or []

    print(f"{'来源':<14}{'条数':>6}{'唯一':>6}{'标题%':>7}{'正文%':>7}{'时间%':>7}{'均长':>6}  时间范围")
    print("-" * 92)
    for src in srcs:
        s = summarize(src, data[src])
        if errors.get(src):
            print(f"{s['label']:<14}{'ERR':>6}  {errors[src][:60]}")
            continue
        print(
            f"{s['label']:<14}{s['rows']:>6}{s['unique_titles']:>6}"
            f"{s['title_fill']:>7.0%}{s['content_fill']:>7.0%}{s['time_fill']:>7.0%}"
            f"{s['avg_content_len']:>6.0f}  {s['time_range']}"
        )

    print("\n\033[1m跨源重叠（同一条新闻被几个源都报了）\033[0m")
    print("  " + "\033[2m判定：标题 Jaccard >= " + f"{args.threshold}\033[0m")
    pairs = overlap_matrix(data)
    for a, b, hits in pairs:
        if hits:
            smaller = min(len(data[a]), len(data[b]))
            share = hits / smaller if smaller else 0
            print(
                f"  {src_label(a):<8} × {src_label(b):<8} {hits:>4} 条共同 "
                f"（占较少一方 {share:.0%}）"
            )
    if not any(h for _, _, h in pairs):
        print("  （无跨源重叠：这些源在当前窗口报道的事件不重合）")

    total = sum(len(v) for v in data.values())
    print(f"\n  合计 {total} 条（含跨源重复）")
    print("  \033[2m提示：重叠越高 → 越依赖 L3 转载合并；重叠越低 → 来源越互补\033[0m\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
