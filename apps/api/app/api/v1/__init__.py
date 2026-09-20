from fastapi import APIRouter

from app.api.v1 import annotations, connectors, materials, news, projects, reviews

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(connectors.router)
api_router.include_router(news.router)

# M2：素材 →（可选）批注 → 检查 → 选题
api_router.include_router(materials.router)
api_router.include_router(materials.topics_router)
api_router.include_router(annotations.router)
api_router.include_router(reviews.router)
api_router.include_router(projects.router)
api_router.include_router(projects.prompts_router)

__all__ = ["api_router"]
