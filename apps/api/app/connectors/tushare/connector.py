"""Tushare 长文 / 公告 / 政策 / 研报连接器。

覆盖除快讯之外的 tushare 资讯类接口（快讯已拆到 `tushare.flash`，见 flash.py）：
major_news(长文) / cctv_news(新闻联播) / anns_d(公告) / npr(政策) / research_report(研报)

要点：
- 按粒度切分时间窗，避免长区间一次性拉取
- token bucket 限流 + 单段失败不中断整体（记入 failed_segments，同步结束时标 partial）
- 字段映射全部走声明式 ChannelSpec（`specs.ARTICLE_SPECS`），本文件不写字段映射逻辑
- normalize() 是纯函数，无 IO

★ 与快讯的差别：这里**没有渠道分组**，`RawItem.channel` 就是接口名本身。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog

from app.connectors.base import (
    ConnectorCapability,
    NormalizedItem,
    Provenance,
    RawItem,
    SyncCursor,
)
from app.connectors.registry import register
from app.connectors.spec import DEFAULT_TZ
from app.connectors.tushare.base import (
    TUSHARE_DATE_FMT,
    TushareBase,
    iter_windows,
    to_standard_code,  # noqa: F401  （历史上从这里导入，保留可导入性）
)
from app.connectors.tushare.specs import ARTICLE_SPECS, api_label

log = structlog.get_logger()

# (接口名, 拉取粒度, content_type)
ENDPOINTS: list[tuple[str, str, str]] = [
    ("major_news", "day", "article"),
    ("cctv_news", "day", "article"),
    ("anns_d", "day", "announcement"),
    ("npr", "day", "policy"),
    ("research_report", "day", "research_report"),
]

PROBE_LOOKBACK = timedelta(days=1)


@register
class TushareArticleConnector(TushareBase):
    key = "tushare.article"
    display_name = "Tushare 长文 / 公告 / 政策 / 研报"
    capability = ConnectorCapability(
        content_types=["article", "announcement", "policy", "research_report"],
        supports_incremental=True,
        supports_backfill=True,
        rate_limit_per_min=200,
        requires_credentials=True,
        config_schema=[
            {
                "key": "endpoints",
                "label": "启用的接口",
                "type": "multiselect",
                "required": False,
                "options": [{"value": a, "label": a} for a, _g, _c in ENDPOINTS],
                "default": [],
                "help": "留空 = 自动只跑当前 token 有权限的接口；无权限的接口会被探测出来并跳过。",
            },
        ],
    )

    # ---------------- 查询 ----------------

    async def _query_endpoint(self, api: str, start: datetime, end: datetime) -> list[dict]:
        """各接口参数形态不同（Spike #1 实测）。"""
        if api == "cctv_news":
            params: dict = {"date": start.strftime(TUSHARE_DATE_FMT)}
        else:
            params = {
                "start_date": start.strftime(TUSHARE_DATE_FMT),
                "end_date": end.strftime(TUSHARE_DATE_FMT),
            }
            if api == "anns_d":
                params["fields"] = "ts_code,name,ann_date,ann_type,title,url"
        return await self._query(api, channel=api, **params)

    # ---------------- 探测 ----------------

    async def probe_endpoints(self) -> dict[str, dict]:
        """逐个探测接口权限，而不是等主查询失败（docs/04 §4.4 要求）。

        实测结论（2026-09，本 token）：
        - anns_d / npr / research_report：直接抛"没有接口访问权限"
        - major_news / cctv_news：可用
        注意"返回 0 行且不报错"**不能**判为无权限（可能只是该区间无数据），
        文案必须把两种可能都说出来。
        """
        end = datetime.now(tz=ZoneInfo(DEFAULT_TZ))
        start = end - PROBE_LOOKBACK
        results: dict[str, dict] = {}
        for api, _gran, _ct in ENDPOINTS:
            try:
                rows = await self._query_endpoint(api, start, end)
                results[api] = {
                    "ok": bool(rows),
                    "rows": len(rows),
                    "reason": ""
                    if rows
                    else "接口返回 0 条：可能无权限，或该区间确实无数据",
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

    def empty_reason(self) -> str | None:
        """同步 0 条时的人话原因（取代原先写在 sync_service 里的 tushare 专属判定）。"""
        selected = (self.config or {}).get("endpoints")
        if selected:
            allowed = set(self.available_endpoints or [])
            missing = [a for a in selected if a not in allowed]
            if missing:
                return (
                    f"所选接口无权限或返回空：{', '.join(missing)}；"
                    "请在数据源配置中改用可用接口"
                )

        probe = self.probe_results or {}
        if not probe:
            return None  # 没探测过 → 交给通用兜底文案
        if not any(r["ok"] for r in probe.values()):
            return "所有接口均无权限或返回空，请检查 token 权限"
        if not all(r["ok"] for r in probe.values()):
            partial = [a for a, r in probe.items() if r["ok"]]
            return f"仅 {', '.join(partial)} 可用，其余接口无权限或该区间无数据"
        return "区间内无数据（可能是非交易日或时间段内无更新）"

    # ---------------- 校验 ----------------

    async def validate(self) -> tuple[bool, str]:
        """凭据自检 + 接口权限提前探测（不等问题发生时才报错）。"""
        if not self.token:
            return False, "缺少 Tushare token：请在「数据源管理」中填写你自己的 token"
        try:
            await self._query("trade_cal", channel="trade_cal", exchange="SSE", limit=1)
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

    # ---------------- 拉取 ----------------

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

        for api, granularity, _content_type in ENDPOINTS:
            if api not in selected:
                continue
            for seg_start, seg_end in iter_windows(start, end, granularity):
                try:
                    rows = await self._query_endpoint(api, seg_start, seg_end)
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
                    spec = ARTICLE_SPECS[api]
                    external_id = spec.build_external_id(row, {"channel": api})
                    yield RawItem(
                        external_id=external_id,
                        payload=row,
                        fetched_at=datetime.now(tz=ZoneInfo(DEFAULT_TZ)),
                        source_ref=row.get("url"),
                        # content_type 来自 spec，避免与 ENDPOINTS 表两处定义漂移
                        content_type=spec.content_type,
                        channel=api,
                    )

    # ---------------- 归一化 ----------------

    def normalize(self, raw: RawItem) -> NormalizedItem:
        """纯函数：映射逻辑全在 ARTICLE_SPECS 里。"""
        api = raw.channel or raw.external_id.split(":", 1)[0]
        spec = ARTICLE_SPECS.get(api)
        if spec is None:
            raise ValueError(f"tushare.article 未声明接口 {api} 的字段映射")

        ctx = {
            "api": api,
            "channel": api,
            "channel_label": api_label(api),
            "fetched_at": raw.fetched_at,
        }
        return spec.normalize(
            raw.payload,
            ctx=ctx,
            external_id=raw.external_id,
            source_ref=raw.source_ref,
            provenance=Provenance(
                connector_key=self.key,
                api=api,
                channel=api,
                channel_label=api_label(api),
                fetched_at=raw.fetched_at,
            ),
        )


__all__ = ["ENDPOINTS", "TushareArticleConnector", "to_standard_code"]
