"""三轨检查（规则版）。

接口与数据结构按最终形态定义（docs/01 §4.2 C），当前用规则实现，
后续换成 ReviewerAgent 时**不改表结构、不改接口**，只替换 `_rules_for`。

为什么三轨阈值必须分开（docs/01 §4.2 C 产品化要点）：
- fact：高精度（宁可漏报）→ 只报能在事实基线里对上的冲突/无出处数值
- compliance：高召回（宁可误报）→ 红线词库优先命中，命中即 blocker
- logic：折中 → 绝对化/以偏概全，high 或 medium
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent import AgentRun, UsageRecord
from app.models.enums import (
    AnnotationStatus,
    FindingSeverity,
    FindingStatus,
    FindingTrack,
    ReportVerdict,
    RunGraph,
    RunStatus,
)
from app.models.material import Annotation, Material
from app.models.news import NewsItem
from app.models.review import FactCardClaim, ReviewFinding, ReviewReport
from app.repositories.review_repo import ReviewRepository, verdict_of
from app.services.model_provider import Task, get_model_provider
from app.services.review_llm import PROMPT_VERSION, llm_review

log = structlog.get_logger()

# ---------------- 词表（v1 规则版；M2 迁入 compliance_rules 表） ----------------

REDLINES: dict[str, tuple[str, str]] = {
    "骗局": ("R-014", "未证实指控"),
    "造假": ("R-014", "未证实指控"),
    "操纵": ("R-014", "未证实指控"),
    "内幕": ("R-015", "内幕信息暗示"),
    "割韭菜": ("R-021", "贬损性定性"),
    "稳赚": ("R-030", "收益承诺"),
    "必涨": ("R-030", "收益承诺"),
    "必跌": ("R-030", "收益承诺"),
    "荐股": ("R-030", "荐股"),
    "目标价": ("R-030", "目标价"),
    "保证收益": ("R-030", "收益承诺"),
}

ABSOLUTE_HIGH = {"必然", "一定会", "绝对", "毫无疑问", "不可能", "必然是"}
ABSOLUTE_MEDIUM = {"所有", "全部", "唯一", "任何时候", "肯定是", "肯定能"}

NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|％|亿元|万元|亿|万|倍|个基点|bp)?")


@dataclass
class FindingDraft:
    track: FindingTrack
    severity: FindingSeverity
    message: str
    quote: str | None = None
    suggestion: str | None = None
    evidence: list | None = None
    # ★ 模型版才有；规则版留 None。用于按轨道调阈值与事后归因
    confidence: float | None = None
    rule_code: str | None = None
    claim_id: uuid.UUID | None = None

    def to_model(self, body: str) -> ReviewFinding:
        start, end = _span(body, self.quote)
        return ReviewFinding(
            track=self.track,
            severity=self.severity,
            # 显式给 open：status 是 server_default，未回读前 Python 侧为 None，
            # 会让 verdict_of 误判成"已处置"
            status=FindingStatus.open,
            span_start=start,
            span_end=end,
            quote=self.quote,
            message=self.message,
            suggestion=self.suggestion,
            evidence=self.evidence or [],
            confidence=self.confidence,
            rule_code=self.rule_code,
            claim_id=self.claim_id,
        )


def _span(body: str, quote: str | None) -> tuple[int, int]:
    if not quote:
        return 0, 0
    i = body.find(quote)
    return (i, i + len(quote)) if i >= 0 else (0, 0)


# ---------------- 三条轨道 ----------------


def compliance_rules(body: str) -> list[FindingDraft]:
    out: list[FindingDraft] = []
    for word, (code, kind) in REDLINES.items():
        if word in body:
            out.append(
                FindingDraft(
                    track=FindingTrack.compliance,
                    severity=FindingSeverity.blocker,
                    quote=word,
                    message=(
                        f"「{word}」命中合规红线 {code}（{kind}），"
                        "存在法律与平台限流风险，必须修改后才能进入写作。"
                    ),
                    suggestion=None,
                )
            )
    return out


def logic_rules(body: str) -> list[FindingDraft]:
    out: list[FindingDraft] = []
    for word in ABSOLUTE_HIGH:
        if word in body:
            out.append(
                FindingDraft(
                    track=FindingTrack.logic,
                    severity=FindingSeverity.high,
                    quote=word,
                    message=f"「{word}」属绝对化断言。因果判断需要边界条件，建议改为条件句。",
                    suggestion="若 X 条件成立，则倾向于…",
                )
            )
    for word in ABSOLUTE_MEDIUM:
        if word in body:
            out.append(
                FindingDraft(
                    track=FindingTrack.logic,
                    severity=FindingSeverity.medium,
                    quote=word,
                    message=f"「{word}」属以偏概全的表述，建议限定范围。",
                    suggestion="多数 / 在我关注的样本里…",
                )
            )
    return out


def fact_rules(body: str, claims: list[FactCardClaim]) -> list[FindingDraft]:
    """高精度取向：只报"基线里能对上"的冲突，或"带单位却查不到出处"的数值。"""
    out: list[FindingDraft] = []
    if not claims:
        return out

    known_numbers: set[str] = set()
    for c in claims:
        known_numbers.update(m.group(1) for m in NUMBER_RE.finditer(c.claim))

    # 1) 基线里标记为 contradicted 的断言，若其数字/关键词出现在点评中 → high
    for c in claims:
        if c.status.value != "contradicted":
            continue
        for num in {m.group(1) for m in NUMBER_RE.finditer(c.claim)}:
            if num in body:
                out.append(
                    FindingDraft(
                        track=FindingTrack.fact,
                        severity=FindingSeverity.high,
                        quote=num,
                        message=f"该数值与事实基线存在口径冲突：{c.claim}",
                        suggestion=None,
                        evidence=c.evidence,
                    )
                )
        # 备注：数值冲突只报 high，不报 blocker —— fact 轨道取向是高精度（宁可漏报）

    # 2) 点评里带单位的数值，若在基线中找不到，提示补口径（medium，不是错误）
    for m in NUMBER_RE.finditer(body):
        value, unit = m.group(1), m.group(2)
        if not unit:
            continue
        if value in known_numbers:
            continue
        out.append(
            FindingDraft(
                track=FindingTrack.fact,
                severity=FindingSeverity.medium,
                quote=m.group(0),
                message=f"「{m.group(0)}」未在本次事实基线中找到出处，建议补上口径与来源。",
                suggestion=f"{m.group(0)}（口径：__，来源：__）",
            )
        )
    return out


def _rules_for(
    body: str, claims: list[FactCardClaim]
) -> list[FindingDraft]:
    findings = compliance_rules(body) + logic_rules(body) + fact_rules(body, claims)
    # 去重（同一 quote + track 只留最严重的一条）并封顶，避免报告噪音
    dedup: dict[tuple[str, str], FindingDraft] = {}
    order = {s: i for i, s in enumerate(
        ["blocker", "high", "medium", "low", "info"]
    )}
    for f in findings:
        key = (f.track.value, f.quote or f.message[:20])
        old = dedup.get(key)
        if old is None or order[f.severity.value] < order[old.severity.value]:
            dedup[key] = f
    return sorted(dedup.values(), key=lambda f: order[f.severity.value])[:20]


def summarize(verdict: ReportVerdict, findings: list[ReviewFinding]) -> str:
    if not findings:
        return "未发现问题"
    blocker = sum(1 for f in findings if f.severity.value == "blocker")
    high = sum(1 for f in findings if f.severity.value == "high")
    medium = sum(1 for f in findings if f.severity.value == "medium")
    rest = len(findings) - blocker - high - medium
    head = {ReportVerdict.passed: "通过", ReportVerdict.needs_revision: "建议修改",
            ReportVerdict.blocked: "存在合规红线"}[verdict]
    return f"{head} · 红线 {blocker} / 严重 {high} / 中等 {medium} / 其他 {rest}"


# ---------------- 编排 ----------------

SEVERITY_RANK = {"blocker": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def cost_of(token_in: int, token_out: int) -> float:
    """按配置费率折算成本。

    ★ 费率默认 0（不猜单价）。Spike #7 实测后按供应商账单填
    `LLM_COST_PER_1K_*`，这里才会产出真实金额。
    """
    return (
        token_in / 1000 * settings.LLM_COST_PER_1K_INPUT
        + token_out / 1000 * settings.LLM_COST_PER_1K_OUTPUT
    )


def _from_llm(findings: list, claims: list, body: str) -> list[FindingDraft]:
    """模型 finding → FindingDraft，并把 claim_seq 映射成 claim_id。"""
    out: list[FindingDraft] = []
    for f in findings:
        claim_id = None
        # claim_seq 是模型看到的 1-based 序号，回指事实基线的具体断言
        if 0 < f.claim_seq <= len(claims):
            claim_id = claims[f.claim_seq - 1].id
        out.append(
            FindingDraft(
                track=f.track,
                severity=f.severity,
                message=f.message,
                quote=f.quote,
                suggestion=f.suggestion,
                evidence=f.evidence or None,
                confidence=f.confidence,
                rule_code=f.rule_code,
                claim_id=claim_id,
            )
        )
    return out


def _not_dismissed(
    drafts: list[FindingDraft], dismissed: set[tuple[str, str]]
) -> list[FindingDraft]:
    """历史驳回过滤：「这不算问题」的同一问题不再重复报。"""
    return [d for d in drafts if (d.track.value, d.quote or "") not in dismissed]


def _merge(*groups: list[FindingDraft]) -> list[FindingDraft]:
    """合并规则版与模型版：按 (track, quote) 去重，严重者优先，再封顶避免噪音。

    ★ 为什么要处理子串包含：两版的 quote 粒度天然不一致 ——
      规则版命中词「必然」，模型版引用整句「业绩必然大涨」。
      只做精确匹配的话，同一问题会并排列成两条，用户看到的是重复噪音。
    """
    dedup: dict[tuple[str, str], FindingDraft] = {}

    def _same_key(new: FindingDraft) -> tuple[str, str] | None:
        q_new = new.quote or ""
        for key, old in dedup.items():
            if key[0] != new.track.value:
                continue
            q_old = old.quote or ""
            if q_new and q_old and (q_new in q_old or q_old in q_new):
                return key
            # 都没有 quote 时退回 message 前缀比较
            if not q_new and not q_old and key[1] == new.message[:20]:
                return key
        return None

    for group in groups:
        for f in group:
            same = _same_key(f)
            if same is None:
                dedup[(f.track.value, f.quote or f.message[:20])] = f
            elif SEVERITY_RANK[f.severity.value] < SEVERITY_RANK[dedup[same].severity.value]:
                dedup[same] = f

    return sorted(dedup.values(), key=lambda f: SEVERITY_RANK[f.severity.value])[:20]


async def run_review(
    session: AsyncSession,
    user_id: uuid.UUID,
    pairs: list[tuple[Material, Annotation]],
    *,
    mode: str | None = None,
    use_cache: bool = True,
    run: AgentRun | None = None,
) -> dict:
    """对一批（素材, 点评）执行三轨检查并落库。

    run：外部已建好的 AgentRun（异步入口用，便于前端立刻拿到 run_id 轮询）；
         为 None 时内部新建。

    mode：
      rules  —— 纯规则（零延迟零成本，M2 现状）
      llm    —— 纯模型
      hybrid —— 规则保底 + 模型增强（**默认**）

    同步执行；异步入口见 `workers.tasks.review_annotations`（返回 202 + run_id）。
    """
    mode = (mode or settings.REVIEW_MODE).strip().lower()
    if mode not in {"rules", "llm", "hybrid"}:
        mode = "hybrid"

    provider = get_model_provider()
    use_llm = mode in {"llm", "hybrid"} and provider.enabled

    repo = ReviewRepository(session)
    if run is None:
        # 异步入口会先建好 run（queued）再交给 worker，这样前端能立刻拿到 run_id 轮询
        run = AgentRun(
            user_id=user_id,
            graph=RunGraph.review,
            status=RunStatus.running,
            thread_id=str(uuid.uuid4()),
            input={
                "material_ids": [str(m.id) for m, _ in pairs],
                "mode": mode,
                "prompt_version": PROMPT_VERSION,
            },
            model=f"{mode}:{PROMPT_VERSION}",
        )
        session.add(run)
        await session.flush()
    else:
        run.input = {
            "material_ids": [str(m.id) for m, _ in pairs],
            "mode": mode,
            "prompt_version": PROMPT_VERSION,
        }
        run.model = f"{mode}:{PROMPT_VERSION}"
    run.status = RunStatus.running
    run.started_at = datetime.now()

    reports: list[ReviewReport] = []
    skipped: list[uuid.UUID] = []
    cache_hits = 0
    budget_exceeded = False
    llm_errors: list[str] = []
    total_in = total_out = 0

    for material, annotation in pairs:
        body = annotation.body or ""
        if not body.strip():
            skipped.append(material.id)
            continue

        card = await repo.get_card(material.news_item_id)
        claims = await repo.claims_of(card.id) if card else []

        # ★ 报告缓存：同一「点评版本 + 提示词版本 + 模式」直接复用。
        #   没有它，用户每点一次检查都要重跑一遍 LLM（钱和时间的双重浪费）。
        if use_cache:
            cached = await repo.latest_report_of(annotation.id)
            if (
                cached is not None
                and cached.annotation_version_no == annotation.current_version_no
                and cached.prompt_version == PROMPT_VERSION
                and cached.mode == mode
            ):
                reports.append(cached)
                cache_hits += 1
                continue

        dismissed = await repo.dismissed_signatures(annotation.id)
        groups: list[list[FindingDraft]] = []

        if mode != "llm":
            groups.append(_not_dismissed(_rules_for(body, claims), dismissed))

        if use_llm and not budget_exceeded:
            news = await session.get(NewsItem, material.news_item_id)
            findings, usage, err = await llm_review(
                body=body,
                title=news.title if news else "",
                claims=claims,
            )
            total_in += usage.input
            total_out += usage.output
            if err:
                llm_errors.append(err)
            if total_in + total_out > settings.REVIEW_TOKEN_BUDGET:
                # ★ 超预算后退回规则版，而不是让账单失控
                budget_exceeded = True
                log.warning("review.budget_exceeded", tokens=total_in + total_out)
            groups.append(_not_dismissed(_from_llm(findings, claims, body), dismissed))

        drafts = _merge(*groups) if groups else []

        report = await repo.create_report(
            user_id=user_id,
            annotation_id=annotation.id,
            annotation_version_no=annotation.current_version_no,
            run_id=run.id,
        )
        report.mode = mode
        report.prompt_version = PROMPT_VERSION
        report.model = (
            provider.model_for(provider.tier_for(Task.REVIEW)) if use_llm else "rules-v1"
        )

        await repo.add_findings(report, [d.to_model(body) for d in drafts])
        findings = await repo.findings_of(report.id)
        report.summary = summarize(report.verdict, findings)

        # ★ blocker 未处置 → annotation=blocked，禁止进入写作
        annotation.status = {
            ReportVerdict.passed: AnnotationStatus.passed,
            ReportVerdict.needs_revision: AnnotationStatus.needs_revision,
            ReportVerdict.blocked: AnnotationStatus.blocked,
        }[report.verdict]
        annotation.last_checked_at = datetime.now()
        reports.append(report)

    run.status = RunStatus.succeeded
    run.finished_at = datetime.now()
    run.token_input = total_in
    run.token_output = total_out
    run.output = {
        "reports": len(reports),
        "cache_hits": cache_hits,
        "skipped": [str(x) for x in skipped],
        "budget_exceeded": budget_exceeded,
        "llm_errors": llm_errors[:3],
        "verdicts": {
            v.value: sum(1 for r in reports if r.verdict == v) for v in ReportVerdict
        },
    }

    # 成本台账：★ M1 就要有，是硬配额与定价的基础（docs/01 §6）
    if total_in or total_out:
        session.add(
            UsageRecord(
                user_id=user_id,
                run_id=run.id,
                category="review",
                model=run.model,
                token_input=total_in,
                token_output=total_out,
                cost_usd=cost_of(total_in, total_out),
            )
        )

    await session.commit()

    log.info(
        "review.finished",
        run_id=str(run.id),
        mode=mode,
        reports=len(reports),
        cache_hits=cache_hits,
        skipped=len(skipped),
        token_total=total_in + total_out,
        budget_exceeded=budget_exceeded,
    )
    return {
        "run_id": run.id,
        "reports": reports,
        "skipped_material_ids": skipped,
        "mode": mode,
        "cache_hits": cache_hits,
        "budget_exceeded": budget_exceeded,
        "token_total": total_in + total_out,
        "llm_errors": llm_errors[:3],
        "verdict_of": lambda r: r.verdict,
    }


def recompute(report: ReviewReport, findings: list[ReviewFinding]) -> ReportVerdict:
    return verdict_of(findings)


async def review_materials(
    user_id: uuid.UUID,
    material_ids: list[uuid.UUID],
    *,
    mode: str | None = None,
    run_id: uuid.UUID | None = None,
) -> dict:
    """★ 异步任务的入口：按素材 ID 检查，返回**可 JSON 序列化**的结果。

    为什么单独包一层：`run_review` 返回的是 ORM 对象与 lambda，arq 存不了 job result。
    这里开自己的 session（worker 进程没有请求上下文），并把结果转成纯 dict。
    """
    from app.core.database import SessionLocal
    from app.repositories.annotation_repo import AnnotationRepository

    async with SessionLocal() as session:
        pairs: list[tuple[Material, Annotation]] = []
        for mid in material_ids:
            material = await session.get(Material, mid)
            if material is None or material.user_id != user_id or material.deleted_at is not None:
                continue
            ann = await AnnotationRepository(session).get_by_material(mid)
            if ann is None:
                continue
            pairs.append((material, ann))

        existing_run = await session.get(AgentRun, run_id) if run_id else None

        if not pairs:
            # 没有可检查的内容：把 run 收尾，避免它永远停在 queued（僵尸 run）
            if existing_run is not None:
                existing_run.status = RunStatus.succeeded
                existing_run.finished_at = datetime.now()
                existing_run.output = {"reports": 0, "reason": "no_checkable_annotations"}
                await session.commit()
            return {
                "run_id": str(run_id) if run_id else None,
                "reports": [],
                "skipped_material_ids": [str(m) for m in material_ids],
                "mode": mode or settings.REVIEW_MODE,
                "cache_hits": 0,
                "budget_exceeded": False,
                "token_total": 0,
                "llm_errors": [],
            }

        result = await run_review(session, user_id, pairs, mode=mode, run=existing_run)
        reports = result["reports"]
        by_report: dict[uuid.UUID, list[ReviewFinding]] = {}
        for r in reports:
            by_report[r.id] = await ReviewRepository(session).findings_of(r.id)

        return {
            "run_id": str(result["run_id"]),
            "mode": result["mode"],
            "cache_hits": result["cache_hits"],
            "budget_exceeded": result["budget_exceeded"],
            "token_total": result["token_total"],
            "llm_errors": result["llm_errors"],
            "skipped_material_ids": [str(x) for x in result["skipped_material_ids"]],
            "reports": [
                {
                    "id": str(r.id),
                    "annotation_id": str(r.annotation_id),
                    "verdict": r.verdict.value,
                    "summary": r.summary,
                    "findings_count": r.findings_count,
                    "mode": r.mode,
                    "prompt_version": r.prompt_version,
                    "model": r.model,
                    "findings": [
                        {
                            "track": f.track.value,
                            "severity": f.severity.value,
                            "quote": f.quote,
                            "message": f.message,
                            "confidence": float(f.confidence) if f.confidence is not None else None,
                            "rule_code": f.rule_code,
                        }
                        for f in by_report.get(r.id, [])
                    ],
                }
                for r in reports
            ],
        }


__all__ = [
    "run_review",
    "recompute",
    "compliance_rules",
    "logic_rules",
    "fact_rules",
    "summarize",
    "REDLINES",
]
