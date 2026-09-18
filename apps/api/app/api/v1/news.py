"""资讯中心 API（M1 第一层「资讯台」）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, get_session
from app.models.enums import ActionType
from app.models.news import NewsItem, NewsItemRelation
from app.models.user import UserNewsAction
from app.repositories.news_repo import NewsRepository

router = APIRouter(prefix="/news", tags=["news"])


class NewsOut(BaseModel):
    id: uuid.UUID
    title: str
    summary: str | None
    source_name: str | None
    url: str | None
    content_type: str
    published_at: datetime
    importance: float | None
    cluster_id: uuid.UUID | None
    industries: list[str]
    market_scope: list[str]
    source_count: int = 1

    model_config = {"from_attributes": True}


class ActionIn(BaseModel):
    action: ActionType
    rating: int | None = None
    dwell_ms: int | None = None


@router.get("", response_model=list[NewsOut])
async def list_news(
    content_type: str | None = None,
    industry: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[NewsItem]:
    stmt = NewsRepository(session).list_query(
        content_type=content_type, industry=industry, since=since, until=until
    )
    result = await session.execute(stmt.limit(limit).offset(offset))
    items = result.scalars().all()
    # source_count：跨源登记了多少家（"另有 N 家报道"的数据来源）
    return [
        NewsOut(
            id=i.id,
            title=i.title,
            summary=i.summary,
            source_name=i.source_name,
            url=i.url,
            content_type=i.content_type.value,
            published_at=i.published_at,
            importance=float(i.importance) if i.importance else None,
            cluster_id=i.cluster_id,
            industries=i.industries or [],
            market_scope=i.market_scope or [],
            source_count=len(i.source_refs or []),
        )
        for i in items
    ]


@router.get("/{news_id}")
async def get_news(
    news_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    item = await session.get(NewsItem, news_id)
    if item is None or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="news not found")

    # 同一事件簇内的其他来源 → "另有 N 家报道"（跨源交叉验证的入口）
    siblings = (
        await session.execute(
            select(NewsItem.id, NewsItem.title, NewsItem.source_name, NewsItem.url).where(
                NewsItem.cluster_id == item.cluster_id,
                NewsItem.id != item.id,
            )
        )
    ).all()

    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "content": item.content,
        "content_type": item.content_type.value,
        "source_name": item.source_name,
        "url": item.url,
        "published_at": item.published_at,
        "importance": float(item.importance) if item.importance else None,
        "industries": item.industries,
        "market_scope": item.market_scope,
        "source_refs": item.source_refs,
        "cluster_id": item.cluster_id,
        "siblings": [
            {"id": s[0], "title": s[1], "source_name": s[2], "url": s[3]} for s in siblings
        ],
    }


@router.post("/{news_id}/actions", status_code=201)
async def create_action(
    news_id: uuid.UUID,
    payload: ActionIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """收藏 / 评级 / 隐藏 / 已读。

    ★ read 是行为流（可多次），其余是状态类（部分唯一索引保证只留最新）。
    """
    item = await session.get(NewsItem, news_id)
    if item is None:
        raise HTTPException(status_code=404, detail="news not found")

    if payload.action == ActionType.rate and (payload.rating is None or not 1 <= payload.rating <= 5):
        raise HTTPException(status_code=422, detail="rating must be between 1 and 5")

    if payload.action != ActionType.read:
        existing = (
            await session.execute(
                select(UserNewsAction).where(
                    UserNewsAction.user_id == user_id,
                    UserNewsAction.news_item_id == news_id,
                    UserNewsAction.action == payload.action,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.rating = payload.rating
            existing.dwell_ms = payload.dwell_ms
            await session.commit()
            return {"id": existing.id, "action": existing.action.value, "updated": True}

    row = UserNewsAction(
        user_id=user_id,
        news_item_id=news_id,
        action=payload.action,
        rating=payload.rating,
        dwell_ms=payload.dwell_ms,
    )
    session.add(row)
    await session.commit()
    return {"id": row.id, "action": row.action.value, "updated": False}


__all__ = ["router", "NewsItemRelation"]
