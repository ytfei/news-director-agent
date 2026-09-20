"""测试夹具。

★ 关键：`app.core.database.engine` 是模块级对象，而 pytest-asyncio 默认**每个测试一个事件循环**。
asyncpg 的连接与创建它的事件循环绑定，跨越循环复用池化连接会直接报
`Task ... attached to a different loop`，表现为"数据库未就绪"被静默 skip ——
最坏情况是整套集成测试假装通过。

解决：每个测试结束后释放连接池，下个测试在自己的循环里重新建连。
"""

from __future__ import annotations

import pytest
from app.core.database import engine


@pytest.fixture(autouse=True)
async def _isolate_db_pool():
    yield
    await engine.dispose()
