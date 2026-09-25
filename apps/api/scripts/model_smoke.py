"""模型连通性真机自检（不依赖数据库）。

    make models            # 或 cd apps/api && uv run python scripts/model_smoke.py

为什么单独一个脚本而不是放进 doctor：
doctor 要求"快且无副作用"（会进 CI 与部署前置），而模型探测要真实花钱、
耗时数秒。两者分开：doctor 只校验配置是否自洽，本脚本负责"真的能调通"。

检查项：
1. Embedding 维度是否与 EMBEDDING_DIM 一致（不一致 = 写入 PG 直接报错）
2. 对话是否可用，并单独统计 reasoning token（推理模型成本可观测的前提）

退出码：0 通过；1 失败。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.core.config import settings  # noqa: E402
from app.services.model_provider import ModelError, get_model_provider  # noqa: E402

OK, WARN, ERR = "\033[32m✓\033[0m", "\033[33m!\033[0m", "\033[31m✗\033[0m"

SAMPLE = "贵州茅台三季度营收增长，机构上调目标价"


def mask(key: str | None) -> str:
    if not key:
        return "(未配置)"
    return key[:8] + "***" + key[-4:] if len(key) > 16 else "***"


async def main() -> int:
    print("\n\033[1m主理人 Agent · 模型连通性自检\033[0m\n")
    print("配置")
    print(f"  · OPENAI_BASE_URL = {settings.OPENAI_BASE_URL}")
    print(f"  · OPENAI_API_KEY  = {mask(settings.OPENAI_API_KEY)}")
    print(f"  · LLM_MODEL       = {settings.LLM_MODEL}"
          f"{'  (推理模型)' if settings.LLM_IS_REASONING else ''}")
    print(f"  · EMBEDDING_MODEL = {settings.EMBEDDING_MODEL}"
          f"  dim={settings.EMBEDDING_DIM}")
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
        vec = await provider.embed_one(SAMPLE)
    except ModelError as exc:
        print(f"  {ERR} 调用失败：{exc}")
        return 1

    actual = len(vec)
    if actual == settings.EMBEDDING_DIM:
        print(f"  {OK} 维度一致 vector({actual})")
    else:
        failed = True
        print(f"  {ERR} 维度不一致：模型返回 {actual}，配置 EMBEDDING_DIM={settings.EMBEDDING_DIM}")
        print("     写入 news_items.embedding 会直接报错。请把 EMBEDDING_DIM 改为模型的真实维度")

    if actual > 2000:
        print(f"  {WARN} {actual} 维超过 pgvector 索引上限 2000 → 向量索引不会创建，"
              f"语义检索退化为全表扫描")
        print("     需要索引时：设 EMBEDDING_TRUNCATE_TO<=2000（统一截断，精度下降）或换模型")

    # ---------------- Chat
    print("\n对话")
    try:
        text, usage = await provider.chat(
            [{"role": "user", "content": "用一句话说明什么是降准"}],
            max_tokens=300,
        )
    except ModelError as exc:
        print(f"  {ERR} 调用失败：{exc}")
        return 1

    ratio = usage.reasoning / max(usage.output, 1)
    print(f"  {OK} 可用（{settings.LLM_MODEL}）")
    print(f"  · 输入 {usage.input} / 输出 {usage.output}，其中推理 {usage.reasoning}（{ratio:.0%}）")
    print(f"  · 回复：{text.strip()[:80]}…")

    if usage.reasoning > usage.output * 0.5:
        print(f"  {WARN} 推理 token 占比 {ratio:.0%} —— 此模型成本与延迟都高，"
              f"「打标 / 聚类」等简单任务不要用它（配置 LLM_MODEL_LIGHT）")

    print()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
