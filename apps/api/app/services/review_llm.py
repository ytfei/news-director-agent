"""三轨检查的模型版（B1）。

★ 为什么是"一次调用返回三轨"，而不是三轨各调一次：
    实测核查类任务单次 48~108s（turbo 3613 tokens / 56s）。
    三条轨道各调一次 = 3 倍延迟与 3 倍成本，而且三轨本质是同一段文本的
    不同视角，"分三次问"并不会更准。
    改为一次调用返回三轨结果，**后处理阶段再按 track 用不同阈值过滤** ——
    阈值分离的目标（fact 高精度 / compliance 高召回）照样达成。

★ 与规则版的关系是「增强」不是「替换」：
    规则版 = 高精度、零延迟、零成本（红线词库、数值冲突）
    模型版 = 补语义层（隐含的收益承诺、以偏概全、无出处的断言）
    合并时按 (track, quote) 去重，严重者优先。

★ 降级：模型不可用 / 返回非法 JSON / 超时 → 返回空列表 + 标记，
    规则版结果照常出报告，绝不因为模型挂了就让用户看不到检查。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from app.core.config import settings
from app.models.enums import FindingSeverity, FindingTrack
from app.services.model_provider import ModelError, Task, TokenUsage, get_model_provider

log = structlog.get_logger()

PROMPT_VERSION = settings.REVIEW_PROMPT_VERSION

# ★ 三轨阈值（docs/01 §4.2 C）：统一阈值下两个验收指标互斥，必须分开
THRESHOLDS: dict[str, float] = {
    FindingTrack.fact.value: settings.REVIEW_CONFIDENCE_FACT,             # 高精度，宁可漏报
    FindingTrack.compliance.value: settings.REVIEW_CONFIDENCE_COMPLIANCE,  # 高召回，宁可误报
    FindingTrack.logic.value: settings.REVIEW_CONFIDENCE_LOGIC,            # 折中
}

VALID_SEVERITY = {s.value for s in FindingSeverity}
VALID_TRACK = {t.value for t in FindingTrack}
MAX_FINDINGS = 12

SYSTEM_PROMPT = """你是财经内容主编，负责给「主理人观点点评」做发布前体检。

你要从三个轨道找问题，三个轨道的取向**不同**，这点至关重要：

1. compliance（合规）—— **宁可误报，不可漏报**
   漏报意味着法律风险（平台封号、监管处罚）。哪怕拿不准也要报出来。
   常见红线：荐股（点名具体股票并建议买卖）、收益承诺（稳赚/必涨/保证收益）、
   目标价、内幕信息暗示、未证实指控（骗局/造假/操纵）、贬损性定性（割韭菜）。
   命中即 blocker。

2. logic（逻辑）—— 折中
   绝对化断言（必然/绝对/一定会/毫无疑问）、以偏概全（所有/全部/唯一）、
   因果倒置、把相关性当因果、缺少边界条件。

3. fact（事实）—— **宁可漏报，不可误报**
   误报直接伤害用户对产品的信任。只报你能明确指出冲突或确实查不到出处的：
   - 与事实基线冲突的表述（口径、数值、时间、主体）
   - 带单位/数值却没有任何出处的断言
   拿不准就不报。

输出要求：
- quote 必须是**点评正文里原样出现的连续子串**，一字不差。找不到就留空字符串。
  这不是形式要求 —— 前端要靠它划词高亮和一键采纳，quote 对不上等于这条 finding 废了。
- suggestion 给出可直接替换的改写文本；给不出就留空。
- confidence 是你对自己这条判断的把握（0~1），会用于按轨道过滤，请诚实打分。
- claim_seq：若该问题与事实基线里某条断言相关，填它的 seq 序号，否则填 0。
- 没问题就返回空数组，不要为了凑数硬报。"""

USER_TEMPLATE = """资讯标题：{title}

事实基线（已核实的原子断言，seq 是序号）：
{claims}

待检查的点评正文：
\"\"\"
{body}
\"\"\"

