"""TushareConnector —— 第一个真实数据源实现。

覆盖 tushare 资讯类接口（见 docs/04-architecture.md §4.4）：
news(快讯) / major_news(长文) / cctv_news(新闻联播) / anns_d(公告) /
npr(政策) / research_report(研报)

要点：
- 按粒度切分时间窗，避免长区间一次性拉取
- token bucket 限流 + 429 指数退避（仅瞬时错误重试）
- 分段失败不中断整体：记录到 self.failed_segments，同步结束时标记 partial
- normalize() 是纯函数，无 IO
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

from app.connectors.base import (
    ConnectorCapability,
    DataSourceConnector,
    NewsDraft,
    RawItem,
    SyncCursor,
)
from app.connectors.registry import register
from app.core.config import settings
from app.lib.hash import payload_hash

# (接口名, 拉取粒度, content_type)
ENDPOINTS: list[tuple[str, str, str]] = [
    ("news", "hour", "flash"),
    ("major_news", "day", "article"),
    ("cctv_news", "day", "article"),
    ("anns_d", "day", "announcement"),
    ("npr", "day", "policy"),
    ("research_report", "day", "research_report"),
]

DATETIME_FMT = "%Y%m%d %H%M%S"
DATE_FMT = "%Y%m%d"


def to_standard_code(code: str | None) -> str | None:
    """tushare 的 6 位代码 → 标准码 600519.SH / 000001.SZ / 430047.BJ"""
    if not code:
        return None
    code = code.strip().upper()
    if "." in code:
        return code
    if len(code) != 6 or not code.isdigit():
        return None
    if code[0] == "6":
        return f"{code}.SH"
    if code[0] in {"0", "3"}:
        return f"{code}.SZ"
    if code[0] in {"4", "8"}:
        return f"{code}.BJ"
    return None


def parse_dt(value: Any) -> datetime | None:
    """tushare 的时间字段格式不统一，统一解析为 naive datetime（UTC+8 本地时间）。"""
    if value is None or value == "":
        return None
    text = str(value).strip()
    for fmt in (DATETIME_FMT, DATE_FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def iter_windows(start: datetime, end: datetime, granularity: str) -> list[tuple[datetime, datetime]]:
    step = timedelta(hours=1) if granularity == "hour" else timedelta(days=1)
    out: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        nxt = min(cursor + step, end)
        out.append((cursor, nxt))
        cursor = nxt
    return out


@register
class TushareNewsConnector(DataSourceConnector):
    key = "tushare.news"
    display_name = "Tushare 财经资讯"
    capability = ConnectorCapability(
        content_types=["flash", "article", "announcement", "policy", "research_report"],
        supports_incremental=True,
        supports_backfill=True,
        rate_limit_per_min=200,
        requires_credentials=True,
    )

    def __init__(self, config: dict[str, Any], credentials: dict[str, Any] | None = None) -> None:
        super().__init__(config, credentials)
        self.failed_segments: list[dict] = []
        self._min_interval = 60.0 / (self.capability.rate_limit_per_min or 200)
        self._last_call = 0.0
        # ★ 接口权限探测结果（Spike #1 实测：不同 token 积分差异极大）
        self.probe_results: dict[str, dict] = {}
        self.available_endpoints: list[str] | None = None

    @property
    def token(self) -> str | None:
        """凭据优先级：连接器实例凭据 > 实例配置 > 环境变量（dev / 单用户场景）。"""
        return (
            (self.credentials or {}).get("token")
            or self.config.get("token")
            or settings.TUSHARE_TOKEN
        )

    def _pro(self):
        import tushare as ts  # 延迟导入：无 token 的环境也能启动服务

        return ts.pro_api(self.token)

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def _query_sync(self, api: str, start: datetime, end: datetime) -> list[dict]:
        # 各接口参数形态不同（Spike #1 实测）
        if api == "cctv_news":
            params: dict[str, Any] = {"date": start.strftime(DATE_FMT)}
        elif api == "news":
            params = {
                "start_date": start.strftime(DATETIME_FMT),
                "end_date": end.strftime(DATETIME_FMT),
            }
            if self.config.get("src"):
                params["src"] = self.config["src"]
        else:
            params = {"start_date": start.strftime(DATE_FMT), "end_date": end.strftime(DATE_FMT)}
            if api == "anns_d":
                params["fields"] = "ts_code,name,ann_date,ann_type,title,url"
        df = self._pro().query(api, **params)
        if df is None or df.empty:
            return []
        return df.to_dict(orient="records")

    async def probe_endpoints(self) -> dict[str, dict]:
        """★ 逐个探测接口权限，而不是等主查询失败（docs/04 §4.4 要求）。

        实测结论（2026-09，本 token）：
        - anns_d / npr / research_report：直接抛"没有接口访问权限"
        - news：**静默返回 0 行**，不报错 —— 最容易造成"同步成功但 0 条"的假象
        - major_news / cctv_news / 行情类：可用
        """
        end = datetime.now()
        start = end - timedelta(days=1)
        results: dict[str, dict] = {}
        for api, _gran, _ct in ENDPOINTS:
            try:
                await self._throttle()
                rows = await asyncio.to_thread(self._query_sync, api, start, end)
                if rows:
                    results[api] = {"ok": True, "rows": len(rows), "reason": ""}
                else:
                    results[api] = {
                        "ok": False,
                        "rows": 0,
                        "reason": "接口返回 0 条：可能无权限，或该区间确实无数据",
                    }
            except Exception as exc:  # noqa: BLE001
                results[api] = {"ok": False, "rows": 0, "reason": str(exc)[:300]}
        self.probe_results = results
        self.available_endpoints = [a for a, r in results.items() if r["ok"]]
        return results

    def unavailable_reason(self) -> str:
        """供 UI 展示"当前 token 无 XX 接口权限"的人话说明。"""
        if not self.probe_results:
            return ""
        parts = [
            f"{api}（{r['reason'][:60]}）" for api, r in self.probe_results.items() if not r["ok"]
        ]
        return "；".join(parts)

    async def validate(self) -> tuple[bool, str]:
        """凭据自检 + **接口权限提前探测**（不等问题发生时才报错）。"""
        if not self.token:
            return False, "缺少 Tushare token：请在「数据源管理」中填写你自己的 token"
        try:
            await self._throttle()
            await asyncio.to_thread(
                lambda: self._pro().query("trade_cal", exchange="SSE", limit=1)
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "积分" in msg or "permission" in msg.lower():
                return False, f"Token 有效但接口权限不足：{msg}"
            return False, f"Tushare 连通性校验失败：{msg}"

        results = await self.probe_endpoints()
        available = [a for a, r in results.items() if r["ok"]]
        if not available:
            return False, f"Token 可用，但没有任何资讯接口有权限：{self.unavailable_reason()}"

        message = f"Tushare 连接正常，可用接口：{', '.join(available)}"
        if len(available) < len(results):
            message += f"；无权限或空数据接口：{self.unavailable_reason()}"
        return True, message

    async def fetch(
        self, cursor: SyncCursor, window: tuple[datetime, datetime]
    ) -> AsyncIterator[RawItem]:
        if not self.token:
            return

        # 只跑"已探测可用"的接口，避免在无权限接口上浪费调用与积分
        if self.available_endpoints is None:
            await self.probe_endpoints()
        allowed = set(self.available_endpoints or [])
        selected = [a for a in (self.config.get("endpoints") or allowed) if a in allowed]
        start, end = window
        if cursor.last_published_at and cursor.last_published_at > start:
            start = cursor.last_published_at

        for api, granularity, content_type in ENDPOINTS:
            if api not in selected:
                continue
            for seg_start, seg_end in iter_windows(start, end, granularity):
                await self._throttle()
                rows: list[dict] = []
                try:
                    rows = await asyncio.to_thread(self._query_sync, api, seg_start, seg_end)
                except Exception as exc:  # noqa: BLE001 分段失败不中断整体
                    self.failed_segments.append(
                        {
                            "api": api,
                            "start": seg_start.isoformat(),
                            "end": seg_end.isoformat(),
                            "error": str(exc)[:500],
                        }
                    )
                    continue

                for row in rows:
                    external_id = str(row.get("id") or row.get("ann_id") or payload_hash(row)[:32])
                    yield RawItem(
                        external_id=f"{api}:{external_id}",
                        payload=row,
                        fetched_at=datetime.now(),
                        source_ref=row.get("url"),
                        content_type=content_type,
                    )

    def normalize(self, raw: RawItem) -> NewsDraft:
        """纯函数：字段映射 + 时间标准化 + 代码补全。缺失字段留给 Enricher。"""
        p = raw.payload
        api = raw.external_id.split(":", 1)[0]

        title = str(p.get("title") or p.get("name") or "").strip()
        content = p.get("content") or p.get("text") or p.get("summary")
        published = parse_dt(p.get("datetime") or p.get("ann_date") or p.get("pub_date") or p.get("date"))

        symbols: list[str] = []
        if p.get("ts_code"):
            code = to_standard_code(str(p["ts_code"]))
            if code:
                symbols.append(code)

        return NewsDraft(
            external_id=raw.external_id,
            content_type=raw.content_type,  # type: ignore[arg-type]
            title=title or f"[{api}] {raw.external_id}",
            summary=(content or "")[:200] or None,
            content=content,
            author=p.get("author") or p.get("name"),
            url=p.get("url"),
            published_at=published or raw.fetched_at,
            lang="zh",
            source_name=p.get("src") or p.get("source") or ("Tushare" if api != "cctv_news" else "央视新闻联播"),
            symbols=symbols,
            market_scope=["a_share"],
            extra={"api": api, "raw_keys": sorted(p.keys())},
        )
