"""tushare 快讯连接器单测（除特别标注外都不依赖数据库、不联网）。

这些用例锁定的是**契约**，不是实现：
- 官方规格（doc 143）的字段映射与时间格式
- 幂等键的稳定性（跨次拉取同一条 → 同一个 id；上游多回无关字段 → 依然同一个 id）
- 渠道身份来自 src 映射表（上游返回里没有 src，读 payload 只会拿到兜底值）
- 多来源的进度互不拖累
- 触顶（1500）细分窗口而不是静默丢数据
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.connectors.base import RawItem, SyncCursor
from app.connectors.spec import DEFAULT_TZ, parse_time
from app.connectors.tushare.flash import (
    FLASH_WINDOW,
    TushareFlashConnector,
)
from app.connectors.tushare.specs import NEWS_MAX_ROWS, NEWS_SPEC, SRC_LABELS, src_label

TZ = ZoneInfo(DEFAULT_TZ)


def make_raw(**payload) -> RawItem:
    body = {"title": "央行宣布降准0.25个百分点", "content": "具体内容", "datetime": "2026-09-18 10:30:00"}
    body.update(payload)
    return RawItem(
        external_id=NEWS_SPEC.build_external_id(body, {"channel": "cls"}),
        payload=body,
        fetched_at=datetime(2026, 9, 18, 11, 0, tzinfo=TZ),
        channel="cls",
    )


# ---------------------------------------------------------------- 规格映射


def test_src_labels_cover_official_sources():
    """9 个官方来源都要有中文名 —— 否则渠道身份会退化成英文标识。"""
    assert set(SRC_LABELS) == {
        "sina",
        "wallstreetcn",
        "10jqka",
        "eastmoney",
        "yuncaijing",
        "fenghuang",
        "jinrongjie",
        "cls",
        "yicai",
    }
    assert src_label("cls") == "财联社"
    assert src_label("unknown-src") == "unknown-src"  # 未知来源透传，不静默丢弃
    assert src_label(None) is None


def test_spec_maps_official_fields():
    """doc 143 的输出只有 datetime / content / title / channels。"""
    conn = TushareFlashConnector(config={"srcs": ["cls"]})
    draft = conn.normalize(make_raw(channels="宏观"))

    assert draft.title == "央行宣布降准0.25个百分点"
    assert draft.content == "具体内容"
    assert draft.source_name == "财联社"  # ← 不是 payload 里的 src，而是渠道映射
    assert draft.attributes["channels"] == "宏观"  # ← 上游分类进 attributes 通道
    assert draft.content_type.value == "flash"
    assert draft.kind.value == "news"
    assert draft.provenance.api == "news"
    assert draft.provenance.channel == "cls"
    assert draft.provenance.channel_label == "财联社"
    assert draft.has_metrics is False


def test_channel_identity_not_lost_from_payload_src():
    """回归：旧实现取 `p.get("src")`，而上游返回里根本没有 src，
    导致 9 个来源的 source_name 全部退化成 "Tushare"。"""
    conn = TushareFlashConnector(config={"srcs": ["cls", "sina"]})
    a = conn.normalize(make_raw())
    b = conn.normalize(make_raw().model_copy(update={"channel": "sina"}))

    assert a.source_name == "财联社"
    assert b.source_name == "新浪财经"
    assert "Tushare" not in {a.source_name, b.source_name}


# ---------------------------------------------------------------- 时间语义


@pytest.mark.parametrize(
    "raw_time",
    ["2026-09-18 10:30:00", "20260918 103000"],  # 官方格式 + 兼容格式
)
def test_time_is_tz_aware(raw_time):
    conn = TushareFlashConnector(config={"srcs": ["cls"]})
    draft = conn.normalize(make_raw(datetime=raw_time))
    assert draft.published_at == datetime(2026, 9, 18, 10, 30, tzinfo=TZ)
    # ★ 库里是 timestamptz：naive datetime 会被 PG 按会话时区隐式解释
    assert draft.published_at.tzinfo is not None


def test_unparsable_time_falls_back_to_fetched_at():
    conn = TushareFlashConnector(config={"srcs": ["cls"]})
    raw = make_raw(datetime="")
    draft = conn.normalize(raw)
    assert draft.published_at == raw.fetched_at


# ---------------------------------------------------------------- 幂等键


def test_external_id_is_stable_and_channel_scoped():
    """跨次拉取同一条 → 同一个 id；换渠道 → 不同 id；上游多回无关字段 → 依然同一个 id。"""
    base = {"title": "T", "content": "C", "datetime": "2026-09-18 10:30:00"}
    id_cls = NEWS_SPEC.build_external_id(base, {"channel": "cls"})
    id_cls_again = NEWS_SPEC.build_external_id(dict(base), {"channel": "cls"})
    id_sina = NEWS_SPEC.build_external_id(base, {"channel": "sina"})
    id_with_junk = NEWS_SPEC.build_external_id({**base, "extra_field": "上游新加的"}, {"channel": "cls"})

    assert id_cls == id_cls_again
    assert id_cls != id_sina, "不同来源的同一条快讯是两条原始记录（跨源合并发生在 content_hash 层）"
    assert id_cls == id_with_junk, "全字段 hash 会因无关字段变化产生新 id、重复占原始层"


# ---------------------------------------------------------------- 纯函数


def test_normalize_is_pure():
    conn = TushareFlashConnector(config={"srcs": ["cls"]})
    raw = make_raw()
    assert conn.normalize(raw) == conn.normalize(raw)


def test_missing_title_falls_back_to_content():
    """快讯经常只有 content 没有 title（tushare 返回 NaN）→ 展示标题退到正文摘要。"""
    conn = TushareFlashConnector(config={"srcs": ["cls"]})
    draft = conn.normalize(make_raw(title=None))
    assert draft.title is None
    assert draft.display_title == "具体内容"


# ---------------------------------------------------------------- 配置解析


@pytest.mark.parametrize(
    "config,expected",
    [
        ({"srcs": ["cls", "sina"]}, ["cls", "sina"]),
        ({"srcs": "cls"}, ["cls"]),  # 手写成字符串也要能用
        ({"src": "sina"}, ["sina"]),  # 兼容旧的单 src 配置
        ({"srcs": ["cls", "nope", "cls"]}, ["cls"]),  # 去掉未知值 + 去重
        ({}, []),  # 未配置 → 空（不做"没配就全都要"的兜底，避免白烧配额）
    ],
)
def test_srcs_config_parsing(config, expected):
    assert TushareFlashConnector(config=config).srcs == expected


def test_unknown_srcs_are_reported_not_silently_dropped():
    conn = TushareFlashConnector(config={"srcs": ["cls", "weibo"]})
    assert conn.srcs == ["cls"]
    assert conn.unknown_srcs == ["weibo"]


def test_capability_declares_config_schema():
    """能力声明必须带配置项 —— 前端靠它渲染来源多选（否则"表单动态渲染"是空话）。"""
    fields = {f.key: f for f in TushareFlashConnector.capability.config_schema}
    assert "srcs" in fields
    assert fields["srcs"].type == "multiselect"
    assert fields["srcs"].required is True
    assert {o["value"] for o in fields["srcs"].options} == set(SRC_LABELS)


# ---------------------------------------------------------------- 校验（不联网）


@pytest.mark.asyncio
async def test_validate_without_srcs_gives_actionable_message():
    conn = TushareFlashConnector(config={"srcs": ["weibo"]})
    conn.credentials = {"token": "fake"}
    ok, message = await conn.validate()
    assert ok is False
    assert "新闻来源" in message
    assert "weibo" in message  # 明确告诉用户哪个值不认


@pytest.mark.asyncio
async def test_validate_without_token():
    conn = TushareFlashConnector(config={"srcs": ["cls"]})
    conn.credentials = {}
    conn.config.pop("token", None)
    import app.connectors.tushare.base as base_mod

    original = base_mod.settings.TUSHARE_TOKEN
    base_mod.settings.TUSHARE_TOKEN = None
    try:
        ok, message = await conn.validate()
    finally:
        base_mod.settings.TUSHARE_TOKEN = original
    assert ok is False
    assert "token" in message


# ---------------------------------------------------------------- 探测


@pytest.mark.asyncio
async def test_probe_distinguishes_no_permission_from_empty(monkeypatch):
    """必须能分开「无权限（抛错）」与「区间为空（0 行不报错）」。"""
    conn = TushareFlashConnector(config={"srcs": ["cls", "sina", "10jqka"]})

    async def fake_query(src, start, end):
        if src == "sina":
            raise RuntimeError("抱歉，您没有接口访问权限")
        if src == "10jqka":
            return []
        return [{"title": "x"}]

    monkeypatch.setattr(conn, "_query_flash", fake_query)
    results = await conn.probe_srcs()

    assert results["cls"]["ok"] is True and results["cls"]["rows"] == 1
    assert results["sina"]["ok"] is False and "权限" in results["sina"]["reason"]
    assert results["10jqka"]["ok"] is False and "返回 0 条" in results["10jqka"]["reason"]
    # 面板文案要带上中文来源名，用户才看得懂
    assert results["cls"]["label"] == "财联社"


@pytest.mark.asyncio
async def test_empty_reason_prefers_per_source_diagnosis():
    conn = TushareFlashConnector(config={"srcs": ["cls"]})
    conn.probe_results = {
        "cls": {"ok": False, "rows": 0, "label": "财联社", "reason": "近 3 小时返回 0 条"}
    }
    reason = conn.empty_reason()
    assert reason and "财联社" in reason


# ---------------------------------------------------------------- 拉取


class _StubFlash(TushareFlashConnector):
    """把网络换成可控的假实现，用来验证窗口切分与多来源游标。"""

    def __init__(self, config, rows_by_span=None):
        super().__init__(config)
        self.credentials = {"token": "fake"}
        self.calls: list[tuple[str, datetime, datetime]] = []
        self.fail_srcs: set[str] = set()
        self.rows_by_span = rows_by_span or (
            lambda span: [{"title": "t", "content": "c", "datetime": "2026-09-18 10:30:00"}]
        )

    async def _query_flash(self, src, start, end):
        self.calls.append((src, start, end))
        if src in self.fail_srcs:
            raise RuntimeError("boom")
        return self.rows_by_span(end - start)


@pytest.mark.asyncio
async def test_truncation_splits_window_instead_of_dropping():
    """触顶 1500 条时必须细分窗口重拉，而不是当作正常结果丢掉剩余数据。"""

    def rows_by_span(span: timedelta):
        # 宽窗口（>15min）一律返回满额 → 触发细分；细分到 15min 后返回 1 条 → 收敛
        if span > timedelta(minutes=15):
            saturated = {"title": "saturated", "content": "c", "datetime": "2026-09-18 10:30:00"}
            return [dict(saturated) for _ in range(NEWS_MAX_ROWS)]
        return [{"title": "narrow", "content": "c", "datetime": "2026-09-18 10:30:00"}]

    conn = _StubFlash(config={"srcs": ["cls"]}, rows_by_span=rows_by_span)
    cursor = SyncCursor()
    start = datetime(2026, 9, 18, 10, 0, tzinfo=TZ)
    window = (start, start + FLASH_WINDOW)

    items = [item async for item in conn.fetch(cursor, window)]

    # 1h 触顶 → 2×30m 各触顶 → 4×15m 收敛，共 4 条窄窗口结果
    assert len(conn.calls) == 1 + 2 + 4, (
        f"细分次数不符：{[(_s, a.isoformat(), b.isoformat()) for _s, a, b in conn.calls]}"
    )
    assert len(items) == 4
    assert conn.failed_segments == [], "细分能收敛时不应记为丢数据"
    # 细分后必须仍在原窗口范围内，且覆盖完整（4 个 15min 子段无缝拼接）
    spans = sorted((seg_start, seg_end) for _src, seg_start, seg_end in conn.calls)
    assert min(s for s, _e in spans) == start and max(e for _s, e in spans) == window[1]
    for seg_start, seg_end in spans:
        assert start <= seg_start < seg_end <= window[1]


@pytest.mark.asyncio
async def test_failed_source_does_not_block_or_advance_others():
    """★ 多来源的核心保障：某个来源失败，既不拖累其他来源，也不推进自己的游标。"""
    conn = _StubFlash(config={"srcs": ["cls", "sina"]}, rows_by_span=lambda span: [
        {"title": "t", "content": "c", "datetime": "2026-09-18 10:30:00"}
    ])
    conn.fail_srcs = {"sina"}

    cursor = SyncCursor()
    start = datetime(2026, 9, 18, 10, 0, tzinfo=TZ)
    window = (start, start + FLASH_WINDOW)
    items = [item async for item in conn.fetch(cursor, window)]

    assert items and {i.channel for i in items} == {"cls"}
    src_cursors = cursor.payload["srcs"]
    assert src_cursors["cls"]["last_published_at"] == window[1].isoformat()
    assert "sina" not in src_cursors, "失败来源不能推进游标，否则下次会永久丢一段数据"
    assert len(conn.failed_segments) == 1
    assert conn.failed_segments[0]["api"] == "news"
    assert conn.failed_segments[0]["src"] == "sina"


@pytest.mark.asyncio
async def test_each_source_resumes_from_its_own_cursor():
    """一个来源落后时，从它自己的位置续拉 —— 而不是跟随连接器整体水位。"""
    conn = _StubFlash(config={"srcs": ["cls", "sina"]}, rows_by_span=lambda span: [])
    behind = datetime(2026, 9, 18, 8, 0, tzinfo=TZ)
    cursor = SyncCursor(payload={"srcs": {"cls": {"last_published_at": behind.isoformat()}}})

    start = datetime(2026, 9, 18, 10, 0, tzinfo=TZ)
    window = (start, start + FLASH_WINDOW)
    async for _ in conn.fetch(cursor, window):
        pass

    # 取每个来源的**第一次**调用（窗口是向前切的，最后一次必然落在窗口尾部）
    first_call: dict[str, datetime] = {}
    for src, seg_start, _seg_end in conn.calls:
        first_call.setdefault(src, seg_start)
    assert first_call["cls"] == behind, "有游标的来源应从自己的进度续拉（补上上次失败的那一段）"
    assert first_call["sina"] == start, "没有游标的来源从窗口起点开始"


@pytest.mark.asyncio
async def test_cursor_is_tz_aware_after_roundtrip():
    """游标存成 ISO 字符串，读回来必须仍是带时区的（否则会跟 tz-aware 窗口比较出错）。"""
    conn = _StubFlash(config={"srcs": ["cls"]}, rows_by_span=lambda span: [])
    cursor = SyncCursor()
    start = datetime(2026, 9, 18, 10, 0, tzinfo=TZ)
    async for _ in conn.fetch(cursor, (start, start + FLASH_WINDOW)):
        pass

    restored = conn._cursor_of(cursor, "cls")
    assert restored == start + FLASH_WINDOW
    assert restored.tzinfo is not None


def test_parse_time_used_by_cursor_is_strict():
    """游标解析不能靠猜：非法值返回 None，而不是悄悄变成 now()。"""
    assert parse_time("not-a-time") is None
    assert parse_time("2026-09-18T10:30:00+08:00") == datetime(2026, 9, 18, 10, 30, tzinfo=TZ)
