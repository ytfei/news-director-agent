"""API 依赖。

★ M1 未接 JWT：用 X-User-Id 头或 dev 默认用户。接入鉴权时只需替换 current_user_id。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models.user import User

# dev 兜底用户，首次请求时自动创建
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def current_user_id(x_user_id: str | None = Header(default=None)) -> uuid.UUID:
    if not x_user_id:
        return DEV_USER_ID
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        return DEV_USER_ID


async def ensure_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    """确保用户存在（dev 阶段自动创建）。"""
    existing = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if existing:
        return existing
    user = User(id=user_id, display_name="开发者", email=f"dev+{user_id}@local")
    session.add(user)
    await session.commit()
    return user


__all__ = ["get_session", "current_user_id", "ensure_user", "DEV_USER_ID"]
