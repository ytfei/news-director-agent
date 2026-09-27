"""tushare 新闻快讯连接器（doc_id=143）。

## 与旧实现的关键差异（旧实现的参数是错的）

| 项 | 官方规格 | 修正后 |
| --- | --- | --- |
| `src` | **必选**，9 个来源之一 | 实例可配多个来源，逐个循环拉取 |
| 时间格式 | `2018-11-20 09:00:00`（`%Y-%m-%d %H:%M:%S`） | 按此格式传参 |
| 单次上限 | 1500 条 | 触顶自动二分细分窗口，避免静默丢数据 |
| 渠道身份 | 返回里**没有 src** | 由连接器注入 `$channel`，来源中文名从 `SRC_LABELS` 取 |

## 多来源的进度管理

每个来源有**独立游标**（存在 `SyncCursor.payload["srcs"]`），
所以某个来源失败不会把其他来源的进度一起拖回去 —— 这是"一个实例配多个来源"
必须付出的代价，也是必须做对的地方：共用游标会让一个来源的失败造成其他来源丢数据。

## 未做的部分

历史回补（6 年+）需要按小时切窗，约 5 万次调用，属于独立任务，本期不碰。
`MAX_LOOKBACK` 限制单次拉取跨度，防止误配置把配额一次烧穿。
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog

from app.connectors.base import (
    ConfigField,
    ConnectorCapability,
    NormalizedItem,
    Provenance,
    RawItem,
    SyncCursor,
)
from app.connectors.registry import register
from app.connectors.spec import DEFAULT_TZ, parse_time
from app.connectors.tushare.base import TUSHARE_DATETIME_FMT, TushareBase, iter_windows
from app.connectors.tushare.specs import NEWS_MAX_ROWS, NEWS_SPEC, SRC_LABELS, src_label
from app.models.enums import ContentType

log = structlog.get_logger()

API = "news"

# 正文里"【标题】"这类前缀（东方财富常见），提标题时先剥掉
_BRACKET_PREFIX = re.compile(r"^\s*【[^】]{1,40}】\s*")
_SENTENCE_ENDS = ("。", "！", "？", "\n", "；")
TITLE_FALLBACK_LIMIT = 80


def ensure_tz(dt: datetime) -> datetime:
    """★ 统一为带时区。

    调用方（sync_service）传的窗口可能是 naive，而来源游标（`parse_time`）是 aware，
    两者一比较就 `TypeError: can't compare offset-naive and offset-aware datetimes`。
    在连接器入口统一，而不是要求每个调用方都做对。
    """
    return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo(DEFAULT_TZ))


def title_from_content(content: str | None, limit: int = TITLE_FALLBACK_LIMIT) -> str:
    """★ 部分来源（新浪财经、华尔街见闻）的 `title` 恒为 None，正文就是一句话新闻。

    实测 12 小时窗口：新浪 160 条标题填充率 **0%**、华尔街见闻 72%、金融界 63%。
    若不兜底会有两个后果：
    1. `external_id` = [channel, datetime, title] 退化为 [channel, datetime, ""]，
       同一秒的多条快讯**幂等键撞车**，互相覆盖；
    2. `news_items.title` 是 NOT NULL，只能落到无意义的兜底值。
    """
    text = (content or "").strip()
    if not text:
        return ""
    stripped = _BRACKET_PREFIX.sub("", text).strip()
    if stripped:
        text = stripped
    for sep in _SENTENCE_ENDS:
        idx = text.find(sep)
        if idx > 0:
            return text[: idx + 1][:limit]
    return text[:limit]


FLASH_WINDOW = timedelta(hours=1)  # 单段窗口：1500 条上限下，一小时足够安全
MAX_SPLIT_DEPTH = 4  # 触顶后最多细分 4 层（1h → 3.75min）
MAX_LOOKBACK = timedelta(days=7)  # 单次拉取跨度上限，防止配额被一次烧穿
PROBE_HOURS = 3  # 来源探测窗口：够近才有数据，够短才省配额


@register
class TushareFlashConnector(TushareBase):
    key = "tushare.flash"
    display_name = "Tushare 新闻快讯"
    capability = ConnectorCapability(
        content_types=["flash"],
        supports_incremental=True,
        supports_backfill=True,
        rate_limit_per_min=200,
        requires_credentials=True,
        emits_metrics=False,
        config_schema=[
            ConfigField(
                key="srcs",
                label="新闻来源",
                type="multiselect",
                required=True,
                options=[{"value": k, "label": v} for k, v in SRC_LABELS.items()],
                # 三个主力源（新浪 / 华尔街见闻 / 东方财富）+ 财联社。
                # 实测 12h 窗口条数：新浪 160 · 东方财富 91 · 金融界 49 · 同花顺 48 ·
                # 华尔街见闻 46 · 第一财经 34 · 财联社 6 · 云财经/凤凰 0。
                default=["sina", "wallstreetcn", "eastmoney", "cls"],
                help="可多选。每个来源独立限流、独立续拉；某个来源失败不影响其他来源。",
            ),
        ],
    )

    # ---------------- 配置 ----------------

    @property
    def _configured_srcs(self) -> list[str]:
        """原始配置值归一为列表（兼容单个 `src` 的旧写法与字符串写法）。"""
        raw = self.config.get("srcs")
        if isinstance(raw, str):
            raw = [raw]
        if not raw:
            single = self.config.get("src")
            raw = [single] if single else []
        return list(dict.fromkeys(raw or []))

    @property
    def srcs(self) -> list[str]:
        """启用的来源列表（已过滤掉上游不认的值）。

        ★ 未配置时返回空，由 `validate()` 给出人话提示 —— 不做"没配就全都要"的兜底：
        9 个来源全量拉取会白烧配额，而且用户根本不知道自己在拉什么。
        """
        return [s for s in self._configured_srcs if s in SRC_LABELS]

    @property
    def unknown_srcs(self) -> list[str]:
        """配置里写了但 tushare 不认的来源（给出提示而不是静默忽略）。"""
        return [s for s in self._configured_srcs if s not in SRC_LABELS]

    # ---------------- 游标（按来源独立） ----------------

    def _cursor_of(self, cursor: SyncCursor, src: str) -> datetime | None:
        """读取单个来源的进度。存的是 ISO 字符串，读回来必须仍是带时区的。"""
        entry = (cursor.payload.get("srcs") or {}).get(src) or {}
        return parse_time(entry.get("last_published_at"), None, DEFAULT_TZ)

    def _set_cursor(self, cursor: SyncCursor, src: str, ts: datetime) -> None:
        """推进单个来源的进度（其他来源不受影响）。"""
        payload = dict(cursor.payload)
        srcs = dict(payload.get("srcs") or {})
        srcs[src] = {"last_published_at": ts.isoformat()}
        payload["srcs"] = srcs
        cursor.payload = payload

    # ---------------- 查询 ----------------

    async def _query_flash(
        self, src: str, start: datetime, end: datetime
    ) -> list[dict]:
        """按官方规格调 `news`：src 必传、时间用 `%Y-%m-%d %H:%M:%S`。"""
        return await self._query(
            API,
            channel=src,
            src=src,
            start_date=start.strftime(TUSHARE_DATETIME_FMT),
            end_date=end.strftime(TUSHARE_DATETIME_FMT),
        )

    # ---------------- 探测 ----------------

    async def probe_srcs(self, hours: int = PROBE_HOURS) -> dict[str, dict]:
        """逐来源探测：**有数据 / 无权限（抛异常）/ 区间为空（0 行不报错）**。

        ★ 只探配置里启用的来源。旧的 `probe_endpoints()` 用错误参数探测，
        得出的"news 无权限"是假阴性 —— 这里用修正后的参数重探，才能分开
        "权限不足"与"我们的参数写错了"这两种完全不同的故障。

        注意：即使参数正确，"近 N 小时无数据"也不等于无权限（可能是非交易时段），
        所以 reason 文案必须把这两种可能都写出来，不能替用户下结论。
        """
        zone = ZoneInfo(DEFAULT_TZ)
        end = datetime.now(tz=zone)
        start = end - timedelta(hours=hours)

        results: dict[str, dict] = {}
        for src in self.srcs:
            label = src_label(src)
            try:
                rows = await self._query_flash(src, start, end)
                results[src] = {
                    "ok": bool(rows),
                    "rows": len(rows),
                    "label": label,
                    "reason": ""
                    if rows
                    else f"近 {hours} 小时返回 0 条：可能是该来源当前无更新，或 token 未开通 news 接口权限",
                }
            except Exception as exc:  # noqa: BLE001 单个来源失败不影响其他来源
                results[src] = {
                    "ok": False,
                    "rows": 0,
                    "label": label,
                    "reason": str(exc)[:300],
                }
        self.probe_results = results
        self.available_endpoints = [s for s, r in results.items() if r["ok"]]
        return results

    def unavailable_reason(self) -> str:
        """供 UI 展示"哪个来源不可用、为什么"。"""
        parts = [
            f"{r.get('label') or s}（{str(r.get('reason') or '')[:60]}）"
            for s, r in self.probe_results.items()
            if not r["ok"]
        ]
        return "；".join(parts)

    def empty_reason(self) -> str | None:
        """同步 0 条时的人话原因（同步编排会用它替代通用文案）。"""
        if not self.srcs:
            return "未配置新闻来源：请在数据源配置里至少选择一个来源（如 财联社 / 新浪财经）"
        if not self.probe_results:
            return "未做来源探测，无法区分「来源无权限」与「区间内无数据」"
        ok = [s for s, r in self.probe_results.items() if r["ok"]]
        if not ok:
            return f"配置的 {len(self.probe_results)} 个来源近 {PROBE_HOURS} 小时均无数据：{self.unavailable_reason()}"
        return "所选来源在本次时间区间内无新快讯（快讯集中在交易时段，深夜/凌晨通常为空）"

    # ---------------- 校验 ----------------

    async def validate(self) -> tuple[bool, str]:
        """凭据自检 + 逐来源探测（不等问题发生时才报错）。"""
        if not self.token:
            return False, "缺少 Tushare token：请在「数据源管理」中填写你自己的 token"
        if not self.srcs:
            hint = f"（配置里有无法识别的来源：{', '.join(self.unknown_srcs)}）" if self.unknown_srcs else ""
            return False, f"未配置新闻来源：请至少选择一个来源，可选 {', '.join(SRC_LABELS)}{hint}"

        try:
            await self._query("trade_cal", exchange="SSE", limit=1)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "积分" in message or "permission" in message.lower():
                return False, f"Token 有效但接口权限不足：{message}"
            return False, f"Tushare 连通性校验失败：{message}"

        results = await self.probe_srcs()
        available = [s for s, r in results.items() if r["ok"]]
        if not available:
            return (
                False,
                f"Token 可用，但配置的 {len(results)} 个来源近 {PROBE_HOURS} 小时都没有数据："
                f"{self.unavailable_reason()}",
            )

        labels = ", ".join(src_label(s) or s for s in available)
        message = f"Tushare 快讯连接正常，近 {PROBE_HOURS} 小时有数据的来源：{labels}"
        if len(available) < len(results):
            message += f"；暂无数据：{self.unavailable_reason()}"
        if self.unknown_srcs:
            message += f"；已忽略无法识别的来源：{', '.join(self.unknown_srcs)}"
        return True, message

    # ---------------- 拉取 ----------------

    async def fetch(
        self, cursor: SyncCursor, window: tuple[datetime, datetime]
    ) -> AsyncIterator[RawItem]:
        if not self.token or not self.srcs:
            return

        start, end = ensure_tz(window[0]), ensure_tz(window[1])
        floor = end - MAX_LOOKBACK

        for src in self.srcs:
            # ★ 用来源自己的游标，而不是连接器整体水位：
            #   某个来源上次失败时进度落后，用整体水位会让它永久丢一段数据
            src_start = self._cursor_of(cursor, src) or start
            if src_start < floor:
                src_start = floor
            if src_start >= end:
                continue

            log.info("flash.fetch.src", connector_key=self.key, src=src,
                     start=src_start.isoformat(), end=end.isoformat())

            for seg_start, seg_end in iter_windows(src_start, end, FLASH_WINDOW):
                try:
                    async for item in self._fetch_segment(src, seg_start, seg_end, depth=0):
                        yield item
                except Exception as exc:  # noqa: BLE001 单段失败不中断整体
                    self.failed_segments.append(
                        {
                            "api": API,
                            "src": src,
                            "start": seg_start.isoformat(),
                            "end": seg_end.isoformat(),
                            "error": str(exc)[:500],
                        }
                    )
                    # 失败段不推进游标 → 下次从这一段重来
                    continue
                # 段成功后才推进该来源的游标（至少一次语义，宁可重拉不丢数据）
                self._set_cursor(cursor, src, seg_end)

    async def _fetch_segment(
        self, src: str, seg_start: datetime, seg_end: datetime, depth: int
    ) -> AsyncIterator[RawItem]:
        """拉一个时间段的快讯；触顶（1500）则二分细分，避免静默丢数据。"""
        rows = await self._query_flash(src, seg_start, seg_end)

        span = seg_end - seg_start
        if len(rows) >= NEWS_MAX_ROWS and depth < MAX_SPLIT_DEPTH and span > timedelta(minutes=1):
            mid = seg_start + span / 2
            log.warning(
                "flash.segment.truncated",
                connector_key=self.key,
                src=src,
                start=seg_start.isoformat(),
                end=seg_end.isoformat(),
                rows=len(rows),
                depth=depth,
                action="split",
            )
            async for item in self._fetch_segment(src, seg_start, mid, depth + 1):
                yield item
            async for item in self._fetch_segment(src, mid, seg_end, depth + 1):
                yield item
            return

        if len(rows) >= NEWS_MAX_ROWS:
            # 细分到极限仍触顶：明确记账，而不是当作正常结果
            self.failed_segments.append(
                {
                    "api": API,
                    "src": src,
                    "start": seg_start.isoformat(),
                    "end": seg_end.isoformat(),
                    "error": f"窗口内达到单次上限 {NEWS_MAX_ROWS} 条且已细分到最小粒度，可能丢数据",
                }
            )

        for row in rows:
            # ★ 先把缺失的 title 从正文补出来，再算幂等键：
            #   否则同一秒的多条新浪快讯会因为 title 为空而撞键互相覆盖
            row = dict(row)
            if not str(row.get("title") or "").strip():
                row["title"] = title_from_content(
                    row.get("content") or row.get("text")
                )
            # 幂等键与 normalize 用同一套规则，保证 ODS 与 DWD 对"同一条"的判断一致
            external_id = NEWS_SPEC.build_external_id(row, {"channel": src})
            yield RawItem(
                external_id=external_id,
                payload=row,
                fetched_at=datetime.now(tz=ZoneInfo(DEFAULT_TZ)),
                source_ref=None,  # doc 143 不返回 url
                content_type=ContentType.flash,
                channel=src,
            )

    # ---------------- 归一化 ----------------

    def normalize(self, raw: RawItem) -> NormalizedItem:
        """纯函数：映射逻辑全在 NEWS_SPEC 里，这里只补来源溯源。"""
        src = raw.channel
        ctx = {
            "channel": src,
            "channel_label": src_label(src),
            "fetched_at": raw.fetched_at,
        }
        item = NEWS_SPEC.normalize(
            raw.payload,
            ctx=ctx,
            external_id=raw.external_id,
            provenance=Provenance(
                connector_key=self.key,
                api=API,
                channel=src,
                channel_label=src_label(src),
                fetched_at=raw.fetched_at,
            ),
        )
        return item


__all__ = [
    "FLASH_WINDOW",
    "MAX_LOOKBACK",
    "PROBE_HOURS",
    "TushareFlashConnector",
]
