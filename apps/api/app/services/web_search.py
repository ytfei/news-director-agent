"""网页检索（B0-2）。

为什么必须有：tushare 覆盖不到海外与自由文本源（X / arXiv / 公司博客 / GitHub），
没有这一层，fact 轨的事实核查就被锁死在 tushare 的覆盖范围里 ——
P1 的科技/产业博主用户群完全服务不了（docs/04 §4.2 B 的 `web_probe`）。

设计原则：**没有配置就安静降级，绝不拖垮主链路**。
检索是"加分项"，拿不到结果只是少一条证据，不该让检查失败。
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger()


class WebSearch:
    """Tavily / 博查检索。无 key 时 `enabled=False`，调用直接返回空列表。"""

    def __init__(self) -> None:
        self.provider = (settings.WEB_SEARCH_PROVIDER or "").strip().lower()
        self.api_key = (settings.WEB_SEARCH_API_KEY or "").strip()
        self.base_url = settings.WEB_SEARCH_BASE_URL.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.provider and self.api_key)

    async def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """返回 [{title, url, snippet, published_at}]。失败返回 []（不抛）。"""
        if not self.enabled or not query.strip():
            return []

        k = top_k or settings.WEB_SEARCH_TOP_K
        try:
            if self.provider == "tavily":
                return await self._tavily(query, k)
            log.warning("web_search.unsupported_provider", provider=self.provider)
            return []
        except Exception as exc:  # noqa: BLE001
            # ★ 检索失败不能让整次检查失败：只记录，返回空
            log.warning("web_search.failed", query=query[:60], error=str(exc)[:200])
            return []

    async def _tavily(self, query: str, top_k: int) -> list[dict]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": top_k,
            "search_depth": "basic",
        }
        async with httpx.AsyncClient(timeout=settings.WEB_SEARCH_TIMEOUT) as client:
            resp = await client.post(f"{self.base_url}/search", json=payload)
            resp.raise_for_status()
            data = resp.json()

        out: list[dict] = []
        for item in data.get("results") or []:
            out.append(
                {
                    "title": item.get("title") or "",
                    "url": item.get("url") or "",
                    "snippet": (item.get("content") or "")[:500],
                    "published_at": item.get("published_date"),
                    "source": "web:tavily",
                }
            )
        return out

    async def search_many(self, queries: list[str]) -> list[dict]:
        """并发检索多个 query 并去重（按 url）。"""
        if not self.enabled or not queries:
            return []
        results = await asyncio.gather(*[self.search(q) for q in queries])
        seen: set[str] = set()
        merged: list[dict] = []
        for group in results:
            for r in group:
                if r["url"] and r["url"] in seen:
                    continue
                seen.add(r["url"])
                merged.append(r)
        return merged


_web_search: WebSearch | None = None


def get_web_search() -> WebSearch:
    global _web_search
    if _web_search is None:
        _web_search = WebSearch()
    return _web_search


__all__ = ["WebSearch", "get_web_search"]
