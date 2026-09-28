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


async def generate_fact_card(ctx: dict, news_item_id: str) -> dict:
    """★ B2：资讯级事实基线预生成。

    放在 ingest 阶段而不是 review 阶段，是三个硬约束决定的（docs/05 §4.1）：
    延迟（review 时才跑不可能 < 8s）、成本（每条资讯一次，而非每次检查一次）、
    一致性（同一资讯下不同用户共享同一份基线）。
    """
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.services.researcher_service import generate_fact_card as _generate

    if not settings.FACT_CARD_AUTO_GENERATE:
        return {"news_item_id": news_item_id, "generated": False, "reason": "disabled"}

    async with SessionLocal() as session:
        try:
            card = await _generate(session, uuid.UUID(news_item_id))
        except Exception as exc:  # noqa: BLE001
            # ★ 事实基线是增强项，失败不能污染同步链路
            log.warning("task.fact_card_failed", news_item_id=news_item_id, error=str(exc)[:200])
            return {"news_item_id": news_item_id, "generated": False, "error": str(exc)[:200]}
    return {"news_item_id": news_item_id, "generated": card is not None}


async def generate_due_fact_cards(ctx: dict, limit: int = 10) -> dict:
    """cron：为「已被加为素材但还没有事实基线」的资讯补生成（限量，控成本）。"""
    from app.core.config import settings
    from app.services.researcher_service import generate_due_fact_cards as _generate

    if not settings.FACT_CARD_AUTO_GENERATE:
        return {"scanned": 0, "generated": 0, "failed": 0, "reason": "disabled"}
    return await _generate(limit=limit)


async def review_annotations(
    ctx: dict,
    user_id: str,
    material_ids: list[str],
    mode: str | None = None,
    run_id: str | None = None,
) -> dict:
    """★ 异步三轨检查（B1-3）。

    必须异步：实测核查类任务单条 48~108 秒，同步等在请求里会让用户以为服务挂了。
    调用方拿 202 + run_id 后轮询 `GET /reviews/runs/{run_id}`。

    run_id 由 API 预先建好（status=queued），这样前端无需等任务启动就能拿到 ID。
    """
    from app.services.review_service import review_materials

    return await review_materials(
        uuid.UUID(user_id),
        [uuid.UUID(m) for m in material_ids],
        mode=mode,
        run_id=uuid.UUID(run_id) if run_id else None,
    )


async def compose_project(ctx: dict, user_id: str, project_id: str, run_id: str) -> dict:
    """★ M3 第一阶段：编译 brief + 生成大纲 → 停在 `waiting_human`。

    docs/04 §5.4：interrupt = job **结束**。本 job 到此返回，
    用户确认大纲后由 `compose_resume`（新 job）续跑。
    """
    from app.services.compose_service import plan_phase

    return await plan_phase(uuid.UUID(user_id), uuid.UUID(project_id), uuid.UUID(run_id))


async def compose_resume(ctx: dict, user_id: str, run_id: str) -> dict:
    """★ M3 第二阶段（新 job）：分段并行写作 → 落库稿件。"""
    from app.services.compose_service import resume_phase

    return await resume_phase(uuid.UUID(user_id), uuid.UUID(run_id))


async def cleanup_stale_runs(ctx: dict, hours: int = 24) -> dict:
    """★ 清理超时未恢复的断点 run（docs/03 §5：24h 无响应 → cancelled）。

    没有这个，用户触发写作后关掉页面，`waiting_human` 的 run 会永久堆积，
    一直占着 checkpointer 与配额。
    """
    from datetime import datetime, timedelta

    from sqlalchemy import update

    from app.core.database import SessionLocal
    from app.models.agent import AgentRun
    from app.models.enums import RunStatus

    cutoff = datetime.now() - timedelta(hours=hours)
    async with SessionLocal() as session:
        try:
            result = await session.execute(
                update(AgentRun)
                .where(
                    AgentRun.status == RunStatus.waiting_human,
                    AgentRun.created_at < cutoff,
                )
                .values(status=RunStatus.cancelled, finished_at=datetime.now())
            )
            cancelled = result.rowcount or 0
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("task.cleanup_failed", error=str(exc)[:200])
            return {"cancelled": 0, "error": str(exc)[:200]}

    if cancelled:
        log.info("task.cleanup_stale_runs", cancelled=cancelled, hours=hours)
    return {"cancelled": cancelled}


__all__ = [
    "sync_connector",
    "sync_due",
    "enrich_news_item",
    "generate_fact_card",
    "generate_due_fact_cards",
    "review_annotations",
    "compose_project",
    "compose_resume",
    "cleanup_stale_runs",
]
