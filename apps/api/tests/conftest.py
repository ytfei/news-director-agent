"""测试夹具。

★ 关键：本项目的 **DB 引擎和 Redis 客户端都是模块级单例**，而 pytest-asyncio 默认
**每个测试一个事件循环**。两者的连接都绑定在"创建它的事件循环"上，跨循环复用会报错：

- asyncpg：`Task ... attached to a different loop` —— 表现为"数据库未就绪"被静默 skip，
  最坏情况是整套集成测试假装通过；
- redis：测试结束、循环已关闭之后才去关 socket —— 报 `RuntimeError: Event loop is closed`
  （同步链路要用分布式锁，所以接上快讯之后这个问题必然暴露）。

解决：每个测试结束后把两者都释放掉，下个测试在自己的循环里重新建连。
"""

from __future__ import annotations

import os

# ★ 必须在导入 app.* 之前切换：database.engine 是模块级单例，导入时就按 DATABASE_URL 建好了。
#   环境变量优先级高于 .env，所以这样改是生效的。
#   设 USE_TEST_DB=0 可强制走开发库（调试个别用例时用）。
if os.getenv("USE_TEST_DB", "1") != "0":
    os.environ.setdefault(
        "DATABASE_URL",
        os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://nda:nda@localhost:5433/nda_test"),
    )
    os.environ.setdefault(
        "DATABASE_URL_SYNC",
        os.getenv(
            "TEST_DATABASE_URL_SYNC", "postgresql+psycopg://nda:nda@localhost:5433/nda_test"
        ),
    )

import pytest
from app.core.database import SessionLocal, engine
from app.core.redis import close_redis
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def _isolate_loop_bound_clients():
    yield
    await engine.dispose()
    # 在同一测试的循环内关闭，避免留到循环已关闭时才去关
    await close_redis()


async def db_ready() -> tuple[bool, str]:
    """数据库是否可用（且已迁移）。

    不可用时 **skip 而不是 fail**：纯逻辑测试不该因为没起 Postgres 就红。
    但 skip 必须带原因 —— 本项目踩过"集成测试被静默 skip 却显示通过"的坑。
    """
    try:
        async with SessionLocal() as s:
            await s.execute(text("select 1 from source_connectors limit 1"))
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:160]


@pytest.fixture
async def db_session():
    """需要直接操作数据库的测试用（自动 skip 无库环境）。"""
    ok, reason = await db_ready()
    if not ok:
        pytest.skip(f"数据库未就绪（{reason}）")
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def client():
    """走 ASGI 的 API 客户端（自动 skip 无库环境）。"""
    ok, reason = await db_ready()
    if not ok:
        pytest.skip(f"数据库未就绪（{reason}）")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
