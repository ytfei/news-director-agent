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
    # ★ 独立测试库：集成测试默认写这里，避免污染开发库（TODO D13）。
    #   用空库跑测试时先执行 make test-db-create
    TEST_DATABASE_URL: str = "postgresql+asyncpg://nda:nda@localhost:5433/nda_test"
    TEST_DATABASE_URL_SYNC: str = "postgresql+psycopg://nda:nda@localhost:5433/nda_test"
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

    # ---- 三档模型（seed 2.1 系列）----
    # ★ 实测：三款**都是推理模型**（reasoning token 占 97~100%）。
    #   同一 prompt 对比（2026-09-25）：
    #     pro   1M 上下文 · 最强长链推理      分类 194tok/10s · 核查 4285tok/108s
    #     turbo 256k · 推理强、价约 pro 一半   分类  37tok/ 2s · 核查 3613tok/ 56s  ← 甜点
    #     lite  256k · 低成本高吞吐            分类 201tok/ 5s · 核查 3055tok/ 48s
    # ★ 反直觉：lite 在简单任务上**并不比 turbo 省**（201 vs 37）。
    #   "轻量"指能力定位，不是思考更少。因此默认档是 turbo 而非 lite。
    LLM_MODEL_PRO: str = "doubao-seed-2.1-pro"
    LLM_MODEL_TURBO: str = "doubao-seed-2.1-turbo"
    LLM_MODEL_LITE: str = "doubao-seed-2.1-lite"
    # 未显式指定档位时的默认
    LLM_TIER_DEFAULT: str = "turbo"
    # 按场景覆盖档位：{"write_plan":"pro","review":"turbo"}，键见 Task 枚举
    LLM_TIER_OVERRIDES: dict[str, str] = {}

    LLM_IS_REASONING: bool = True
    LLM_TIMEOUT: int = 180
    LLM_MAX_RETRIES: int = 2

    # 是否用 LLM 做打标。turbo 在分类任务实测仅 37 tokens / 2s，成本可接受；
    # 但仍默认关：先让规则版跑稳，M2 收尾时评估是否切换
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

    # 向量维度：doubao-embedding-vision 实测 2048（已定案），换维度需重建向量列
    EMBEDDING_DIM: int = 2048

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
