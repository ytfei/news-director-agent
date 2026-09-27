"""arq 入队封装（API 进程 → worker 进程）。

★ 为什么需要这一层：
    三轨检查实测单条 48~108 秒，绝不能同步等在 HTTP 请求里 ——
    用户会以为服务挂了。必须入队，API 立刻返回 202 + run_id 供轮询。

★ 降级约定：
    Redis 不可用时返回 None（而不是抛异常），由调用方决定
    「降级为同步执行」还是「直接报错」。开发机上不启 worker 也要能跑通链路。
"""

from __future__ import annotations

import structlog
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings

log = structlog.get_logger()


async def enqueue_job(name: str, *args, **kwargs) -> str | None:
    """入队一个 arq 任务，返回 job_id；失败返回 None。"""
    try:
        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    except Exception as exc:  # noqa: BLE001
        log.warning("queue.connect_failed", error=str(exc)[:200])
        return None

    try:
        job = await redis.enqueue_job(name, *args, **kwargs)
        return job.job_id if job else None
    except Exception as exc:  # noqa: BLE001
        log.warning("queue.enqueue_failed", name=name, error=str(exc)[:200])
        return None
    finally:
        # 关闭失败不影响入队结果（任务已经放进 Redis 了）
        try:
            redis.close()
            await redis.wait_closed()
        except Exception:  # noqa: BLE001, S110
            pass


__all__ = ["enqueue_job"]
