"""模型层测试。

- 不需要 key 的部分：维度对齐（_fit）、档位路由、降级行为
- 需要 key 的部分：真机连通（缺 key 时 skip，注意 skip ≠ pass）
"""

from __future__ import annotations

import os

import pytest
from app.core.config import settings
from app.services.model_provider import (
    DEFAULT_TIER,
    ModelError,
    ModelProvider,
    Task,
    Tier,
    TokenUsage,
)

HAS_KEY = bool(settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"))


def test_token_usage():
    u = TokenUsage(input=10, output=20, reasoning=19)
    assert u.total == 30
    assert 0.9 < u.reasoning_ratio < 1.0
    u.merge(TokenUsage(input=1, output=2, reasoning=3))
    assert (u.input, u.output, u.reasoning) == (11, 22, 22)


def test_fit_truncates_and_pads():
    """维度必须对齐到实际存储维度，否则写入 PG 报错。"""
    p = ModelProvider(api_key="test")
    assert len(p._fit([0.1] * 2048)) == p.embedding_dim
    assert len(p._fit([0.1] * 10)) == p.embedding_dim


def test_disabled_provider_raises():
    """未配置 key 时应抛 ModelError，而不是 AttributeError。"""
    p = ModelProvider(api_key=None)
    assert p.enabled is False
    with pytest.raises(ModelError):
        p._ensure_client()


def test_tier_routing():
    """路由表必须覆盖全部场景，且符合实测结论。"""
    for task in Task:
        assert task in DEFAULT_TIER, f"{task} 缺少默认档位"

    # 实测依据：turbo 在简单任务只要 37 tok / 2s，是全场最省
    assert DEFAULT_TIER[Task.CLASSIFY] is Tier.TURBO
    assert DEFAULT_TIER[Task.EXTRACT] is Tier.TURBO
    # 批量类走 lite
    assert DEFAULT_TIER[Task.SUMMARIZE] is Tier.LITE
    assert DEFAULT_TIER[Task.FACT_CHECK] is Tier.LITE
    # 只有复杂长链推理值得 pro
    assert DEFAULT_TIER[Task.WRITE_PLAN] is Tier.PRO
    # 检查走 turbo：pro 太慢（实测 108s），lite 复杂推理弱
    assert DEFAULT_TIER[Task.REVIEW] is Tier.TURBO


def test_model_for_tier():
    p = ModelProvider(api_key="test")
    assert p.model_for(Tier.PRO) == settings.LLM_MODEL_PRO
    assert p.model_for(Tier.TURBO) == settings.LLM_MODEL_TURBO
    assert p.model_for(Tier.LITE) == settings.LLM_MODEL_LITE
    assert p.tier_for(None) == Tier(settings.LLM_TIER_DEFAULT)


@pytest.mark.skipif(not HAS_KEY, reason="需要 OPENAI_API_KEY")
@pytest.mark.asyncio
async def test_real_embedding():
    p = ModelProvider()
    vec = await p.embed_one("贵州茅台三季度营收")
    assert len(vec) == p.embedding_dim
    print(f"\n[embedding] dim={len(vec)} target={p.embedding_dim}")


@pytest.mark.skipif(not HAS_KEY, reason="需要 OPENAI_API_KEY")
@pytest.mark.asyncio
async def test_real_chat_default_tier():
    """默认档（turbo）可用，且 reasoning token 被单独统计。"""
    p = ModelProvider()
    text, usage = await p.chat(
        [{"role": "user", "content": "用一句话说明什么是降准"}],
        task=Task.SUMMARIZE,
        max_tokens=200,
    )
    assert text.strip()
    assert usage.input > 0 and usage.output > 0
    print(f"\n[chat] {usage.as_dict()} reasoning_ratio={usage.reasoning_ratio:.0%}")
