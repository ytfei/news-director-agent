from fastapi import APIRouter

from app.api.v1 import (
    annotations,
    articles,
    connectors,
    market,
    materials,
    news,
    projects,
    reviews,
    runs,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(connectors.router)
api_router.include_router(news.router)
api_router.include_router(market.router)
api_router.include_router(runs.router)  # 通用：查 run 状态 + 恢复断点

# M2：素材 →（可选）批注 → 检查 → 选题
api_router.include_router(materials.router)
api_router.include_router(materials.topics_router)
api_router.include_router(annotations.router)
api_router.include_router(reviews.router)
api_router.include_router(projects.router)
api_router.include_router(projects.prompts_router)

# M3：自动写作（稿件库 + run 断点恢复）
api_router.include_router(articles.router)

__all__ = ["api_router"]
