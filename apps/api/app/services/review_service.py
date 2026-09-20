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

from app.models.agent import AgentRun
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
from app.models.review import FactCardClaim, ReviewFinding, ReviewReport
from app.repositories.review_repo import ReviewRepository, verdict_of

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


async def run_review(
    session: AsyncSession,
    user_id: uuid.UUID,
    pairs: list[tuple[Material, Annotation]],
) -> dict:
    """对一批（素材, 点评）执行三轨检查并落库。

    同步执行：M2 的规则版足够快；接 ReviewerAgent 后改为 arq 任务 + SSE 推送，
    API 形状（返回 run_id 与 reports）保持不变。
    """
    repo = ReviewRepository(session)
    run = AgentRun(
        user_id=user_id,
        graph=RunGraph.review,
        status=RunStatus.running,
        thread_id=str(uuid.uuid4()),
        input={"material_ids": [str(m.id) for m, _ in pairs]},
        model="rules-v1",
    )
    session.add(run)
    await session.flush()
    run.started_at = datetime.now()

    reports: list[ReviewReport] = []
    skipped: list[uuid.UUID] = []

    for material, annotation in pairs:
        if not (annotation.body or "").strip():
            skipped.append(material.id)
            continue
        card = await repo.get_card(material.news_item_id)
        claims = await repo.claims_of(card.id) if card else []

        # 历史驳回：「已确认不是问题」的同一问题不再重复报
        dismissed = await repo.dismissed_signatures(annotation.id)
        drafts = [
            d
            for d in _rules_for(annotation.body, claims)
            if (d.track.value, d.quote or "") not in dismissed
        ]
        report = await repo.create_report(
            user_id=user_id,
            annotation_id=annotation.id,
            annotation_version_no=annotation.current_version_no,
            run_id=run.id,
        )
        await repo.add_findings(report, [d.to_model(annotation.body) for d in drafts])
        findings = await repo.findings_of(report.id)
        report.summary = summarize(report.verdict, findings)

        # ★ blocker 未处置 → annotation=blocked，禁止进入写作
        status = {
            ReportVerdict.passed: AnnotationStatus.passed,
            ReportVerdict.needs_revision: AnnotationStatus.needs_revision,
            ReportVerdict.blocked: AnnotationStatus.blocked,
        }[report.verdict]
        annotation.status = status
        annotation.last_checked_at = datetime.now()
        reports.append(report)

    run.status = RunStatus.succeeded
    run.finished_at = datetime.now()
    run.output = {
        "reports": len(reports),
        "skipped": [str(x) for x in skipped],
        "verdicts": {
            v.value: sum(1 for r in reports if r.verdict == v) for v in ReportVerdict
        },
    }
    await session.commit()

    log.info("review.finished", run_id=str(run.id), reports=len(reports), skipped=len(skipped))
    return {
        "run_id": run.id,
        "reports": reports,
        "skipped_material_ids": skipped,
        "verdict_of": lambda r: r.verdict,
    }


def recompute(report: ReviewReport, findings: list[ReviewFinding]) -> ReportVerdict:
    return verdict_of(findings)


__all__ = [
    "run_review",
    "recompute",
    "compliance_rules",
    "logic_rules",
    "fact_rules",
    "summarize",
    "REDLINES",
]
