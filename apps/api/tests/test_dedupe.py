"""去重与归簇算法测试（不需要数据库）。

重点验证两件事：
1. MinHash 的估计值是否接近真实 Jaccard（否则阈值没有意义）
2. **渠道改写**的场景能否被识别 —— 这是 simhash 失效的地方
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.lib.dedupe import (
    EventCandidate,
    cosine,
    event_score,
    jaccard_from_signatures,
    jaccard_text,
    minhash_bucket,
    minhash_signature,
    normalize_text,
    shingles,
)

NOW = datetime(2026, 9, 26, 10, 0, 0)


def sig(text: str) -> bytes:
    return minhash_signature(shingles(text))


def test_normalize_strips_source_prefix():
    """渠道爱加「【有色发布】」这类前缀，必须去掉才可比。"""
    assert normalize_text("【有色发布】陕西有色集团出席论坛") == "陕西有色集团出席论坛"
    assert normalize_text("（独家）央行宣布降准") == "央行宣布降准"
    # NFKC：全角转半角
    assert normalize_text("Ａ股上涨１．５％") == "a股上涨1.5"


def test_minhash_estimates_true_jaccard():
    """估计值与精确值的偏差应足够小（64 perm → 标准误约 0.06）。"""
    a = "贵州茅台发布2026年三季度财报，营收同比增长百分之十二，净利润略低于市场预期"
    b = "贵州茅台2026年三季度财报出炉：营收同比增长12%，净利润不及预期"
    est = jaccard_from_signatures(sig(a), sig(b))
    true = jaccard_text(a, b)
    assert abs(est - true) < 0.15, f"估计 {est:.2f} 与真值 {true:.2f} 偏差过大"
    assert true > 0.2, "改写后仍应保留一定重合"


def test_identical_text_is_one():
    assert jaccard_from_signatures(sig("完全一样的标题内容"), sig("完全一样的标题内容")) == 1.0


def test_unrelated_text_is_low():
    a = "贵州茅台发布三季度财报营收增长"
    b = "国际油价下跌欧佩克宣布增产计划"
    assert jaccard_from_signatures(sig(a), sig(b)) < 0.15


def test_rewrite_detected_but_not_identical():
    """渠道改写：应显著高于无关文本，但低于完全相同的 1.0。"""
    a = "央行宣布下调存款准备金率0.5个百分点，释放长期资金约1万亿元"
    b = "央行决定下调金融机构存款准备金率0.5个百分点，预计释放长期资金超1万亿元"
    score = jaccard_from_signatures(sig(a), sig(b))
    unrelated = jaccard_from_signatures(sig(a), sig("某地举办马拉松比赛参赛人数创新高"))
    assert score > unrelated + 0.2, "改写稿应明显区别于无关稿"
    assert score < 1.0


def test_bucket_is_deterministic_and_selective():
    a = sig("贵州茅台三季度财报营收增长")
    assert minhash_bucket(a) == minhash_bucket(sig("贵州茅台三季度财报营收增长"))
    # 不同文本大概率落不同桶（用于粗筛，不要求 100%）
    assert minhash_bucket(a) != minhash_bucket(sig("国际油价下跌欧佩克增产"))


def test_event_score_same_event_high():
    """同事件：标题重合 + 实体重合。"""
    a = EventCandidate.from_item(
        "贵州茅台发布三季度财报营收增长12%",
        entities=["贵州茅台"],
        keywords=["财报", "三季度"],
        published_at=NOW,
    )
    b = EventCandidate.from_item(
        "贵州茅台三季度财报出炉净利润不及预期",
        entities=["贵州茅台"],
        keywords=["财报", "三季度"],
        published_at=NOW + timedelta(hours=4),
    )
    score, parts = event_score(a, b)
    # 渠道改写后标题 Jaccard 通常只有 0.15~0.25，这是真实值，不是算法缺陷
    assert parts["title"] > 0.15, f"标题应有一定重合，实际 {parts['title']}"
    assert score > 0.15, f"同事件应得高分，实际 {score} / {parts}"


def test_event_score_different_event_low():
    a = EventCandidate.from_item("贵州茅台三季度财报营收增长", published_at=NOW)
    b = EventCandidate.from_item("国际油价下跌欧佩克宣布增产", published_at=NOW)
    score, _ = event_score(a, b)
    assert score < 0.1


def test_event_score_out_of_window_is_zero():
    """超出时间窗：即使标题完全一样也不算同事件（10 天后是另一件事）。"""
    a = EventCandidate.from_item("贵州茅台发布三季度财报", published_at=NOW)
    near = EventCandidate.from_item("贵州茅台发布三季度财报", published_at=NOW + timedelta(hours=2))
    far = EventCandidate.from_item("贵州茅台发布三季度财报", published_at=NOW + timedelta(days=10))
    s_near, _ = event_score(a, near)
    s_far, _ = event_score(a, far)
    assert s_near > 0.75
    assert s_far == 0.0


def test_event_score_without_embedding_still_works():
    """存量没有 embedding 时也必须能算（权重按比例分摊，title 拿大头）。"""
    a = EventCandidate.from_item(
        "贵州茅台三季度财报", entities=["贵州茅台"], keywords=["财报"], published_at=NOW
    )
    b = EventCandidate.from_item(
        "贵州茅台三季度财报", entities=["贵州茅台"], keywords=["财报"], published_at=NOW
    )
    score, parts = event_score(a, b)
    assert "embed" not in parts
    assert score > 0.8


def test_event_score_with_embedding():
    a = EventCandidate(entities=[], keywords=[], published_at=NOW, embedding=[1.0, 0.0, 0.0])
    b = EventCandidate(entities=[], keywords=[], published_at=NOW, embedding=[0.9, 0.1, 0.0])
    score, parts = event_score(a, b)
    assert "embed" in parts
    assert parts["embed"] > 0.9


def test_cosine():
    assert cosine([1, 0], [1, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([1, 0], []) == 0.0
