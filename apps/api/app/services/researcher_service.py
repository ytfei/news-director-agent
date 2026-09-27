"""事实基线生成（B2 · ResearcherAgent 的第一层）。

★ 定位（docs/05 §4.1 修订后的两层结构）：
    第一层 = **资讯级事实基线**：属于资讯，ingest 阶段异步预生成，跨用户/跨点评复用
    第二层 = **点评级核查**：属于用户，review 时按需补查，结果写 review_finding_evidence

这里只做第一层。把它放在 ingest 而不是 review 里，是三个硬约束共同决定的：
1. 延迟：review 时才跑会同步阻塞，< 8s 不可能达成；
2. 成本：事实检索从"每次检查 × 20 条"降为"每条资讯一次"，是最大的一项优化；
3. 一致性：同一资讯下不同用户的点评共享同一份基线，"交叉验证"口径才一致。

硬约束：**没有 evidence 的 claim 不允许标 verified**（仓储层还会再兜一次）。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.news import NewsItem
from app.models.review import FactCard
from app.repositories.review_repo import ReviewRepository
from app.services.model_provider import ModelError, Task, get_model_provider
from app.services.web_search import get_web_search

log = structlog.get_logger()

SYSTEM_PROMPT = """你是事实抽取助手，负责把一篇资讯拆成**可独立核实的原子事实断言**。

严格约束（违反任何一条都会让下游的事实核查失效）：
1. 每条断言只讲一个事实（主体 + 数值/时间/事件），能单独被核实；
2. **只抽取正文明确陈述的内容** —— 不推断、不补全、不预测、不加入你的背景知识；
3. status 判定：
   - verified：正文明确陈述，且有具体数值/时间/主体支撑；
   - unverifiable：含糊表述、转述他人观点、或缺乏可核实细节。
     拿不准就标 unverifiable，不要为了"显得有用"而标 verified；
4. snippet 必须是**正文里的原句**，是这条断言的证据。留空等于这条断言不可追溯；
5. open_questions：这篇资讯里**仍然无法确认**、会影响投资/判断的问题 ——
   这些问题决定了"哪些话不能说死"，对下游写作很重要；
6. related_symbols：涉及的公司与标的代码（如 600519.SH），没有就留空数组。"""

USER_TEMPLATE = """资讯标题：{title}
来源：{source}    发布时间：{published}

正文：
\"\"\"
{body}
\"\"\"

