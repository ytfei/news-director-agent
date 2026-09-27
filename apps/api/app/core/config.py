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

    # ---- 去重与归簇（分层：精确 / 转载 / 事件，见 app/lib/dedupe.py）----
    # L3 转载判定：精确率优先（误合并会丢掉一条独立报道），阈值偏高
    DUP_JACCARD_THRESHOLD: float = 0.75
    DEDUPE_WINDOW_DAYS: int = 7
    # L4 事件聚类：召回优先（漏了就失去交叉验证），阈值偏低。
    # ★ 0.32 是"当前特征不全"下的起点：库里 entities/keywords 全空、embedding 几乎没有，
    #   实际只有"标题重合 + 时间"两个信号，标题相似度 ≈0.43 才能过线。
    #   补上实体抽取与 embedding 后需**用标注集重新标定**（见 TODO P1）。
    EVENT_SCORE_THRESHOLD: float = 0.32
    EVENT_WINDOW_HOURS: float = 72.0
    # 粗筛候选上限（同 bucket 内），控制单次入库的计算量
    DEDUPE_CANDIDATE_LIMIT: int = 200

    # 同步锁 TTL（秒）。★ 配合心跳续约（SyncLock）所以能设短：
    #   进程崩溃后最多等 300s 即可重跑（原 3600s 要等 1 小时，D21）；
    #   正常运行中由心跳每 TTL/3 续期，全量回填这类长任务不会中途丢锁。
    SYNC_LOCK_TTL: int = 300

    # 同步
    SYNC_MAX_CONCURRENT_CONNECTORS: int = 2
    # 单批检查并发上限（其余排队），避免同时打满 LLM
    REVIEW_MAX_CONCURRENCY: int = 5

    # ---- 检查引擎（B1：规则保底 + 模型增强）----
    # rules = 纯规则（零延迟零成本）；llm = 纯模型；hybrid = 两者合并（默认）
    # ★ 默认 hybrid 而不是 llm：实测核查类任务单次 48~108s，且规则版是高精度零成本，
    #   用模型"替换"规则既慢又可能引入误报；规则保底 + 模型补语义层才是正解。
    REVIEW_MODE: str = "hybrid"
    # ★ 改 prompt 必须递增此版本号，否则报告缓存永远命中旧结论
    REVIEW_PROMPT_VERSION: str = "2026-09-28.v1"
    # 三轨置信度阈值（docs/01 §4.2 C：统一阈值下「事实误报<15%」与「合规召回>95%」互斥）
    REVIEW_CONFIDENCE_FACT: float = 0.70        # 高精度：宁可漏报，误报直接伤信任
    REVIEW_CONFIDENCE_COMPLIANCE: float = 0.35  # 高召回：宁可误报，漏报是法律风险
    REVIEW_CONFIDENCE_LOGIC: float = 0.55       # 折中
    # 成本控制：单 run 的 token 预算，超了就停止调用后续条目并标记 budget_exceeded
    REVIEW_TOKEN_BUDGET: int = 200_000
    REVIEW_MAX_ITEMS_PER_RUN: int = 20
    # 成本费率（USD / 1K tokens）。★ 默认 0 = 只记 token 不计费 ——
    # 单价应由 Spike #7 实测后按供应商账单填写，这里不猜。
    # 填了之后 usage_records.cost_usd 才有意义，硬配额也才能按金额判定。
    LLM_COST_PER_1K_INPUT: float = 0.0
    LLM_COST_PER_1K_OUTPUT: float = 0.0

    # ---- 网页检索（B0-2：fact 轨补查，tushare 覆盖不到的海外与自由文本源）----
    WEB_SEARCH_PROVIDER: str = ""          # tavily / bocha；空 = 禁用（自动降级）
    WEB_SEARCH_API_KEY: str = ""
    WEB_SEARCH_BASE_URL: str = "https://api.tavily.com"
    WEB_SEARCH_TIMEOUT: int = 20
    WEB_SEARCH_TOP_K: int = 5

    # ---- 事实基线（B2）----
    # ingest 阶段异步预生成（review 时只读缓存，这是「检查 < 8s」的前提）
    FACT_CARD_AUTO_GENERATE: bool = True
    FACT_CARD_MAX_CLAIMS: int = 12

    # 写入 PG 的目标维度。★ 必须 ≤ 2000：pgvector 的 HNSW/IVFFlat 索引硬上限，
    # 超过则索引无法创建，语义检索退化为 O(n) 全表扫描。
    # doubao-embedding-vision 原生 2048 维，但支持 Matryoshka 降维 ——
    # 调用时传 dimensions=1024 由模型端直接输出 1024 维（前 1024 维本身即有效的
    # 低维表示，非简单截断）。1024 维在检索场景精度损失通常 <2%，换来：
    # 存储减半（8KB→4KB/条）、距离计算减半、且索引终于能建。
    # ★ 改这个值必须配套：新迁移（改 vector 列类型 + 重建 HNSW）+ 全量重算存量向量。
    EMBEDDING_DIM: int = 1024

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
