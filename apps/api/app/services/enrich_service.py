"""打标与向量化（M1 规则版）。

ScoutAgent（ingest_graph）上线后替换本实现；表结构与 enrich_status 语义不变。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog

from app.core.database import SessionLocal
from app.lib.hash import simhash64
from app.models.news import NewsItem

log = structlog.get_logger()

# 极简行业关键词表：M1 够用，后续交给模型
INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "bank": ["银行", "信贷", "存款", "降准", "LPR"],
    "semiconductor": ["半导体", "芯片", "晶圆", "光刻", "存储芯片"],
    "new_energy": ["新能源", "光伏", "锂电", "储能", "风电"],
    "auto": ["汽车", "新能源车", "整车", "智驾"],
    "real_estate": ["房地产", "楼市", "住建", "房企"],
    "macro": ["GDP", "CPI", "PMI", "央行", "财政部", "降息"],
}


def guess_industries(text: str) -> list[str]:
    found = [k for k, words in INDUSTRY_KEYWORDS.items() if any(w in text for w in words)]
    return found


def guess_importance(item: NewsItem) -> float:
    """0.00~1.00 机器打分（M1 规则版）。"""
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


async def enrich_news_item(news_item_id: uuid.UUID) -> dict:
    async with SessionLocal() as session:
        item = await session.get(NewsItem, news_item_id)
        if item is None:
            return {"status": "not_found"}

        text = f"{item.title}\n{item.content or item.summary or ''}"
        industries = guess_industries(text)
        if industries:
            item.industries = sorted(set(list(item.industries or []) + industries))
        if not item.simhash:
            item.simhash = simhash64(text)
        if not item.keywords:
            item.keywords = []
        item.importance = guess_importance(item)
        item.enrich_status = "done"
        await session.commit()

        log.info("enrich.done", news_item_id=str(news_item_id), industries=industries)
        return {"status": "done", "industries": industries, "importance": float(item.importance)}


__all__ = ["enrich_news_item", "guess_industries", "guess_importance", "datetime"]
