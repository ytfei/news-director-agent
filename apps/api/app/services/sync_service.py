"""同步编排：Connector.fetch → ODS → 归一化 → 两级去重 → 归簇 → DWD。

流程见 docs/04-architecture.md §4.5 与 docs/03-user-flow.md 步骤①。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import structlog

from app.core.database import SessionLocal
from app.core.redis import acquire_lock, release_lock
from app.models.enums import SyncStatus
from app.repositories.ingest_repo import ConnectorRepository, SyncRunRepository
from app.repositories.news_repo import NewsRepository
from app.services.connector_factory import build_connector

log = structlog.get_logger()

DEFAULT_LOOKBACK = timedelta(days=1)
COMMIT_EVERY = 50


def default_window(last_run_at: datetime | None, now: datetime) -> tuple[datetime, datetime]:
    start = last_run_at or (now - DEFAULT_LOOKBACK)
    return start, now


def next_run_after(cron_minutes: int, now: datetime) -> datetime:
    return now + timedelta(minutes=cron_minutes)


def empty_reason(connector) -> str:
    """同步结果为空时，给出人话原因（docs/03 §3 步骤① 失败处理表）。

    必须区分「权限不足 / 非交易日 / 区间无数据」，否则用户会以为系统坏了。
    """
    # 用户显式指定了接口，但全部不可用 → 必须明说，否则会以为"同步成功但没数据"
    selected = (connector.config or {}).get("endpoints")
    if selected:
        allowed = set(getattr(connector, "available_endpoints", []) or [])
        missing = [a for a in selected if a not in allowed]
        if missing:
            return f"所选接口无权限或返回空：{', '.join(missing)}；请在数据源配置中改用可用接口"

    probe = getattr(connector, "probe_results", {}) or {}
    if probe and not any(r["ok"] for r in probe.values()):
        return "所有接口均无权限或返回空，请检查 token 积分"
    if probe and not all(r["ok"] for r in probe.values()):
        partial = [a for a, r in probe.items() if r["ok"]]
        return f"仅 {', '.join(partial)} 可用，其余接口无权限或该区间无数据"
    return "区间内无数据（可能是非交易日或时间段内无更新）"


async def run_sync(
    connector_id: uuid.UUID,
    window: tuple[datetime, datetime] | None = None,
    *,
    cron_minutes: int = 30,
) -> dict:
    """执行一次同步。返回统计字典；失败时抛异常由调用方处理。"""
    lock_key = f"nda:sync:lock:{connector_id}"
    if not await acquire_lock(lock_key):
        log.warning("sync.skipped", connector_id=str(connector_id), reason="already_running")
        return {"status": "skipped", "reason": "already_running"}

    inserted = deduped = duplicated = 0
    run_id = None
    try:
        async with SessionLocal() as session:
            conn_repo = ConnectorRepository(session)
            sync_repo = SyncRunRepository(session)
            news_repo = NewsRepository(session)

            connector_row = await conn_repo.get(connector_id)
            if connector_row is None:
                return {"status": "not_found"}

            now = datetime.now()
            win = window or default_window(connector_row.last_run_at, now)
            run = await sync_repo.start_run(connector_id, win)
            run_id = str(run.id)

            connector = build_connector(connector_row)
            ok, message = await connector.validate()
            if not ok:
                await sync_repo.fail_run(run, message)
                await conn_repo.mark_failure(connector_row, message, next_run_after(cron_minutes, now))
                await session.commit()
                return {"status": "failed", "run_id": run_id, "error": message}

            # 保存权限探测结果，供「数据源管理」页高亮"当前 token 无 XX 接口权限"
            probe = getattr(connector, "probe_results", {}) or {}
            if probe:
                connector_row.config = {**(connector_row.config or {}), "probe": probe}

            cursor = conn_repo.cursor_of(connector_row)
            failed_segments: list[dict] = []
            pending = 0

            try:
                async for raw in connector.fetch(cursor, win):
                    raw_id = await news_repo.upsert_raw(connector_id, raw)
                    draft = connector.normalize(raw)

                    # ★ 命中 content_hash 时 is_new=False，但绝不能丢弃
                    news_id, is_new = await news_repo.upsert_draft(
                        draft, connector_id, raw_document_id=raw_id
                    )
                    if is_new:
                        inserted += 1
                    else:
                        duplicated += 1
                        await news_repo.link_duplicate(news_id, connector_id, draft)

                    await news_repo.mark_raw_normalized(raw_id)

                    cursor.last_external_id = raw.external_id
                    cursor.last_published_at = draft.published_at
                    await conn_repo.touch_cursor(connector_row, cursor)

                    pending += 1
                    if pending >= COMMIT_EVERY:
                        await session.commit()
                        pending = 0
            finally:
                failed_segments = list(getattr(connector, "failed_segments", []))
                await connector.close()

            failed_segments += []
            run = await sync_repo.finish_run(
                run,
                inserted=inserted,
                deduped=deduped,
                duplicated=duplicated,
                failed_segments=failed_segments,
            )
            if run.status == SyncStatus.failed:
                await conn_repo.mark_failure(
                    connector_row, run.error or "sync failed", next_run_after(cron_minutes, now)
                )
            else:
                await conn_repo.mark_success(connector_row, next_run_after(cron_minutes, now))
            await session.commit()

            stats = {
                "status": run.status.value,
                "run_id": run_id,
                "fetched": run.fetched_count,
                "inserted": inserted,
                "duplicated": duplicated,
                "failed_segments": failed_segments,
            }
            if run.fetched_count == 0:
                # ★ 空结果必须给出原因，避免"同步成功但 0 条"的假象
                stats["empty_reason"] = empty_reason(connector)
                run.stats = {"empty_reason": stats["empty_reason"]}
            log.info("sync.finished", connector_id=str(connector_id), **stats)
            return stats
    finally:
        await release_lock(lock_key)


async def sync_due_connectors() -> list[dict]:
    """调度入口：运行所有到期的连接器（由 arq cron 调用）。"""
    now = datetime.now()
    async with SessionLocal() as session:
        due = await ConnectorRepository(session).list_due(now)

    results = []
    for row in due:
        results.append(await run_sync(row.id))
    return results


__all__ = ["run_sync", "sync_due_connectors", "default_window"]
