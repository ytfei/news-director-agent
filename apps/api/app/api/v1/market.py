"""数值事实读取接口。

本期只用于**验证落库路径可用**：tushare 快讯不产出数值事实，所以这张表当前是空的。
接行情 / 资金流 / 宏观数据源后，这里就是"引用事实"、事实卡片与写作时量化引用的取数入口。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, get_session
from app.repositories.market_repo import MarketFactRepository

router = APIRouter(prefix="/market", tags=["market"])


def _out(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        # numeric(24,6) 精确存储；出参转 float 是为了让 JSON 消费方免于解析字符串。
        # 典型财经量级（亿元 / % / 万元每吨）在 float64 的 15~16 位有效数字内是无损的。
        "value": float(row.value),
        "value_exact": str(row.value),
        "unit": row.unit,
        "period": row.period,
        "ts_code": row.ts_code,
        "observed_at": row.observed_at,
        "attributes": row.attributes or {},
        "news_item_id": row.news_item_id,
        "source_connector_id": row.source_connector_id,
    }


@router.get("/facts")
async def list_facts(
    ts_code: str | None = Query(default=None, description="标准码，如 600519.SH"),
    name: str | None = Query(default=None, description="指标名"),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[dict]:
    """按标的 / 指标 / 时间区间取数值事实（时间序列，新的在前）。"""
    rows = await MarketFactRepository(session).list_facts(
        ts_code=ts_code, name=name, since=since, until=until, limit=limit, offset=offset
    )
    return [_out(r) for r in rows]


@router.get("/facts/count")
async def count_facts(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """用于运维/自检：确认落库路径是否真的有数据流过。"""
    return {"total": await MarketFactRepository(session).count()}


__all__ = ["router"]
