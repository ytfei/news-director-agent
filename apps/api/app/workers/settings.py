"""arq Worker 配置（docs/04-architecture.md §5.4）。"""

from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.workers.tasks import (
    enrich_news_item,
    generate_due_fact_cards,
    generate_fact_card,
    review_annotations,
    sync_connector,
    sync_due,
)


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    # LLM 调用是 IO 密集，但单 job 占用久 → 低并发
    max_jobs = settings.ARQ_MAX_JOBS
    # 单次"无中断连续执行"的上限；HITL 中断时 job 会正常结束，不占这个额度
    job_timeout = settings.ARQ_JOB_TIMEOUT
    # LLM 任务不做自动重试（成本高且非幂等），失败交用户决定
    max_tries = 2
    poll_delay = 0.5
    health_check_interval = 30

    functions = [
        sync_connector,
        sync_due,
        enrich_news_item,
        generate_fact_card,
        generate_due_fact_cards,
        review_annotations,
    ]

    cron_jobs = [
        # 交易日每 30 分钟（非交易日降频由 connector 状态控制）
        cron(sync_due, minute={0, 30}, run_at_startup=False),
        # 事实基线补生成：每小时限量 10 条。★ 限量是刻意的 ——
        # 全量预生成意味着上万次 LLM 调用，成本会吃掉收入，只为被用到的资讯生成。
        cron(generate_due_fact_cards, minute={15}, run_at_startup=False),
    ]


__all__ = ["WorkerSettings"]
