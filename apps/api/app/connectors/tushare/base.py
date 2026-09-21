"""tushare 系连接器的公共部分：凭据、SDK 调用、按渠道独立限流。

## 两个必须守住的点

**1. tushare SDK 是同步的** → 一律用 `asyncio.to_thread` 包住。
   API 与 worker 都是单进程单事件循环（见 docker-compose 的进程视图），
   一个同步调用就能把整站卡住。

**2. 限流计时器按渠道隔离**。一个连接器实例可能覆盖多个来源（如快讯的 9 个 src），
   共用一个计时器会让 N 个来源被串行拖慢；完全不限流又会撞上游频率限制。
   这里按渠道各记一个 `last_call`，既独立又不会互相挤占。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

from app.connectors.base import DataSourceConnector
from app.core.config import settings
from app.lib.hash import json_safe

# tushare 各接口的时间入参格式（Spike #1 实测：不同接口不一致）
TUSHARE_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"
TUSHARE_COMPACT_DT_FMT = "%Y%m%d %H%M%S"
TUSHARE_DATE_FMT = "%Y%m%d"


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


def iter_windows(
    start: datetime, end: datetime, granularity: str | timedelta
) -> list[tuple[datetime, datetime]]:
    """把 [start, end) 切成若干段，避免长区间一次性拉取。"""
    if isinstance(granularity, timedelta):
        step = granularity
    else:
        step = timedelta(hours=1) if granularity == "hour" else timedelta(days=1)
    out: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        nxt = min(cursor + step, end)
        out.append((cursor, nxt))
        cursor = nxt
    return out


class TushareBase(DataSourceConnector):
    """tushare 系连接器的公共基类。"""

    def __init__(self, config: dict[str, Any], credentials: dict[str, Any] | None = None) -> None:
        super().__init__(config, credentials)
        self.failed_segments: list[dict] = []
        # 每个渠道一个计时器：来源之间互不拖慢
        self._last_call: dict[str, float] = {}
        self._min_interval = 60.0 / (self.capability.rate_limit_per_min or 200)
        # ★ 接口/来源权限探测结果（Spike #1 实测：不同 token 权限差异极大）
        self.probe_results: dict[str, dict] = {}
        self.available_endpoints: list[str] | None = None
        self._pro_client = None

    # ---------------- 凭据 ----------------

    @property
    def token(self) -> str | None:
        """凭据优先级：连接器实例凭据 > 实例配置 > 环境变量（dev / 单用户场景）。"""
        return (
            (self.credentials or {}).get("token")
            or self.config.get("token")
            or settings.TUSHARE_TOKEN
        )

    def _pro(self):
        if self._pro_client is None:
            import tushare as ts  # 延迟导入：无 token 的环境也能启动服务

            self._pro_client = ts.pro_api(self.token)
        return self._pro_client

    # ---------------- 调用 ----------------

    async def _throttle(self, channel: str = "-") -> None:
        elapsed = time.monotonic() - self._last_call.get(channel, 0.0)
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_call[channel] = time.monotonic()

    async def _query(self, api: str, *, channel: str = "-", **params: Any) -> list[dict]:
        """调 tushare 接口并返回记录列表。

        同步 SDK 放线程池；空结果统一归一为 `[]`，避免每个调用点各写一遍。
        异常向上抛，由调用方决定是"整段失败"还是"记入 failed_segments 后继续"。
        """
        await self._throttle(channel)

        def _run() -> list[dict]:
            frame = self._pro().query(api, **params)
            if frame is None or getattr(frame, "empty", True):
                return []
            # ★ pandas 的缺失值是 float('nan')/NaT，直接进 jsonb 会被 PG 拒收
            #   （invalid input syntax for type json: Token "NaN" is invalid）。
            #   在**数据入口**统一归一，比让每个调用点各自清洗可靠。
            return [json_safe(row) for row in frame.to_dict(orient="records")]

        return await asyncio.to_thread(_run)

    async def close(self) -> None:
        self._pro_client = None


__all__ = [
    "TUSHARE_COMPACT_DT_FMT",
    "TUSHARE_DATE_FMT",
    "TUSHARE_DATETIME_FMT",
    "TushareBase",
    "iter_windows",
    "to_standard_code",
]
