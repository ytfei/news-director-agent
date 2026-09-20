"""三轨检查规则的单测（不依赖数据库）。

规则版是临时实现，但 finding 的**结构与 severity 取向**是长期契约：
- compliance 高召回：命中红线词即 blocker
- logic 折中：绝对化断言 high / 以偏概全 medium
- fact 高精度：只报基线里能对上的冲突，或带单位却查不到出处的数值
"""

from __future__ import annotations

from app.models.enums import FactStatus, FindingSeverity, FindingStatus, ReportVerdict
from app.models.review import FactCardClaim, ReviewFinding
from app.repositories.review_repo import verdict_of
from app.services.review_service import (
    _rules_for,
    compliance_rules,
    fact_rules,
    logic_rules,
    summarize,
)


def _claim(claim: str, status: FactStatus, evidence=None) -> FactCardClaim:
    return FactCardClaim(
        card_id=None,  # type: ignore[arg-type]
        seq=1,
        claim=claim,
        status=status,
        confidence=0.9,
        evidence=evidence if evidence is not None else [{"src": "公告", "date": "2026-09-19"}],
    )


def test_compliance_hits_are_blockers():
    findings = compliance_rules("这家公司的估值体系就是骗局")
    assert len(findings) == 1
    assert findings[0].track.value == "compliance"
    assert findings[0].severity == FindingSeverity.blocker
    assert findings[0].quote == "骗局"
    assert "R-014" in findings[0].message


def test_logic_severity_tiers():
    high = logic_rules("因此股价必然下跌")
    assert [f.severity for f in high] == [FindingSeverity.high]

    medium = logic_rules("所有新兴市场都会受益")
    assert [f.severity for f in medium] == [FindingSeverity.medium]


def test_fact_ignores_when_no_baseline():
    """没有事实基线时不能凭猜测报错（高精度取向）。"""
    assert fact_rules("营收增长 30%，毛利率 20.4%", []) == []


def test_fact_flags_contradiction_and_unknown_number():
    claims = [
        _claim("2026 年上半年营业收入同比 +12.4%", FactStatus.verified),
        _claim("市场流传的营收增长 30% 为含税口径", FactStatus.contradicted),
        _claim("2026Q2 综合毛利率 20.4%", FactStatus.verified),
    ]
    body = "营收增长 30% 是假的，实际只有 12.4%，毛利率 20.4%，产能利用率 85%"
    findings = fact_rules(body, claims)

    # 1) 与 contradicted 断言冲突的数值 → high
    assert any(f.severity == FindingSeverity.high and f.quote == "30" for f in findings)
    # 2) 基线中未出现的带单位数值 → medium（提示补口径，不是错误）
    unknown = [f for f in findings if f.severity == FindingSeverity.medium]
    assert any("85%" in (f.quote or "") for f in unknown)
    # 3) 基线中出现过的数值不再报
    assert not any((f.quote or "").startswith("12.4") for f in findings)
    assert not any((f.quote or "").startswith("20.4") for f in findings)


def test_rules_dedup_and_cap():
    body = "必然上涨。必然上涨。必然上涨。" + "骗局" * 3
    findings = _rules_for(body, [])
    keys = [(f.track.value, f.quote) for f in findings]
    assert len(keys) == len(set(keys))
    assert len(findings) <= 20
    # blocker 排在最前
    assert findings[0].severity == FindingSeverity.blocker


def _finding(severity: FindingSeverity, status: FindingStatus = FindingStatus.open):
    return ReviewFinding(
        report_id=None,  # type: ignore[arg-type]
        track=None,  # type: ignore[arg-type]
        severity=severity,
        status=status,
        message="x",
    )


def test_verdict_derivation():
    assert verdict_of([]) == ReportVerdict.passed
    assert verdict_of([_finding(FindingSeverity.info)]) == ReportVerdict.passed
    assert verdict_of([_finding(FindingSeverity.medium)]) == ReportVerdict.needs_revision
    assert verdict_of([_finding(FindingSeverity.high)]) == ReportVerdict.needs_revision
    assert verdict_of([_finding(FindingSeverity.blocker)]) == ReportVerdict.blocked


def test_blocker_stops_blocking_after_resolution():
    """★ 处置后的 finding 不再参与 verdict —— 这是"改完就能写作"的关键。"""
    findings = [
        _finding(FindingSeverity.blocker, FindingStatus.accepted),
        _finding(FindingSeverity.medium, FindingStatus.open),
    ]
    assert verdict_of(findings) == ReportVerdict.needs_revision
    findings[1].status = FindingStatus.ignored
    assert verdict_of(findings) == ReportVerdict.passed


def test_summarize_counts_by_severity():
    text = summarize(
        ReportVerdict.needs_revision,
        [
            _finding(FindingSeverity.blocker),
            _finding(FindingSeverity.high),
            _finding(FindingSeverity.medium),
            _finding(FindingSeverity.info),
        ],
    )
    assert "红线 1" in text and "严重 1" in text