请输出 JSON：
{{"findings": [
  {{"track": "compliance|logic|fact",
    "severity": "blocker|high|medium|low|info",
    "quote": "正文原样子串",
    "message": "问题说明（一句话，说清风险）",
    "suggestion": "可直接替换的改写文本",
    "confidence": 0.85,
    "rule_code": "R-030（compliance 轨填，其他轨空字符串）",
    "claim_seq": 0}}
]}}"""


@dataclass
class LlmFinding:
    """模型产出的原始 finding（尚未映射 claim_id / 尚未落库）。"""

    track: FindingTrack
    severity: FindingSeverity
    message: str
    quote: str | None = None
    suggestion: str | None = None
    confidence: float = 0.5
    rule_code: str | None = None
    claim_seq: int = 0
    evidence: list = field(default_factory=list)


def _norm_track(value: str) -> str | None:
    v = (value or "").strip().lower()
    return v if v in VALID_TRACK else None


def _norm_severity(value: str) -> FindingSeverity | None:
    v = (value or "").strip().lower()
    return FindingSeverity(v) if v in VALID_SEVERITY else None


def _clean_quote(quote: str | None, body: str) -> str | None:
    """★ 校验 quote 确实是正文的子串。

    模型偶尔会"改写"quote 或带上省略号，那样前端无法划词定位。
    对不上就置空（退化为整条点评级提示），而不是丢掉这条 finding。
    """
    if not quote or not body:
        return None
    q = quote.strip()
    return q if q in body else None


def parse_findings(payload: dict | list | None, body: str) -> list[LlmFinding]:
    """把模型返回的 JSON 解析成 LlmFinding。★ 任何脏数据都跳过，不抛异常。"""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("findings")
    if not isinstance(raw, list):
        return []

    out: list[LlmFinding] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        track = _norm_track(str(item.get("track", "")))
        severity = _norm_severity(str(item.get("severity", "")))
        message = (item.get("message") or "").strip()
        if not track or not severity or not message:
            continue
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        try:
            claim_seq = int(item.get("claim_seq") or 0)
        except (TypeError, ValueError):
            claim_seq = 0

        out.append(
            LlmFinding(
                track=FindingTrack(track),
                severity=severity,
                message=message[:500],
                quote=_clean_quote(item.get("quote"), body),
                suggestion=(item.get("suggestion") or "").strip() or None,
                confidence=confidence,
                rule_code=(item.get("rule_code") or "").strip() or None,
                claim_seq=max(0, claim_seq),
            )
        )
        if len(out) >= MAX_FINDINGS:
            break
    return out


def apply_thresholds(findings: list[LlmFinding]) -> list[LlmFinding]:
    """★ 阈值分离的核心：同一批结果，按 track 用不同门槛过滤。"""
    kept: list[LlmFinding] = []
    for f in findings:
        floor = THRESHOLDS.get(f.track.value, 0.5)
        if f.confidence < floor:
            log.debug(
                "review_llm.below_threshold",
                track=f.track.value,
                confidence=f.confidence,
                floor=floor,
            )
            continue
        kept.append(f)
    return kept


async def llm_review(
    *,
    body: str,
    title: str = "",
    claims: list | None = None,
) -> tuple[list[LlmFinding], TokenUsage, str | None]:
    """跑一次模型检查。返回 (findings, usage, error)。

    error 不为 None 表示降级了（调用方应照常出规则版报告）。
    """
    provider = get_model_provider()
    if not provider.enabled:
        return [], TokenUsage(), "模型未配置（OPENAI_API_KEY 缺失），跳过模型检查"

    claims = claims or []
    claims_text = "\n".join(
        f"[{i}] {c.claim}（状态：{c.status.value}，置信度 {float(c.confidence):.2f}）"
        for i, c in enumerate(claims, start=1)
    ) or "（暂无事实基线）"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                title=title or "（未知标题）",
                claims=claims_text,
                body=body[:4000],
            ),
        },
    ]

    try:
        payload, usage = await provider.chat_json(messages, task=Task.REVIEW)
    except ModelError as exc:
        log.warning("review_llm.failed", error=str(exc)[:200])
        return [], TokenUsage(), str(exc)[:200]

    findings = apply_thresholds(parse_findings(payload, body))
    log.info(
        "review_llm.done",
        findings=len(findings),
        **usage.as_dict(),
    )
    return findings, usage, None


__all__ = [
    "LlmFinding",
    "llm_review",
    "parse_findings",
    "apply_thresholds",
    "PROMPT_VERSION",
    "THRESHOLDS",
]
