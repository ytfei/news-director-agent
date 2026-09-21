"""数据源管理 API。"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, ensure_user, get_session
from app.connectors.base import SyncCursor
from app.connectors.registry import (
    available_connectors,
    get_connector_class,
    migration_hint,
    resolve_key,
)
from app.lib.crypto import encrypt_secret
from app.models.enums import ConnectorStatus
from app.models.ingest import SourceConnector
from app.repositories.ingest_repo import ConnectorRepository, SyncRunRepository
from app.services.connector_factory import build_connector
from app.services.sync_service import run_sync

log = structlog.get_logger()
router = APIRouter(prefix="/connectors", tags=["connectors"])


class ConnectorCreate(BaseModel):
    key: str
    display_name: str | None = None
    config: dict = Field(default_factory=dict)
    credentials: dict | None = None
    schedule_cron: str | None = "*/30 * * * *"


class ConnectorOut(BaseModel):
    id: uuid.UUID
    key: str
    display_name: str
    status: str
    config: dict
    capability: dict
    schedule_cron: str | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    # 该行的 key 已被拆分/改名时，给出人话迁移提示（前端展示，不自动改数据）
    key_migrated_to: str | None = None
    migration_note: str | None = None

    model_config = {"from_attributes": True}


def to_out(row: SourceConnector) -> ConnectorOut:
    out = ConnectorOut.model_validate(row)
    hint = migration_hint(row.key)
    if hint:
        out.key_migrated_to = hint["to_key"]
        out.migration_note = hint["note"]
    # ★ 能力声明取**注册表里的当前声明**，而不是建表时写进 source_connectors.capability 的快照。
    #   否则给连接器新增配置项后，存量行在前端仍然看不到新表单（快照是旧的）。
    #   连接器已下线时取不到 → 退回存量快照，至少还能展示。
    with contextlib.suppress(LookupError):
        out.capability = get_connector_class(row.key).capability.model_dump()
    return out


class ConnectorPatch(BaseModel):
    """改配置：`config` 整体替换（前端提交完整对象），不做字段级 merge。"""

    display_name: str | None = None
    config: dict | None = None
    credentials: dict | None = None
    schedule_cron: str | None = None
    status: ConnectorStatus | None = None


class SyncTrigger(BaseModel):
    window_start: datetime | None = None
    window_end: datetime | None = None


@router.get("/available")
async def list_available() -> list[dict]:
    """能力声明：前端据此动态渲染配置表单。"""
    return available_connectors()


@router.get("", response_model=list[ConnectorOut])
async def list_connectors(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[ConnectorOut]:
    rows = await ConnectorRepository(session).list_all()
    return [to_out(r) for r in rows]


@router.post("", response_model=ConnectorOut, status_code=201)
async def create_connector(
    payload: ConnectorCreate,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> SourceConnector:
    await ensure_user(session, user_id)
    try:
        cls = get_connector_class(payload.key)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ★ 新行一律落现行 key：别名只用于兼容历史数据，不该继续写进库
    resolved_key = resolve_key(payload.key)

    row = SourceConnector(
        owner_id=user_id,
        connector_type=resolved_key.split(".", 1)[0],
        key=resolved_key,
        display_name=payload.display_name or cls.display_name,
        status=ConnectorStatus.active,
        config=payload.config,
        credentials_ref=encrypt_secret(payload.credentials) if payload.credentials else None,
        capability=cls.capability.model_dump(),
        schedule_cron=payload.schedule_cron,
        next_run_at=datetime.now(),
    )
    session.add(row)
    await session.commit()
    return to_out(row)


@router.patch("/{connector_id}", response_model=ConnectorOut)
async def update_connector(
    connector_id: uuid.UUID,
    payload: ConnectorPatch,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> ConnectorOut:
    """改配置 / 改名 / 改计划。

    前端按能力声明的 `config_schema` 渲染表单，这里只做落库，不需要认识任何具体连接器。
    """
    row = await ConnectorRepository(session).get(connector_id)
    if row is None:
        raise HTTPException(status_code=404, detail="connector not found")

    fields = payload.model_dump(exclude_unset=True)
    if fields.get("config") is not None:
        row.config = fields["config"]
    if fields.get("display_name"):
        row.display_name = fields["display_name"]
    if fields.get("schedule_cron") is not None:
        row.schedule_cron = fields["schedule_cron"]
    if fields.get("status") is not None:
        row.status = fields["status"]
    if fields.get("credentials"):
        row.credentials_ref = encrypt_secret(fields["credentials"])
    await session.commit()
    return to_out(row)


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(
    connector_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> None:
    """软删。软删后同 owner 可重新创建同 key 的连接器（部分唯一索引保证）。"""
    row = await ConnectorRepository(session).get(connector_id)
    if row is None:
        raise HTTPException(status_code=404, detail="connector not found")
    row.deleted_at = datetime.now()
    row.status = ConnectorStatus.disabled
    await session.commit()


@router.post("/{connector_id}/validate")
async def validate_connector(
    connector_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    row = await ConnectorRepository(session).get(connector_id)
    if row is None:
        raise HTTPException(status_code=404, detail="connector not found")
    connector = build_connector(row)
    ok, message = await connector.validate()
    return {"ok": ok, "message": message}


@router.post("/{connector_id}/sync", status_code=202)
async def trigger_sync(
    connector_id: uuid.UUID,
    payload: SyncTrigger | None = None,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """手动触发同步。同步是长任务：M1 同步执行并返回统计（后续改 202 + SSE）。"""
    row = await ConnectorRepository(session).get(connector_id)
    if row is None:
        raise HTTPException(status_code=404, detail="connector not found")

    window = None
    if payload and payload.window_start and payload.window_end:
        window = (payload.window_start, payload.window_end)

    result = await run_sync(connector_id, window)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="connector not found")
    return result


@router.get("/{connector_id}/runs")
async def list_runs(
    connector_id: uuid.UUID,
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[dict]:
    runs = await SyncRunRepository(session).list_runs(connector_id, limit)
    return [
        {
            "id": r.id,
            "status": r.status.value,
            "fetched": r.fetched_count,
            "inserted": r.inserted_count,
            "duplicated": r.duplicated_count,
            "error": r.error,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
        }
        for r in runs
    ]


__all__ = ["router", "SyncCursor"]
