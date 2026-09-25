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

    # ---------------- 模型（OpenAI 兼容协议） ----------------
    # 火山方舟 Ark 的 OpenAI 兼容端点；私有化时换成自建 vLLM / Ollama 的同协议地址
    OPENAI_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/plan/v3"
    OPENAI_API_KEY: str | None = None

    # 大语言模型
    LLM_MODEL: str = "doubao-seed-evolving"
    # ★ doubao-seed-evolving 是推理模型：一次回答里绝大部分 token 是 reasoning_tokens
    #   （实测 1180 completion 中 1136 为推理）。成本与延迟都高，
    #   所以「打标 / 聚类」这类简单任务不要用它（见 LLM_MODEL_LIGHT）。
    LLM_IS_REASONING: bool = True
    LLM_TIMEOUT: int = 180
    LLM_MAX_RETRIES: int = 2
    # 轻量模型：留空表示暂时复用 LLM_MODEL（接入更便宜的模型后在此配置）
    LLM_MODEL_LIGHT: str | None = None

    # 是否用 LLM 做打标（默认关：doubao-seed-evolving 是推理模型，逐条打标成本不可接受）
    ENRICH_USE_LLM: bool = False

    # Embedding
    EMBEDDING_PROVIDER: str = "openai-compatible"
    EMBEDDING_MODEL: str = "doubao-embedding-vision"
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_CONCURRENCY: int = 2
    # 0 = 不截断。pgvector 的 HNSW/IVFFlat 索引上限 2000 维，
    # 若需要建向量索引，可设 ≤2000（对所有向量统一截断，余弦相似度仍可用但精度下降）
    EMBEDDING_TRUNCATE_TO: int = 0

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
