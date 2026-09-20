"""素材库 API（M2 中枢）+ 主题标签 API。

docs/06 §4.1：素材列表是工作台与选题的共同数据源，
因此筛选维度（日期 / 评分 / 主题 / 有无点评）必须一次给全。
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, ensure_user, get_session
from app.models.news import NewsItem
from app.repositories.material_repo import TopicRepository
from app.services.material_service import MaterialService

router = APIRouter(prefix="/materials", tags=["materials"])
topics_router = APIRouter(prefix="/topics", tags=["topics"])


class MaterialIn(BaseModel):
    """标记素材。幂等：同一资讯重复标记 = 更新。"""

    news_id: uuid.UUID
    score: int = Field(default=5, ge=1, le=10)
    topics: list[str] = Field(default_factory=list)
    material_date: date | None = None
    note: str | None = None


class MaterialPatch(BaseModel):
    score: int | None = Field(default=None, ge=1, le=10)
    topics: list[str] | None = None
    material_date: date | None = None
    note: str | None = None


class TopicIn(BaseModel):
    name: str
    color: str | None = None


@router.get("")
async def list_materials(
    date_: date | None = Query(default=None, alias="date"),
    min_score: int | None = Query(default=None, ge=1, le=10),
    max_score: int | None = Query(default=None, ge=1, le=10),
    topic: list[str] = Query(default_factory=list),
    has_annotation: bool | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[dict]:
    return await MaterialService(session).list_items(
        user_id,
        material_date=date_,
        min_score=min_score,
        max_score=max_score,
        topic_names=topic,
        has_annotation=has_annotation,
        limit=limit,
        offset=offset,
    )


@router.get("/stats")
async def material_stats(
    date_: date | None = Query(default=None, alias="date"),
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    return await MaterialService(session).stats(user_id, date_ or date.today())


@router.post("", status_code=201)
async def mark_material(
    payload: MaterialIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    await ensure_user(session, user_id)
    if await session.get(NewsItem, payload.news_id) is None:
        raise HTTPException(status_code=404, detail="news not found")
    result = await MaterialService(session).mark(
        user_id,
        payload.news_id,
        score=payload.score,
        topic_names=payload.topics,
        material_date=payload.material_date,
        note=payload.note,
    )
    await session.commit()
    return result


@router.get("/{material_id}")
async def get_material(
    material_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    item = await MaterialService(session).detail(user_id, material_id)
    if item is None:
        raise HTTPException(status_code=404, detail="material not found")
    return item


@router.patch("/{material_id}")
async def patch_material(
    material_id: uuid.UUID,
    payload: MaterialPatch,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    item = await MaterialService(session).update(
        user_id,
        material_id,
        score=payload.score,
        topic_names=payload.topics,
        material_date=payload.material_date,
        note=payload.note,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="material not found")
    await session.commit()
    return item


@router.delete("/{material_id}", status_code=204)
async def delete_material(
    material_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> None:
    """软删（点评与选题关联保留审计）。"""
    if not await MaterialService(session).remove(user_id, material_id):
        raise HTTPException(status_code=404, detail="material not found")
    await session.commit()


# ---------------- 主题 ----------------


@topics_router.get("")
async def list_topics(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[dict]:
    rows = await TopicRepository(session).list_for_user(user_id)
    return [
        {
            "id": t.id,
            "slug": t.slug,
            "name": t.name,
            "color": t.color,
            "is_system": t.is_system,
        }
        for t in rows
    ]


@topics_router.post("", status_code=201)
async def create_topic(
    payload: TopicIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    await ensure_user(session, user_id)
    topics = await TopicRepository(session).ensure(user_id, [payload.name])
    await session.commit()
    t = topics[0]
    return {"id": t.id, "slug": t.slug, "name": t.name, "color": payload.color, "is_system": False}


__all__ = ["router", "topics_router"]
