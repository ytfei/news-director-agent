"""打标与向量化。

分两条腿：
1. **规则版**（默认，零成本）：行业关键词 + simhash + 重要度评分
2. **模型版**（配置 OPENAI_API_KEY 后自动启用向量；LLM 打标由 ENRICH_USE_LLM 控制）

向量化走 `ModelProvider`（OpenAI 兼容协议），不直接依赖 SDK --
换供应商 / 私有化只改配置。模型不可用时**降级而不是失败**：
规则结果照常入库，embedding 留空，保证同步链路不被模型侧故障拖垮。

ScoutAgent（ingest_graph）上线后替换打标部分；表结构与 enrich_status 语义不变。
"""

from __future__ import annotations

import uuid

import structlog

from app.core.config import settings
from app.core.database import SessionLocal
from app.lib.hash import simhash64
from app.models.news import NewsItem
from app.services.model_provider import ModelError, Task, get_model_provider

log = structlog.get_logger()

# 极简行业关键词表：零成本兜底
INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "bank": ["银行", "信贷", "存款", "降准", "LPR"],
    "semiconductor": ["半导体", "芯片", "晶圆", "光刻", "存储芯片"],
    "new_energy": ["新能源", "光伏", "锂电", "储能", "风电"],
    "auto": ["汽车", "新能源车", "整车", "智驾"],
    "real_estate": ["房地产", "楼市", "住建", "房企"],
    "macro": ["GDP", "CPI", "PMI", "央行", "财政部", "降息"],
}

# 向量模型有输入长度上限，截断避免整批失败
EMBED_MAX_CHARS = 8000


def guess_industries(text: str) -> list[str]:
    return [k for k, words in INDUSTRY_KEYWORDS.items() if any(w in text for w in words)]


def guess_importance(item: NewsItem) -> float:
    """0.00~1.00 机器打分（规则版）。"""
    score = 0.3
    text = f"{item.title} {item.summary or ''}"
    if item.content_type == "announcement":
        score += 0.2
    elif item.content_type == "policy":
        score += 0.25
    elif item.content_type == "research_report":
        score += 0.1
    if item.entities:
        score += 0.1
    if any(w in text for w in ("央行", "国务院", "证监会", "发改委")):
        score += 0.2
    if len(item.content or "") > 2000:
        score += 0.05
    return round(min(score, 1.0), 2)


async def calc_embedding(text: str) -> list[float] | None:
    """调用向量模型。未配置 / 失败都返回 None（降级）。"""
    provider = get_model_provider()
    if not provider.enabled:
        return None
    try:
        return await provider.embed_one(text[:EMBED_MAX_CHARS])
    except ModelError as exc:
        log.warning("enrich.embedding_failed", error=str(exc)[:200])
        return None


async def llm_tag(text: str) -> list[str] | None:
    """用轻量模型抽行业标签。默认关闭（ENRICH_USE_LLM）。"""
    if not settings.ENRICH_USE_LLM:
        return None
    provider = get_model_provider()
    if not provider.enabled:
        return None

    allowed = ", ".join(INDUSTRY_KEYWORDS.keys())
    messages = [
        {
            "role": "system",
            "content": (
                "你是财经资讯分类助手。只输出 JSON：{\"industries\": [...]}。"
                f"industries 只能取自：{allowed}；无法确定就返回空数组。"
            ),
        },
        {"role": "user", "content": text[:2000]},
    ]
    try:
        # 分类属简单高频任务 → 路由到 turbo（实测 37 tokens / 2s）
        data, usage = await provider.chat_json(messages, task=Task.CLASSIFY)
    except ModelError as exc:
        log.warning("enrich.llm_tag_failed", error=str(exc)[:200])
        return None

    log.info("enrich.llm_tag", **usage.as_dict())
    if isinstance(data, dict):
        found = [x for x in data.get("industries", []) if x in INDUSTRY_KEYWORDS]
        return found or None
    return None


async def enrich_news_item(news_item_id: uuid.UUID) -> dict:
    async with SessionLocal() as session:
        item = await session.get(NewsItem, news_item_id)
        if item is None:
            return {"status": "not_found"}

        text = f"{item.title}\n{item.content or item.summary or ''}"

        industries = guess_industries(text)
        llm_industries = await llm_tag(text)
        if llm_industries:
            industries = sorted(set(industries) | set(llm_industries))
        if industries:
            item.industries = sorted(set(list(item.industries or []) + industries))
        if not item.simhash:
            item.simhash = simhash64(text)
        if not item.keywords:
            item.keywords = []

        item.importance = guess_importance(item)

        vec = await calc_embedding(text)
        if vec:
            item.embedding = vec

        item.enrich_status = "done"
        await session.commit()

        result = {
            "status": "done",
            "industries": industries,
            "importance": float(item.importance),
            "embedding_dim": len(vec) if vec else 0,
        }
        log.info("enrich.done", news_item_id=str(news_item_id), **result)
        return result


__all__ = [
    "enrich_news_item",
    "calc_embedding",
    "llm_tag",
    "guess_industries",
    "guess_importance",
]
