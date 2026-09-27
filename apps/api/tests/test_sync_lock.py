"""同步锁测试（需要 Redis，未就绪时 skip 并说明原因）。

覆盖 D21 要解决的两件事：
1. 进程崩溃（没释放）后，TTL 到期能自动重获 —— 不再需要手动 del
2. 长任务运行中锁不会丢 —— 靠心跳续约
3. token 机制 —— 只有持有者能释放，避免误删后来者的锁
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from app.core.redis import (
    LockBusy,
    SyncLock,
    acquire_lock,
    close_redis,
    get_redis,
    release_lock,
)

KEY = f"nda:test:lock:{uuid.uuid4().hex}"


@pytest.fixture(autouse=True)
async def _require_redis():
    try:
        await (await get_redis()).ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis 未就绪（{str(exc)[:80]}）")
    yield
    await close_redis()


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    client = await get_redis()
    await client.delete(KEY)


async def test_acquire_release_cycle():
    token = await acquire_lock(KEY, ttl=30)
    assert token, "首次应能获取"
    assert await acquire_lock(KEY, ttl=30) is None, "持有期间不可重入"
    assert await release_lock(KEY, token) is True
    assert await acquire_lock(KEY, ttl=30) is not None, "释放后应可再获取"


async def test_foreign_token_cannot_release():
    """★ 若用固定值而非 token，A 超时后 B 拿到锁，A 结束时一次 DELETE 会删掉 B 的锁。"""
    token = await acquire_lock(KEY, ttl=30)
    assert await release_lock(KEY, "someone-else") is False
    assert await acquire_lock(KEY, ttl=30) is None, "锁应仍被持有"
    await release_lock(KEY, token)


async def test_recoverable_after_crash():
    """模拟进程崩溃（不释放）：TTL 到期后应能自动重获 —— 这是 D21 的核心。"""
    await acquire_lock(KEY, ttl=2)
    await asyncio.sleep(3)
    assert await acquire_lock(KEY, ttl=30) is not None, "崩溃后 TTL 到期应可重获"


async def test_heartbeat_keeps_lock_alive():
    """长任务：TTL 15s，等 7s 后锁仍应在（被心跳续约），而不是已过期被别人拿走。"""
    lock = SyncLock(KEY, ttl=15)
    assert await lock.acquire()
    await asyncio.sleep(7)
    assert await acquire_lock(KEY, ttl=5) is None, "心跳续约期间不应被他人获取"
    await lock.release()
    assert await acquire_lock(KEY, ttl=5) is not None, "主动释放后应可获取"


async def test_context_manager_and_busy():
    async with SyncLock(KEY, ttl=30):
        with pytest.raises(LockBusy):
            async with SyncLock(KEY, ttl=30):
                pass
    # 退出后不再占用
    async with SyncLock(KEY, ttl=30):
        pass


async def test_release_is_idempotent():
    lock = SyncLock(KEY, ttl=30)
    await lock.acquire()
    await lock.release()
    await lock.release()  # 重复释放不应报错
    assert await acquire_lock(KEY, ttl=5) is not None
