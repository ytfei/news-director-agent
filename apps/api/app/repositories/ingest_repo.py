"""数据源与同步运行仓储。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import SyncCursor
from app.models.enums import SyncStatus
from app.models.ingest import SourceConnector, SyncRun


class ConnectorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, connector_id: uuid.UUID) -> SourceConnector | None:
        return (
            await self.session.execute(
                select(SourceConnector).where(
                    SourceConnector.id == connector_id,
                    SourceConnector.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def list_all(self, *, active_only: bool = True) -> list[SourceConnector]:
        stmt = select(SourceConnector).where(SourceConnector.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(SourceConnector.status == "active")
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_due(self, now: datetime) -> list[SourceConnector]:
        """调度器：取到期需要运行的连接器。"""
        stmt = (
            select(SourceConnector)
            .where(
                SourceConnector.deleted_at.is_(None),
                SourceConnector.status == "active",
                (SourceConnector.next_run_at.is_(None)) | (SourceConnector.next_run_at <= now),
            )
            .order_by(SourceConnector.next_run_at.asc().nullsfirst())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    def cursor_of(self, connector: SourceConnector) -> SyncCursor:
        return SyncCursor.model_validate(connector.cursor or {})

    async def touch_cursor(self, connector: SourceConnector, cursor: SyncCursor) -> None:
        connector.cursor = cursor.model_dump(mode="json")

    async def mark_success(self, connector: SourceConnector, next_run_at: datetime) -> None:
        connector.last_run_at = datetime.now()
        connector.next_run_at = next_run_at
        connector.consecutive_failures = 0
        connector.last_error = None

    async def mark_failure(self, connector: SourceConnector, error: str, next_run_at: datetime) -> None:
        connector.last_run_at = datetime.now()
        connector.next_run_at = next_run_at
        connector.consecutive_failures += 1
        connector.last_error = error[:2000]
        if connector.consecutive_failures >= 3:
            connector.status = "error"


class SyncRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_run(
        self, connector_id: uuid.UUID, window: tuple[datetime, datetime] | None = None
    ) -> SyncRun:
        run = SyncRun(
            connector_id=connector_id,
            status=SyncStatus.running,
            window_start=window[0] if window else None,
            window_end=window[1] if window else None,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def finish_run(
        self,
        run: SyncRun,
        *,
        inserted: int,
        deduped: int,
        duplicated: int,
        failed_segments: list[dict] | None = None,
    ) -> SyncRun:
        fetched = inserted + deduped + duplicated
        failed_segments = failed_segments or []
        run.fetched_count = fetched
        run.inserted_count = inserted
        run.deduped_count = deduped
        run.duplicated_count = duplicated
        run.failed_segments = failed_segments

        if failed_segments:
            run.status = SyncStatus.partial if inserted else SyncStatus.failed
            run.error = f"{len(failed_segments)} 个分段失败"
        else:
            run.status = SyncStatus.success
        run.finished_at = datetime.now()
        await self.session.flush()
        return run

    async def fail_run(self, run: SyncRun, error: str) -> None:
        run.status = SyncStatus.failed
        run.error = error[:2000]
        run.finished_at = datetime.now()
        await self.session.flush()

    async def list_runs(self, connector_id: uuid.UUID, limit: int = 20) -> list[SyncRun]:
        stmt = (
            select(SyncRun)
            .where(SyncRun.connector_id == connector_id)
            .order_by(SyncRun.started_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())


__all__ = ["ConnectorRepository", "SyncRunRepository", "text"]
