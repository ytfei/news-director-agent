"""模型层：OpenAI 兼容协议的统一入口。

设计要点（docs/04 §10.1.1 私有化前置）：
- 所有模型调用走这里，上层不直接依赖 SDK → 换供应商 / 换私有化部署只改配置
- base_url 可指向火山方舟 Ark、OpenAI、自建 vLLM / Ollama 的 OpenAI 兼容端点
- 没有配置 API Key 时 `enabled=False`，调用方降级而不是崩溃（M1/M2 的规则链路仍可跑）

实测记录（2026-09-24）：
- `doubao-embedding-vision` → 2048 维
- `doubao-seed-evolving` → 推理模型，completion token 中约 96% 是 reasoning_tokens
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.config import settings

log = structlog.get_logger()


@dataclass
class TokenUsage:
    input: int = 0
    output: int = 0
    reasoning: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output

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
    llm_model: str = settings.LLM_MODEL
    llm_model_light: str | None = settings.LLM_MODEL_LIGHT
    embedding_model: str = settings.EMBEDDING_MODEL
    _client: Any = field(default=None, init=False, repr=False)

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
    def llm(self) -> str:
        """默认对话模型。"""
        return self.llm_model

    @property
    def llm_light(self) -> str:
        """轻量模型（打标 / 聚类等简单任务）。未配置时回落到主模型。"""
        return self.llm_model_light or self.llm_model

    @property
    def embedding_dim(self) -> int:
        """实际写入数据库的维度（考虑截断）。"""
        return settings.EMBEDDING_TRUNCATE_TO or settings.EMBEDDING_DIM

    # ---------------------------------------------------------------- 对话
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        light: bool = False,
    ) -> tuple[str, TokenUsage]:
        """返回 (文本, token 用量)。推理模型不传 temperature（部分端点会报错）。"""
        client = self._ensure_client()
        use_model = model or (self.llm_light if light else self.llm)

        kwargs: dict[str, Any] = {"model": use_model, "messages": messages}
        # 推理模型（如 doubao-seed-evolving）不接受 temperature
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

        text = resp.choices[0].message.content or ""
        log.info("llm.chat", model=use_model, **usage.as_dict())
        return text, usage

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        light: bool = False,
    ) -> tuple[dict | list | None, TokenUsage]:
        """要求模型返回 JSON。失败时抛 ModelError，由调用方决定降级。"""
        import json

        text, usage = await self.chat(
            messages,
            model=model,
            light=light,
            response_format={"type": "json_object"},
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
                        model=self.embedding_model, input=batch
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error("llm.embed_failed", error=str(exc)[:300])
                    raise ModelError(f"向量化失败：{exc}") from exc
                if resp.usage:
                    log.debug(
                        "llm.embed",
                        batch=len(batch),
                        prompt_tokens=getattr(resp.usage, "prompt_tokens", 0),
                    )
                return [self._fit(d.embedding) for d in resp.data]

        results = await asyncio.gather(*[one(b) for b in batches])
        return [vec for batch in results for vec in batch]

    async def embed_one(self, text: str) -> list[float]:
        vecs = await self.embed([text])
        return vecs[0] if vecs else []

    def _fit(self, vec: list[float]) -> list[float]:
        """对齐到实际存储维度：截断或补零。

        ★ pgvector 索引上限 2000 维，而 doubao-embedding-vision 是 2048 维。
        若配置了 EMBEDDING_TRUNCATE_TO，对所有向量统一截断，余弦相似度仍可用（精度下降）。
        """
        target = self.embedding_dim
        if len(vec) == target:
            return vec
        if len(vec) > target:
            return vec[:target]
        return vec + [0.0] * (target - len(vec))


_provider: ModelProvider | None = None


def get_model_provider() -> ModelProvider:
    global _provider
    if _provider is None:
        _provider = ModelProvider()
    return _provider


__all__ = [
    "TokenUsage",
    "ModelError",
    "ModelProvider",
    "get_model_provider",
]
