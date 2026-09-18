"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import dispose_engine
from app.core.logging import configure_logging
from app.core.redis import close_redis

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("app.startup", env=settings.APP_ENV)
    yield
    await close_redis()
    await dispose_engine()
    log.info("app.shutdown")


app = FastAPI(
    title="主理人 Agent API",
    description="观点驱动的内容生产工作台",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "env": settings.APP_ENV}


__all__ = ["app"]
