"""模型层：OpenAI 兼容协议的统一入口 + 按场景路由档位。

设计要点（docs/04 §10.1.1 私有化前置）：
- 所有模型调用走这里，上层不直接依赖 SDK → 换供应商 / 私有化只改配置
- base_url 可指向火山方舟 Ark、OpenAI、自建 vLLM / Ollama 的 OpenAI 兼容端点
- 没有配置 API Key 时 `enabled=False`，调用方降级而不是崩溃

档位（seed 2.1 系列，2026-09-25 实测）：
    pro   1M   旗舰深度推理    分类 194tok/10s · 核查 4285tok/108s
    turbo 256k 均衡主力        分类  37tok/ 2s · 核查 3613tok/ 56s   ← 甜点
    lite  256k 轻量通用        分类 201tok/ 5s · 核查 3055tok/ 48s

三条实测结论，直接决定了下面的路由表：
1. 三款**都是推理模型**（reasoning 占 97~100%），没有"非推理"选项可用；
2. lite 在简单任务上**并不比 turbo 省**（201 vs 37）—— "轻量"是能力定位，
   不是思考更少，所以默认档是 turbo 而不是 lite；
3. 核查类任务单次要 48~108 秒，远超「检查单条 < 8s」的目标
   → 因此 REVIEW 走 LLM 时必须异步，默认路径仍应保留规则版。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from app.core.config import settings

log = structlog.get_logger()


class Tier(str, Enum):
    PRO = "pro"
    TURBO = "turbo"
    LITE = "lite"


class Task(str, Enum):
    """场景标识。`LLM_TIER_OVERRIDES` 用的就是这个枚举的 value。"""

    CLASSIFY = "classify"  # 打标 / 分类 / 聚类
    EXTRACT = "extract"  # 实体 / 关键词抽取
    SUMMARIZE = "summarize"  # 摘要
    REVIEW = "review"  # 三轨检查（深度模式）
    FACT_CHECK = "fact_check"  # 事实复核（对照 FactCard）
    WRITE_PLAN = "write_plan"  # 大纲规划
    WRITE_SECTION = "write_section"  # 段落写作
    STYLE = "style"  # 风格统一
    TITLE = "title"  # 标题 / 摘要候选


# 场景 → 默认档位。理由见文件头实测数据。
DEFAULT_TIER: dict[Task, Tier] = {
    # 简单高频：turbo 实测只要 37 tokens / 2s，是全场最省
    Task.CLASSIFY: Tier.TURBO,
    Task.EXTRACT: Tier.TURBO,
    Task.TITLE: Tier.TURBO,
    # 批量类：lite 高吞吐
    Task.SUMMARIZE: Tier.LITE,
    Task.FACT_CHECK: Tier.LITE,
    # 需要推理质量：turbo 全能力且价约 pro 一半；pro 太慢（108s）
    Task.REVIEW: Tier.TURBO,
    Task.WRITE_SECTION: Tier.TURBO,
    Task.STYLE: Tier.TURBO,
    # 只有"复杂长链推理"才值得用 pro：大纲规划决定全文结构
    Task.WRITE_PLAN: Tier.PRO,
}


@dataclass
class TokenUsage:
    input: int = 0
    output: int = 0
    reasoning: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output

    @property
    def reasoning_ratio(self) -> float:
        return self.reasoning / max(self.output, 1)

    def merge(self, other: TokenUsage) -> TokenUsage:
        self.input += other.input
        self.output += other.output
        self.reasoning += other.reasoning
        return self

    def as_dict(self) -> dict[str, int]:
        return {"input": self.input, "output": self.output, "reasoning": self.reasoning}


class ModelError(RuntimeError):
    """模型调用失败。"""


@dataclass
class ModelProvider:
    base_url: str = settings.OPENAI_BASE_URL
    api_key: str | None = settings.OPENAI_API_KEY
    _client: Any = field(default=None, init=False, repr=False)

    # ---------------------------------------------------------------- 档位
    @property
    def models(self) -> dict[Tier, str]:
        return {
            Tier.PRO: settings.LLM_MODEL_PRO,
            Tier.TURBO: settings.LLM_MODEL_TURBO,
            Tier.LITE: settings.LLM_MODEL_LITE,
        }

    def tier_for(self, task: Task | None) -> Tier:
        """场景 → 档位，支持配置覆盖。"""
        default = DEFAULT_TIER.get(task, Tier(settings.LLM_TIER_DEFAULT)) if task else Tier(
            settings.LLM_TIER_DEFAULT
        )
        if task:
            override = settings.LLM_TIER_OVERRIDES.get(task.value)
            if override:
                try:
                    return Tier(override)
                except ValueError:
                    log.warning("llm.bad_tier_override", task=task.value, value=override)
        return default

    def model_for(self, tier: Tier) -> str:
        return self.models[tier]

    # ---------------------------------------------------------------- 基础
    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _ensure_client(self):
        if self._client is None:
            if not self.enabled:
                raise ModelError("未配置 OPENAI_API_KEY，模型能力不可用")
            from openai import AsyncOpenAI  # 延迟导入：无 key 时也能启动服务

            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=settings.LLM_TIMEOUT,
                max_retries=settings.LLM_MAX_RETRIES,
            )
        return self._client

    @property
    def embedding_dim(self) -> int:
        """实际写入数据库的维度（考虑截断）。"""
        return settings.EMBEDDING_TRUNCATE_TO or settings.EMBEDDING_DIM

    # ---------------------------------------------------------------- 对话
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        task: Task | None = None,
        tier: Tier | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> tuple[str, TokenUsage]:
        """返回 (文本, token 用量)。

        档位由 `tier` 显式指定，或由 `task` 路由得出。
        推理模型不传 temperature（部分端点会拒绝）。
        """
        client = self._ensure_client()
        use_tier = tier or self.tier_for(task)
        use_model = self.model_for(use_tier)

        kwargs: dict[str, Any] = {"model": use_model, "messages": messages}
        if temperature is not None and not settings.LLM_IS_REASONING:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            resp = await client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            log.error("llm.chat_failed", model=use_model, error=str(exc)[:300])
            raise ModelError(f"模型调用失败（{use_model}）：{exc}") from exc

        usage = TokenUsage()
        if resp.usage:
            usage.input = getattr(resp.usage, "prompt_tokens", 0) or 0
            usage.output = getattr(resp.usage, "completion_tokens", 0) or 0
            details = getattr(resp.usage, "completion_tokens_details", None)
            if details:
                usage.reasoning = getattr(details, "reasoning_tokens", 0) or 0

        log.info(
            "llm.chat",
            model=use_model,
            tier=use_tier.value,
            task=task.value if task else None,
            **usage.as_dict(),
        )
        return resp.choices[0].message.content or "", usage

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        task: Task | None = None,
        tier: Tier | None = None,
    ) -> tuple[dict | list | None, TokenUsage]:
        """要求模型返回 JSON。失败抛 ModelError，由调用方决定降级。"""
        import json

        text, usage = await self.chat(
            messages, task=task, tier=tier, response_format={"type": "json_object"}
        )
        try:
            return json.loads(text), usage
        except json.JSONDecodeError as exc:
            raise ModelError(f"模型未返回合法 JSON：{text[:200]}") from exc

    # ---------------------------------------------------------------- 向量
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化。按 EMBEDDING_BATCH_SIZE 分批、EMBEDDING_CONCURRENCY 并发。"""
        if not texts:
            return []
        client = self._ensure_client()

        batches = [
            texts[i : i + settings.EMBEDDING_BATCH_SIZE]
            for i in range(0, len(texts), settings.EMBEDDING_BATCH_SIZE)
        ]
        sem = asyncio.Semaphore(max(1, settings.EMBEDDING_CONCURRENCY))

        async def one(batch: list[str]) -> list[list[float]]:
            async with sem:
                try:
                    resp = await client.embeddings.create(
                        model=settings.EMBEDDING_MODEL,
                        input=batch,
                        # ★ Matryoshka 降维（2026-09-28 定案）：模型原生 2048 维，
                        #   但 pgvector 的 HNSW/IVFFlat 索引硬上限是 2000 维 —— 超了索引建不了，
                        #   检索会退化成 O(n) 全表扫描。
                        #   该模型支持 dimensions 参数，由模型端直接输出 1024 维
                        #   （Matryoshka 表征：前 N 维本身就是有效的低维表示，不是简单截断）。
                        #   比"取 2048 再本地截断"更干净：传输与存储都减半。
                        dimensions=settings.EMBEDDING_DIM,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error("llm.embed_failed", error=str(exc)[:300])
                    raise ModelError(f"向量化失败：{exc}") from exc
                return [self._fit(d.embedding) for d in resp.data]

        results = await asyncio.gather(*[one(b) for b in batches])
        return [vec for batch in results for vec in batch]

    async def embed_one(self, text: str) -> list[float]:
        vecs = await self.embed([text])
        return vecs[0] if vecs else []

    def _fit(self, vec: list[float]) -> list[float]:
        """对齐到实际存储维度（截断或补零）。**兜底，正常路径不会触发**。

        正常情况下 `dimensions` 参数已让模型返回 EMBEDDING_DIM 维，这里直接返回。
        仅在供应商忽略 dimensions 参数、或换用不支持降维的模型时才需要截断/补零，
        此时 EMBEDDING_TRUNCATE_TO 可进一步指定一个比 EMBEDDING_DIM 更小的目标维度。
        """
        target = self.embedding_dim
        if len(vec) == target:
            return vec
        if len(vec) > target:
            log.warning("llm.embed_dim_mismatch", actual=len(vec), target=target)
            return vec[:target]
        return vec + [0.0] * (target - len(vec))


_provider: ModelProvider | None = None


def get_model_provider() -> ModelProvider:
    global _provider
    if _provider is None:
        _provider = ModelProvider()
    return _provider


__all__ = [
    "Tier",
    "Task",
    "DEFAULT_TIER",
    "TokenUsage",
    "ModelError",
    "ModelProvider",
    "get_model_provider",
]
