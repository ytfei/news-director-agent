"""三轨检查（模型版）的纯逻辑测试。

★ 刻意不碰真实 LLM：模型调用慢（单条 48~108s）且非确定，
  放进集成测试会让整套从 110s 涨到 330s 且结果不稳定 —— 已经踩过一次。

这里只测**最容易写错**的解析与阈值部分：
- 脏数据能不能扛住（模型返回非法 JSON 结构是常态）
- quote 是否真是正文子串（对不上前端就无法划词，这条 finding 等于废了）
- 三轨阈值是不是真的分开了（统一阈值会让两个验收指标互斥）
"""

from __future__ import annotations

import pytest
from app.models.enums import FindingSeverity, FindingTrack
from app.repositories.review_repo import verdict_of
from app.services import review_service
from app.services.review_llm import (
    THRESHOLDS,
    LlmFinding,
    apply_thresholds,
    parse_findings,
)

BODY = "茅台三季报营收增长15%，业绩必然大涨，建议现在买入，稳赚不赔。"


def _f(track: str, severity: str, confidence: float, quote: str = "必然") -> LlmFinding:
    return LlmFinding(
        track=FindingTrack(track),
        severity=FindingSeverity(severity),
        message="测试",
        quote=quote,
        confidence=confidence,
    )


def test_parse_skips_dirty_payload() -> None:
    """模型返回什么都要扛住，不能抛异常。"""
    assert parse_findings(None, BODY) == []
    assert parse_findings([], BODY) == []
    assert parse_findings({"findings": "not-a-list"}, BODY) == []

    out = parse_findings(
        {
            "findings": [
                {"track": "fact", "severity": "high", "message": "有效"},
                {"track": "unknown_track", "severity": "high", "message": "轨道非法"},
                {"track": "fact", "severity": "oh_no", "message": "严重度非法"},
                {"track": "fact", "severity": "high", "message": ""},  # 空 message
                "not-a-dict",
            ]
        },
        BODY,
    )
    assert len(out) == 1
    assert out[0].message == "有效"


def test_quote_must_be_exact_substring() -> None:
    """★ quote 必须是正文原样子串，否则前端无法划词定位。"""
    out = parse_findings(
        {
            "findings": [
                {"track": "logic", "severity": "high", "message": "a", "quote": "必然"},
                # 模型改写过的 quote：对不上就置空，而不是带着错误 span 落库
                {"track": "logic", "severity": "high", "message": "b", "quote": "必然会大涨！"},
            ]
        },
        BODY,
    )
    assert out[0].quote == "必然"
    assert out[1].quote is None


def test_confidence_is_clamped() -> None:
    out = parse_findings(
        {
            "findings": [
                {"track": "fact", "severity": "high", "message": "x", "confidence": 5},
                {"track": "fact", "severity": "high", "message": "y", "confidence": -1},
                {"track": "fact", "severity": "high", "message": "z", "confidence": "abc"},
            ]
        },
        BODY,
    )
    assert [f.confidence for f in out] == [1.0, 0.0, 0.5]


def test_thresholds_differ_per_track() -> None:
    """★ 核心：fact 高精度（宁可漏报）、compliance 高召回（宁可误报）。"""
    assert THRESHOLDS["fact"] > THRESHOLDS["compliance"]
    assert THRESHOLDS["fact"] > THRESHOLDS["logic"] > THRESHOLDS["compliance"]

    findings = [
        _f("compliance", "blocker", 0.40),  # 过（阈值 0.35）
        _f("fact", "high", 0.40),  # 不过（阈值 0.70）
        _f("logic", "high", 0.40),  # 不过（阈值 0.55）
    ]
    kept = {f.track.value for f in apply_thresholds(findings)}
    assert kept == {"compliance"}, "同一置信度下，只有低阈值的 compliance 轨应保留"


def test_merge_keeps_most_severe_on_conflict() -> None:
    """规则版与模型版报同一处时，保留更严重的那个。"""
    rule = [
        review_service.FindingDraft(
            track=FindingTrack.compliance,
            severity=FindingSeverity.medium,
            message="规则版",
            quote="必然",
        )
    ]
    llm = [
        review_service.FindingDraft(
            track=FindingTrack.compliance,
            severity=FindingSeverity.blocker,
            message="模型版",
            quote="必然",
            confidence=0.9,
        )
    ]
    merged = review_service._merge(rule, llm)
    assert len(merged) == 1
    assert merged[0].severity == FindingSeverity.blocker
    assert merged[0].message == "模型版"


def test_merge_dedupes_substring_quotes() -> None:
    """★ 两版 quote 粒度不同是常态：规则版「必然」vs 模型版「业绩必然大涨」。

    只做精确匹配会并列出两条，用户看到的是重复噪音。
    """
    rule = [
        review_service.FindingDraft(
            track=FindingTrack.logic, severity=FindingSeverity.high, message="规则版", quote="必然"
        )
    ]
    llm = [
        review_service.FindingDraft(
            track=FindingTrack.logic,
            severity=FindingSeverity.blocker,
            message="模型版",
            quote="业绩必然大涨",
            confidence=0.9,
        )
    ]
    merged = review_service._merge(rule, llm)
    assert len(merged) == 1, "子串包含的 quote 应视为同一问题"
    assert merged[0].severity == FindingSeverity.blocker


def test_merge_result_drives_verdict() -> None:
    """合并结果要能正确派生 verdict（blocker → blocked）。"""
    drafts = [
        review_service.FindingDraft(
            track=FindingTrack.compliance, severity=FindingSeverity.blocker, message="红线"
        )
    ]
    models = [d.to_model(BODY) for d in drafts]
    assert verdict_of(models).value == "blocked"


def test_cost_of_defaults_to_zero() -> None:
    """费率未配置时不应产出金额（避免编造单价）。"""
    assert review_service.cost_of(1000, 1000) == 0.0


@pytest.mark.parametrize("track", ["fact", "logic", "compliance"])
def test_every_track_has_threshold(track: str) -> None:
    assert 0.0 <= THRESHOLDS[track] <= 1.0
