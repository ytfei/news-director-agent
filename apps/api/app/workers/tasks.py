"""arq 任务定义。

★ 生命周期规则（docs/04-architecture.md §5.4）：
interrupt = job 结束，resume = 新 job。这里只跑"无中断连续执行"的段。
"""

from __future__ import annotations

import uuid

import structlog

from app.services.sync_service import run_sync, sync_due_connectors

log = structlog.get_logger()


async def sync_connector(ctx: dict, connector_id: str) -> dict:
    """同步指定连接器。"""
    return await run_sync(uuid.UUID(connector_id))


async def sync_due(ctx: dict) -> list[dict]:
    """调度入口：运行所有到期的连接器。"""
    return await sync_due_connectors()


async def enrich_news_item(ctx: dict, news_item_id: str) -> dict:
    """打标 / 向量化（M1 为规则版占位，ScoutAgent 上线后替换）。"""
    from app.services.enrich_service import enrich_news_item as _enrich

    return await _enrich(uuid.UUID(news_item_id))


__all__ = ["sync_connector", "sync_due", "enrich_news_item"]
