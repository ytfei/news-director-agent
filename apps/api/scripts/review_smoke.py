"""检查引擎真机冒烟：一次跑通「事实基线 → 规则版 → 模型版 → 合并」四条链路。

用法：
    uv run python scripts/review_smoke.py
    uv run python scripts/review_smoke.py --news-id <uuid>   # 指定资讯生成事实基线

设计取舍：
- **不写业务数据**（素材/点评都不建），只写 `fact_cards`（幂等，本质是缓存）；
- 所以能反复跑，不会因为跑一次就污染一次库。

它回答三个问题：
1. 模型能不能用了？（无 key 会明确报降级原因）
2. 模型版相对规则版**多找到了什么**？（这是接模型的价值所在）
3. 一条事实基线要花多少 token？（决定要不要全量预生成）
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from app.core.database import SessionLocal
from app.models.news import NewsItem
from app.repositories.review_repo import ReviewRepository
from app.services import review_service
from app.services.researcher_service import generate_fact_card
from app.services.review_llm import THRESHOLDS, llm_review
from sqlalchemy import select

# 故意覆盖了三类问题：语义层荐股（规则词库抓不到）、绝对化断言、收益承诺
SAMPLE = "茅台三季报营收增长15%，业绩必然大涨，建议现在买入，稳赚不赔，这是毫无疑问的机会。"

OK = "  \033[32m✓\033[0m"
ERR = "  \033[31m✗\033[0m"
WARN = "  \033[33m!\033[0m"


def show(drafts, label: str) -> None:
    print(f"\n{label}（{len(drafts)} 条）")
    for d in drafts:
        conf = f" conf={d.confidence:.2f}" if d.confidence is not None else ""
        rule = f" {d.rule_code}" if d.rule_code else ""
        print(f"    [{d.track.value:10} {d.severity.value:8}]{conf}{rule} {d.quote!r}")
        print(f"        {d.message[:72]}")


async def main(news_id: uuid.UUID | None) -> int:
    print("=" * 78)
    print("检查引擎真机冒烟")
    print("=" * 78)
    print(f"三轨阈值：{THRESHOLDS}")
    print(f"点评样本：{SAMPLE}")

    failed = False

    # ---------- 1. 事实基线（B2）----------
    print("\n[1] 事实基线生成（B2 · ResearcherAgent 第一层）")
    async with SessionLocal() as session:
        if news_id is None:
            row = (
                await session.execute(
                    select(NewsItem)
                    .where(NewsItem.content.isnot(None))
                    .order_by(NewsItem.published_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        else:
            row = await session.get(NewsItem, news_id)

        if row is None:
            print(f"{WARN} 库里没有带正文的资讯，跳过（先跑一次同步）")
            claims = []
        else:
            print(f"  资讯：{row.title[:56]}")
            card = await generate_fact_card(session, row.id)
            if card is None:
                print(f"{WARN} 事实基线未生成（模型不可用为预期降级）")
                claims = []
            else:
                claims = await ReviewRepository(session).claims_of(card.id)
                print(f"{OK} 事实基线已生成：{len(claims)} 条断言")
                for c in claims[:3]:
                    print(f"    [{c.status.value}] {c.claim[:60]}")

    # ---------- 2. 规则版 ----------
    print("\n[2] 规则版（零延迟零成本基线）")
    rule_drafts = review_service._rules_for(SAMPLE, claims)
    show(rule_drafts, "规则版 findings")

    # ---------- 3. 模型版 ----------
    print("\n[3] 模型版（B1 · 一次调用返回三轨）")
    llm_findings, usage, err = await llm_review(body=SAMPLE, title="贵州茅台三季报", claims=claims)
    if err:
        print(f"{WARN} 模型降级：{err}")
    else:
        print(f"{OK} 调用成功：{usage.total} tokens（reasoning {usage.reasoning}）")
    llm_drafts = review_service._from_llm(llm_findings, claims, SAMPLE)
    show(llm_drafts, "模型版 findings（已过阈值）")

    # ---------- 4. 合并与增量 ----------
    print("\n[4] 合并（规则保底 + 模型增强）")
    merged = review_service._merge(rule_drafts, llm_drafts)
    show(merged, "合并后 findings")

    rule_keys = {(d.track.value, d.quote) for d in rule_drafts}
    added = [d for d in merged if (d.track.value, d.quote) not in rule_keys]
    print(f"\n{OK} 模型版相对规则版的增量：{len(added)} 条")
    for d in added:
        print(f"    + [{d.track.value}/{d.severity.value}] {d.quote!r} —— {d.message[:56]}")

    if not llm_findings and not err:
        print(f"{WARN} 模型没有报出任何问题：检查样本或阈值配置")
        failed = True

    print("\n" + "=" * 78)
    print("结论：" + ("有问题需要检查" if failed else "链路通畅"))
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="检查引擎真机冒烟")
    parser.add_argument("--news-id", type=uuid.UUID, default=None, help="指定资讯生成事实基线")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.news_id)))