请输出 JSON：
{{"claims": [
   {{"claim": "原子事实断言", "status": "verified|unverifiable",
     "confidence": 0.9, "snippet": "正文原句"}}
 ],
 "open_questions": ["还无法确认的问题"],
 "related_symbols": ["600519.SH"]}}"""


def _as_evidence(item: NewsItem, snippet: str) -> list[dict]:
    """把资讯本身包装成 evidence。

    ★ 事实基线的第一份证据永远是"这条资讯自己" —— 它是可追溯的底线。
    网页检索（若启用）会在其后追加外部证据。
    """
    return [
        {
            "src": item.source_name or "unknown",
            "date": item.published_at.date().isoformat() if item.published_at else None,
            "snippet": (snippet or "")[:300],
            "url": item.url,
            "kind": "source_article",
        }
    ]


def _parse(payload: dict | list | None) -> tuple[list[dict], list[str], list[str]]:
    """解析模型输出。★ 脏数据一律跳过，不抛异常。"""
    if not isinstance(payload, dict):
        return [], [], []
    raw_claims = payload.get("claims")
    claims: list[dict] = []
    if isinstance(raw_claims, list):
        for c in raw_claims:
            if not isinstance(c, dict):
                continue
            text = (c.get("claim") or "").strip()
            if not text:
                continue
            status = (c.get("status") or "unverifiable").strip().lower()
            if status not in {"verified", "unverifiable", "contradicted"}:
                status = "unverifiable"
            try:
                confidence = max(0.0, min(1.0, float(c.get("confidence", 0.5))))
            except (TypeError, ValueError):
                confidence = 0.5
            claims.append(
                {
                    "claim": text[:500],
                    "status": status,
                    "confidence": confidence,
                    "snippet": (c.get("snippet") or "")[:300],
                }
            )
            if len(claims) >= settings.FACT_CARD_MAX_CLAIMS:
                break

    questions = [str(q)[:300] for q in (payload.get("open_questions") or []) if q][:8]
    symbols = [str(s)[:32] for s in (payload.get("related_symbols") or []) if s][:16]
    return claims, questions, symbols


async def _maybe_web_evidence(item: NewsItem, claims: list[dict]) -> None:
    """若启用网页检索，为前几条 verified 断言补充外部证据（B2-2 web_probe）。

    ★ 失败静默：没有检索能力只是少一条佐证，不该让基线生成失败。
    """
    search = get_web_search()
    if not search.enabled or not claims:
        return
    queries = [f"{item.title} {c['claim'][:40]}" for c in claims[:3] if c["claim"]]
    try:
        hits = await search.search_many(queries)
    except Exception as exc:  # noqa: BLE001
        log.warning("researcher.web_search_failed", error=str(exc)[:200])
        return
    if not hits:
        return
    extra = [
        {
            "src": h.get("source") or h.get("url") or "web",
            "date": h.get("published_at"),
            "snippet": (h.get("snippet") or "")[:300],
            "url": h.get("url"),
            "kind": "web_search",
        }
        for h in hits[:3]
    ]
    # 只追加给前几条：外部检索结果不保证与每条断言精确对应，全量挂载反而制造噪音
    for c in claims[:3]:
        c.setdefault("extra_evidence", []).extend(extra)


async def generate_fact_card(
    session: AsyncSession, news_item_id: uuid.UUID
) -> FactCard | None:
    """为一条资讯生成/刷新事实基线。返回 None 表示降级（模型不可用）。"""
    item = (
        await session.execute(select(NewsItem).where(NewsItem.id == news_item_id))
    ).scalar_one_or_none()
    if item is None:
        log.warning("researcher.news_not_found", news_item_id=str(news_item_id))
        return None

    provider = get_model_provider()
    if not provider.enabled:
        return None

    body = (item.content or item.summary or item.title or "")[:6000]
    if not body.strip():
        return None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                title=item.title,
                source=item.source_name or "未知来源",
                published=item.published_at.isoformat() if item.published_at else "未知",
                body=body,
            ),
        },
    ]

    try:
        payload, usage = await provider.chat_json(messages, task=Task.FACT_CHECK)
    except ModelError as exc:
        log.warning("researcher.llm_failed", news_item_id=str(news_item_id), error=str(exc)[:200])
        return None

    raw_claims, questions, symbols = _parse(payload)
    if not raw_claims:
        return None

    await _maybe_web_evidence(item, raw_claims)

    claims: list[dict] = []
    for c in raw_claims:
        evidence = _as_evidence(item, c.pop("snippet", ""))
        evidence.extend(c.pop("extra_evidence", []))
        # ★ 硬约束：无 evidence 不得标 verified（仓储层还有一道，这里先做）
        status = c["status"]
        if status == "verified" and not evidence:
            status = "unverifiable"
        claims.append({**c, "status": status, "evidence": evidence})

    repo = ReviewRepository(session)
    card = await repo.upsert_card(
        news_item_id,
        context_notes=None,
        related_symbols=symbols,
        open_questions=questions,
        model=f"fact-extract:{provider.model_for(provider.tier_for(Task.FACT_CHECK))}",
        claims=claims,
    )
    card.generated_at = datetime.now()
    card.status = "ready"
    await session.commit()

    log.info(
        "researcher.fact_card_done",
        news_item_id=str(news_item_id),
        claims=len(claims),
        questions=len(questions),
        **usage.as_dict(),
    )
    return card


async def generate_due_fact_cards(limit: int = 10) -> dict:
    """★ 只为「已被用户加为素材」的资讯补生成基线 —— 成本控制的关键决策。

    为什么不入库即全量预生成：库里有 1.5 万条资讯，全量跑一遍就是 1.5 万次
    LLM 调用，成本会直接吃掉全部收入（docs/01 §6「单位经济性必须为正」）。
    真正会被写点评的只是用户挑出来的那几十条 —— 只为这些生成，成本降几个数量级。
    """
    from app.models.material import Material

    generated = failed = 0
    async with SessionLocal() as session:
        stmt = (
            select(NewsItem.id)
            .join(Material, Material.news_item_id == NewsItem.id)
            .outerjoin(FactCard, FactCard.news_item_id == NewsItem.id)
            .where(FactCard.id.is_(None), Material.deleted_at.is_(None))
            .limit(limit)
        )
        ids = list((await session.execute(stmt)).scalars().all())

        for news_item_id in ids:
            try:
                card = await generate_fact_card(session, news_item_id)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning(
                    "researcher.due_failed", news_item_id=str(news_item_id), error=str(exc)[:200]
                )
                continue
            generated += 1 if card is not None else 0

    log.info("researcher.due_done", scanned=len(ids), generated=generated, failed=failed)
    return {"scanned": len(ids), "generated": generated, "failed": failed}


__all__ = ["generate_fact_card", "generate_due_fact_cards"]
