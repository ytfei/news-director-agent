from fastapi import APIRouter

from app.api.v1 import connectors, news

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(connectors.router)
api_router.include_router(news.router)

__all__ = ["api_router"]
