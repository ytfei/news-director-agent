"""模型连通性与档位对比自检（不依赖数据库）。

    make models            # 或 cd apps/api && uv run python scripts/model_smoke.py

为什么单独一个脚本而不是放进 doctor：
doctor 要求"快且无副作用"（进 CI 与部署前置），而模型探测要真实花钱、
耗时数十秒。两者分开：doctor 只校验配置自洽，本脚本负责"真的能调通"。

检查项：
1. Embedding 维度是否与 EMBEDDING_DIM 一致（不一致 = 写入 PG 直接报错）
2. 三档模型（pro / turbo / lite）是否可用，各消耗多少 token、耗时多久
3. 打印「场景 → 档位」路由表，便于核对策略是否符合预期

退出码：0 通过；1 失败。
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.core.config import settings  # noqa: E402
from app.services.model_provider import (  # noqa: E402
    DEFAULT_TIER,
    ModelError,
    Task,
    Tier,
    get_model_provider,
)

OK, WARN, ERR = "\033[32m✓\033[0m", "\033[33m!\033[0m", "\033[31m✗\033[0m"

# 简单任务：用来暴露各档位的"思考成本"差异
CLASSIFY_PROMPT = (
    "把下面这条财经资讯归类到[银行,半导体,新能源,汽车,地产,宏观]中的一个，只回一个词："
    "央行宣布下调存款准备金率0.5个百分点"
)


def mask(key: str | None) -> str:
    if not key:
        return "(未配置)"
    return key[:8] + "***" + key[-4:] if len(key) > 16 else "***"


def print_routing() -> None:
    print("\n场景 → 档位路由")
    for task in Task:
        tier = DEFAULT_TIER[task]
        override = settings.LLM_TIER_OVERRIDES.get(task.value)
        model = getattr(settings, f"LLM_MODEL_{tier.value.upper()}")
        mark = f"  \033[2m(覆盖: {override})\033[0m" if override else ""
        print(f"  · {task.value:14} → {tier.value:6} {model}{mark}")


async def probe_tier(provider, tier: Tier) -> bool:
    t0 = time.monotonic()
    try:
        text, usage = await provider.chat(
            [{"role": "user", "content": CLASSIFY_PROMPT}],
            tier=tier,
            max_tokens=300,
        )
    except ModelError as exc:
        print(f"  {ERR} {tier.value:6} 调用失败：{exc}")
        return False
    elapsed = time.monotonic() - t0
    print(
        f"  {OK} {tier.value:6} out={usage.output:<5} reasoning={usage.reasoning:<5}"
        f" ({usage.reasoning_ratio:.0%})  {elapsed:.1f}s  答={text.strip()[:12]!r}"
    )
    return True


async def main() -> int:
    print("\n\033[1m主理人 Agent · 模型自检\033[0m\n")
    print("配置")
    print(f"  · OPENAI_BASE_URL = {settings.OPENAI_BASE_URL}")
    print(f"  · OPENAI_API_KEY  = {mask(settings.OPENAI_API_KEY)}")
    print(f"  · EMBEDDING_MODEL = {settings.EMBEDDING_MODEL}  dim={settings.EMBEDDING_DIM}")
    print(f"  · 档位            = pro:{settings.LLM_MODEL_PRO} "
          f"turbo:{settings.LLM_MODEL_TURBO} lite:{settings.LLM_MODEL_LITE}")
    print()

    provider = get_model_provider()
    if not provider.enabled:
        print(f"  {ERR} 未配置 OPENAI_API_KEY，跳过真机探测")
        print("     填写 apps/api/.env 后重跑；未配置时向量化与 LLM 会降级为规则版")
        return 1

    failed = False

    # ---------------- Embedding
    print("Embedding")
    try:
        vec = await provider.embed_one(CLASSIFY_PROMPT)
    except ModelError as exc:
        print(f"  {ERR} 调用失败：{exc}")
        return 1

    actual = len(vec)
    if actual == settings.EMBEDDING_DIM:
        print(f"  {OK} 维度一致 vector({actual})")
    else:
        failed = True
        print(f"  {ERR} 维度不一致：模型返回 {actual}，配置 EMBEDDING_DIM={settings.EMBEDDING_DIM}")
        print("     写入 news_items.embedding 会直接报错")
    if actual > 2000:
        print(f"  {WARN} {actual} 维 > pgvector 索引上限 2000 → 索引不创建，检索走全表扫描")

    # ---------------- 三档对比
    print("\n三档对比（同一简单分类任务）")
    for tier in (Tier.PRO, Tier.TURBO, Tier.LITE):
        if not await probe_tier(provider, tier):
            failed = True

    print_routing()

    # ---------------- 延迟提醒（这是实测中最容易被忽略的风险）
    print(f"\n  {WARN} 实测：核查类任务单次要 48~108s（pro 108s / turbo 56s / lite 48s）")
    print("     → 远超「检查单条 < 8s」目标。深度检查必须异步；默认路径仍走规则版。")

    print()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
