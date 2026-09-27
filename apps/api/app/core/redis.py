"""Redis 客户端（缓存 + 队列 + 分布式锁）。"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

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


# --------------------------------------------------------------------------- 锁
async def acquire_lock(key: str, ttl: int | None = None) -> str | None:
    """获取锁，成功返回 token（释放时必须出示），失败返回 None。

    ★ 用唯一 token 而不是固定值：只有持有者才能续约/释放，
      否则 A 任务超时后，B 拿到锁，A 结束时一次 `DELETE` 就把 B 的锁删掉了。
    """
    client = await get_redis()
    token = str(uuid.uuid4())
    ok = await client.set(key, token, nx=True, ex=ttl or settings.SYNC_LOCK_TTL)
    return token if ok else None


async def renew_lock(key: str, token: str, ttl: int | None = None) -> bool:
    """续约（仅当仍由自己持有）。"""
    client = await get_redis()
    if await client.get(key) == token:
        await client.expire(key, ttl or settings.SYNC_LOCK_TTL)
        return True
    return False


async def release_lock(key: str, token: str) -> bool:
    """释放（仅当仍由自己持有）。"""
    client = await get_redis()
    if await client.get(key) == token:
        await client.delete(key)
        return True
    return False


class SyncLock:
    """同步用的分布式锁：**短 TTL + 心跳续约**。

    为什么这样设计（D21）：
    - TTL 长（原 3600s）：进程崩溃后要等 1 小时才能重跑 —— 本次实际踩到，
      只能手动 `redis-cli del` 解锁；
    - TTL 短：全量回填这类长任务又会中途丢锁，让另一个同步并发进来，
      反而破坏"同一 connector 不允许并发"的约束。

    心跳让两者兼得：TTL 设短（崩溃快速恢复），运行中由后台任务定期续期。
    """

    def __init__(self, key: str, ttl: int | None = None) -> None:
        self.key = key
        self.ttl = ttl or settings.SYNC_LOCK_TTL
        self.token: str | None = None
        self._beat: asyncio.Task | None = None

    async def acquire(self) -> bool:
        self.token = await acquire_lock(self.key, self.ttl)
        if self.token is None:
            return False
        self._beat = asyncio.create_task(self._heartbeat())
        return True

    async def release(self) -> None:
        if self._beat is not None:
            self._beat.cancel()
            # 取消自身不该冒泡（这里只关心"别让心跳任务的异常干扰释放流程"）
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._beat
            self._beat = None
        if self.token:
            await release_lock(self.key, self.token)
            self.token = None

    async def _heartbeat(self) -> None:
        """每 TTL/3 续一次 —— 即使一次网络抖动漏掉，也还有两次机会。"""
        interval = max(5, self.ttl // 3)
        while True:
            await asyncio.sleep(interval)
            if not self.token:
                return
            if not await renew_lock(self.key, self.token, self.ttl):
                # 锁已不属于自己（理论上不该发生），停止续约，避免抢别人的锁
                return

    async def __aenter__(self) -> SyncLock:
        got = await self.acquire()
        if not got:
            raise LockBusy(self.key)
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.release()


class LockBusy(RuntimeError):
    """锁被占用（同一 connector 已有同步在跑）。"""


__all__ = [
    "get_redis",
    "close_redis",
    "acquire_lock",
    "renew_lock",
    "release_lock",
    "SyncLock",
    "LockBusy",
]
