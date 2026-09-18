"""Redis 客户端（缓存 + 队列 + 分布式锁）。"""

from __future__ import annotations

import redis.asyncio as redis

from app.core.config import settings

_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def acquire_lock(key: str, ttl: int = 3600) -> bool:
    """简单分布式锁：同一 connector 不允许并发运行。"""
    client = await get_redis()
    return bool(await client.set(key, "1", nx=True, ex=ttl))


async def release_lock(key: str) -> None:
    client = await get_redis()
    await client.delete(key)


__all__ = ["get_redis", "close_redis", "acquire_lock", "release_lock"]
