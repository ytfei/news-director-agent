"""模型层测试。

- 不需要 key 的部分：维度对齐（_fit）与降级行为
- 需要 key 的部分：真机连通（缺 key 时 skip，注意 skip ≠ pass）
"""

from __future__ import annotations

import os

import pytest

from app.core.config import settings
from app.services.model_provider import ModelError, ModelProvider, TokenUsage

HAS_KEY = bool(settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"))


def test_token_usage_total_and_merge():
    u = TokenUsage(input=10, output=20, reasoning=5)
    assert u.total == 30
    u.merge(TokenUsage(input=1, output=2, reasoning=3))
    assert (u.input, u.output, u.reasoning) == (11, 22, 8)
    assert u.as_dict() == {"input": 11, "output": 22, "reasoning": 8}


def test_fit_truncates_and_pads():
    """维度必须对齐到实际存储维度，否则写入 PG 会报错。"""
    p = ModelProvider(api_key="test")
    p._fit  # noqa: B018  # 仅确认属性存在
    assert len(p._fit([0.1] * 2048)) == p.embedding_dim
    assert len(p._fit([0.1] * 10)) == p.embedding_dim


def test_disabled_provider_raises():
    """未配置 key 时调用应抛 ModelError，而不是 AttributeError。"""
    p = ModelProvider(api_key=None)
    assert p.enabled is False
    with pytest.raises(ModelError):
        p._ensure_client()


def test_light_model_falls_back():
    p = ModelProvider(api_key="test", llm_model="big", llm_model_light=None)
    assert p.llm_light == "big"
    p2 = ModelProvider(api_key="test", llm_model="big", llm_model_light="small")
    assert p2.llm_light == "small"


@pytest.mark.skipif(not HAS_KEY, reason="需要 OPENAI_API_KEY")
@pytest.mark.asyncio
async def test_real_embedding():
    """真机：向量维度必须与 EMBEDDING_DIM 对齐。"""
    p = ModelProvider()
    vec = await p.embed_one("贵州茅台三季度营收")
    assert len(vec) == p.embedding_dim, f"维度不一致：{len(vec)} vs {p.embedding_dim}"
    print(f"\n[embedding] dim={len(vec)} target={p.embedding_dim}")


@pytest.mark.skipif(not HAS_KEY, reason="需要 OPENAI_API_KEY")
@pytest.mark.asyncio
async def test_real_chat_and_reasoning_tokens():
    """真机：对话可用，且推理 token 被单独统计（成本可观测的前提）。"""
    p = ModelProvider()
    text, usage = await p.chat(
        [{"role": "user", "content": "用一句话说明什么是降准"}],
        max_tokens=200,
    )
    assert text.strip()
    assert usage.input > 0 and usage.output > 0
    print(f"\n[chat] {usage.as_dict()} reasoning_ratio="
          f"{usage.reasoning / max(usage.output, 1):.0%}")
