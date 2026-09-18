"""应用配置。全部走环境变量，便于 SaaS 与私有化共用一套代码。"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 应用
    APP_ENV: Literal["dev", "test", "prod"] = "dev"
    LOG_LEVEL: str = "INFO"
    API_PORT: int = 8000

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://nda:nda@localhost:5433/nda"
    DATABASE_URL_SYNC: str = "postgresql+psycopg://nda:nda@localhost:5433/nda"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Redis / 队列
    REDIS_URL: str = "redis://localhost:6379"
    ARQ_MAX_JOBS: int = 8
    # 单次"无中断连续执行"的上限；HITL 中断时 job 会正常结束，不占这个额度
    ARQ_JOB_TIMEOUT: int = 900

    # 数据源
    TUSHARE_TOKEN: str | None = None
    TUSHARE_QPS: float = 3.0
    TUSHARE_TIMEOUT: int = 30

    # Embedding（私有化时换本地模型，走同一 ModelProvider 抽象）
    EMBEDDING_PROVIDER: str = "volcengine"
    EMBEDDING_MODEL: str = "doubao-embedding-vision"

    # 同步
    SYNC_MAX_CONCURRENT_CONNECTORS: int = 2
    # 单批检查并发上限（其余排队），避免同时打满 LLM
    REVIEW_MAX_CONCURRENCY: int = 5

    # 向量维度：由 Spike #4 定模型后固定，换维度需重建 HNSW
    EMBEDDING_DIM: int = 1024

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
