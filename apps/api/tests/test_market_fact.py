"""数值事实链路单测：脏值归一 → 幂等键 → 落库分流 → 读取接口。

本期只接 tushare 快讯（不产出数值事实），所以这张表**没有数据源在写**。
为了不让它变成没人敢动的死代码，这里用两个层次证明它是活的：
1. 仓储层：直接调 `upsert_from_item`（sync_service 用的就是它），锁定幂等语义；
2. 端到端：注册一个**测试用的数值源连接器**，跑完整 run_sync，
   证明 ODS → 归一化 → DWD → 分流到事实表这条链路真的通。

端到端用的是 `custom_api.*` 前缀（`connector_type` 是 PG 原生枚举，
随便造一个 `test` 类型会因为不在枚举里而插不进去）。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from app.connectors.base import (
    ConnectorCapability,
    DataSourceConnector,
    Metric,
    NormalizedItem,
    Provenance,
    RawItem,
    SourceKind,
    SyncCursor,
)
from app.connectors.registry import register
from app.connectors.spec import DEFAULT_TZ, ChannelSpec, FieldRef, MetricSpec, to_decimal
from app.lib.hash import json_safe, payload_hash
from app.models.enums import ContentType
from app.models.market import MarketFact
from app.repositories.market_repo import MarketFactRepository, build_rows, fact_key
from sqlalchemy import delete, text

TZ = ZoneInfo(DEFAULT_TZ)


# ---------------------------------------------------------------- 脏值归一


def test_json_safe_removes_illegal_json_values():
    """★ 回归：tushare 走 pandas，缺失字段是 float('nan')。

    裸 `NaN` 不是合法 JSON，PostgreSQL 的 jsonb 直接拒收
    （invalid input syntax for type json: Token "NaN" is invalid）。
    真实快讯里"没有标题"的行很常见，所以这条不是理论问题。
    """
    import json

    row = {
        "title": float("nan"),
        "content": "正常内容",
        "score": float("inf"),
        "channels": None,
    }
    cleaned = json_safe(row)
    assert cleaned == {"title": None, "content": "正常内容", "score": None, "channels": None}
    # 必须能被严格 JSON 编码器接受（allow_nan=False 会把裸 NaN 变成异常）
    encoded = json.dumps(cleaned, allow_nan=False)
    assert "NaN" not in encoded and "Infinity" not in encoded
    assert json.loads(encoded) == cleaned


def test_json_safe_handles_pandas_and_numpy_scalars():
    assert json_safe(pd.NaT) is None, "NaT 是 datetime 的子类，先判类型名再判 isoformat"
    assert json_safe(pd.NA) is None
    assert json_safe(np.int64(5)) == 5
    assert json_safe(np.bool_(True)) is True
    assert json_safe(np.float32("nan")) is None
    assert json_safe(pd.Timestamp("2026-09-18 10:30:00")) == "2026-09-18T10:30:00"
    assert json_safe({"a": [np.float64("nan"), {"b": pd.NaT}]}) == {"a": [None, {"b": None}]}


def test_payload_hash_survives_nan_payload():
    """hash 与入库形态必须一致，否则 ODS 幂等判定会漂移。"""
    a = payload_hash({"title": float("nan"), "x": 1})
    b = payload_hash({"title": None, "x": 1})
    assert a == b
    assert a == payload_hash({"x": 1, "title": None})  # 键序无关


def test_to_decimal_does_not_guess():
    assert to_decimal("74000") == Decimal("74000")
    assert to_decimal(" 1,234.5 ") == Decimal("1234.5")
    assert to_decimal(None) is None
    assert to_decimal("") is None
    assert to_decimal("约 7 万") is None  # 不能瞎猜，宁可不出这条事实
    assert to_decimal(float("nan")) is None
    assert to_decimal(True) is None  # bool 不是数值


# ---------------------------------------------------------------- 幂等键


def _item(**kwargs) -> NormalizedItem:
    metrics = kwargs.pop("metrics", None)
    base = {
        "external_id": "item-1",
        "kind": SourceKind.market,
        "content_type": ContentType.market_data,
        "published_at": datetime(2026, 9, 18, 10, 0, tzinfo=TZ),
        "source_name": "测试源",
    }
    base.update(kwargs)
    if metrics is not None:
        base["metrics"] = metrics
    return NormalizedItem(**base)


def test_fact_key_ignores_value_but_respects_identity():
    """上游更正数值时应更新同一行，而不是产生第二条事实。"""
    m1 = Metric(name="碳酸锂均价", value="74000", unit="元/吨")
    m2 = Metric(name="碳酸锂均价", value="75000", unit="元/吨")
    assert fact_key("item-1", m1) == fact_key("item-1", m2)

    other_name = Metric(name="氢氧化锂均价", value="74000")
    other_item = fact_key("item-2", m1)
    assert fact_key("item-1", m1) != fact_key("item-1", other_name)
    assert fact_key("item-1", m1) != other_item


def test_fact_key_distinguishes_period_and_symbol():
    a = Metric(name="产量", value="1", ts_code="600519.SH", period="2026Q1")
    b = Metric(name="产量", value="1", ts_code="600519.SH", period="2026Q2")
    c = Metric(name="产量", value="1", ts_code="000001.SZ", period="2026Q1")
    assert fact_key("i", a) != fact_key("i", b)
    assert fact_key("i", a) != fact_key("i", c)


def test_build_rows_carries_provenance_and_sanitizes():
    cid = uuid.uuid4()
    item = _item(
        metrics=[Metric(name="碳酸锂均价", value="74000", unit="元/吨", attributes={"src": "smm"})],
        provenance=Provenance(connector_key="demo", api="quote", channel="smm"),
    )
    rows = build_rows(item, cid, raw_document_id=None, news_item_id=None)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "碳酸锂均价"
    assert row["value"] == Decimal("74000")
    assert row["unit"] == "元/吨"
    assert row["observed_at"] == item.published_at  # 没给观测时间就退到发布时间
    assert row["payload"]["provenance"]["channel"] == "smm"
    # payload 必须是 JSON 可序列化的（UUID 之类会在这里炸）
    import json

    json.dumps(row["payload"], allow_nan=False)
    json.dumps(row["attributes"], allow_nan=False)


def test_metric_spec_skips_non_numeric_and_keeps_numeric():
    """数值通道的取值声明：取不到数字就不产出这条事实（不猜）。"""
    spec = ChannelSpec(
        key="demo",
        kind=SourceKind.market,
        content_type=ContentType.market_data,
        time=FieldRef.of("ts"),
        time_formats=["%Y-%m-%d %H:%M:%S"],
        metric_specs=[
            MetricSpec(
                name=FieldRef.const("产能利用率"),
                value=FieldRef.of("util"),
                unit=FieldRef.const("%"),
            ),
            MetricSpec(name=FieldRef.const("缺失指标"), value=FieldRef.of("missing")),
        ],
    )
    item = spec.normalize(
        {"ts": "2026-09-18 10:00:00", "util": "85.5"},
        ctx={"fetched_at": datetime(2026, 9, 18, 11, 0, tzinfo=TZ)},
    )
    assert len(item.metrics) == 1
    assert item.metrics[0].name == "产能利用率"
    assert item.metrics[0].value == Decimal("85.5")
    assert item.metrics[0].unit == "%"
    assert item.has_metrics is True


# ---------------------------------------------------------------- 仓储（真库）


@pytest.mark.asyncio
async def test_upsert_is_idempotent_and_readable(db_session):

    connector_id = (
        await db_session.execute(text("select id from source_connectors limit 1"))
    ).scalar_one()

    marker = f"T{uuid.uuid4().hex[:8]}"
    item = _item(
        external_id=f"mkt-{marker}",
        metrics=[
            Metric(name=f"测试指标-{marker}", value="74000", unit="元/吨", ts_code=f"{marker}.SH"),
        ],
    )
    repo = MarketFactRepository(db_session)

    try:
        first = await repo.upsert_from_item(item, connector_id)
        await db_session.commit()
        assert first == 1

        # ★ 幂等：同一份 payload 重复落库不产生第二条
        again = await repo.upsert_from_item(item, connector_id)
        await db_session.commit()
        rows = await repo.list_facts(ts_code=f"{marker}.SH")
        assert len(rows) == 1
        assert again == 1  # 返回的是 RETURNING 行数，不是"新增"行数

        # 上游更正数值 → 更新同一行
        corrected = _item(
            external_id=f"mkt-{marker}",
            metrics=[
                Metric(name=f"测试指标-{marker}", value="75100", unit="元/吨", ts_code=f"{marker}.SH"),
            ],
        )
        await repo.upsert_from_item(corrected, connector_id)
        await db_session.commit()

        # 用**原始 SQL** 核对库里的真实值。
        # 这里不能复用 list_facts 返回的对象：sessionmaker 是 expire_on_commit=False，
        # 同一 session 内的身份映射会继续给出第一次读到的那份属性（值看起来没变）。
        # 生产代码每个请求一个新 session，不受影响；但这个坑值得在测试里挑明。
        stored = (
            await db_session.execute(
                text("select count(*), max(value) from market_facts where ts_code = :code"),
                {"code": f"{marker}.SH"},
            )
        ).one()
        assert stored[0] == 1, "更正数值不该产生第二条事实"
        assert stored[1] == Decimal("75100.000000"), "上游更正后应更新同一行的数值"

        # 顺带确认 ORM 层也能读到新值（refresh 后）
        await db_session.refresh(rows[0])
        assert rows[0].value == Decimal("75100.000000")
    finally:
        await db_session.execute(
            delete(MarketFact).where(
                MarketFact.external_id
                == fact_key(f"mkt-{marker}", item.metrics[0], item.published_at)
            )
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_repository_ignores_items_without_metrics(db_session):
    repo = MarketFactRepository(db_session)
    connector_id = (
        await db_session.execute(text("select id from source_connectors limit 1"))
    ).scalar_one()
    assert await repo.upsert_from_item(_item(external_id="no-metrics"), connector_id) == 0


# ---------------------------------------------------------------- 端到端：分流链路

FAKE_KEY = "custom_api.metric_demo"


@register
class _DemoMetricConnector(DataSourceConnector):
    """测试用数值源：证明「有 metrics → 落事实表」这条分流真的接通了。"""

    key = FAKE_KEY
    display_name = "测试数值源"
    capability = ConnectorCapability(
        content_types=["market_data"], requires_credentials=False, emits_metrics=True
    )

    def __init__(self, config, credentials=None):
        super().__init__(config, credentials)

    async def validate(self) -> tuple[bool, str]:
        return True, "ok"

    async def fetch(self, cursor: SyncCursor, window):
        yield RawItem(
            external_id=f"demo:{self.config.get('marker', 'x')}",
            payload={"symbol": self.config.get("symbol"), "price": "74000", "unit": "元/吨"},
            fetched_at=datetime(2026, 9, 18, 11, 0, tzinfo=TZ),
            content_type=ContentType.market_data,
            channel="demo",
        )

    def normalize(self, raw: RawItem) -> NormalizedItem:
        return NormalizedItem(
            external_id=raw.external_id,
            kind=SourceKind.market,
            content_type=ContentType.market_data,
            title=None,
            published_at=raw.fetched_at,
            source_name="测试数值源",
            metrics=[
                Metric(
                    name=f"碳酸锂均价-{self.config.get('marker')}",
                    value=raw.payload["price"],
                    unit=raw.payload["unit"],
                    ts_code=self.config.get("symbol"),
                )
            ],
            provenance=Provenance(connector_key=self.key, api="quote", channel="demo"),
        )


@pytest.mark.asyncio
async def test_run_sync_writes_metrics_to_fact_table(client):
    """端到端：run_sync 把带 metrics 的条目分流到 market_facts。"""
    marker = uuid.uuid4().hex[:8]
    symbol = f"{marker}.SH"

    # 清理同名测试连接器（同 owner 同 key 只允许一条活跃行）
    resp = await client.get("/api/v1/connectors")
    for c in resp.json():
        if c["key"] == FAKE_KEY:
            assert (await client.delete(f"/api/v1/connectors/{c['id']}")).status_code == 204

    resp = await client.post(
        "/api/v1/connectors",
        json={"key": FAKE_KEY, "config": {"marker": marker, "symbol": symbol}},
    )
    assert resp.status_code == 201, resp.text
    connector_id = resp.json()["id"]

    now = datetime.now(tz=TZ)
    resp = await client.post(
        f"/api/v1/connectors/{connector_id}/sync",
        json={"window_start": (now - datetime.resolution).isoformat(), "window_end": now.isoformat()},
    )
    assert resp.status_code == 202, resp.text
    stats = resp.json()
    assert stats["status"] == "success", stats
    assert stats["inserted"] == 1
    # ★ 分流的证据：文本条目落 news_items，同一条里的数值同时落 market_facts
    assert stats["facts_written"] == 1, stats

    # 读取接口能取到
    resp = await client.get("/api/v1/market/facts", params={"ts_code": symbol})
    assert resp.status_code == 200, resp.text
    facts = resp.json()
    assert len(facts) == 1
    fact = facts[0]
    assert fact["name"] == f"碳酸锂均价-{marker}"
    assert fact["value"] == 74000.0
    assert fact["value_exact"] == "74000.000000"
    assert fact["unit"] == "元/吨"
    assert fact["ts_code"] == symbol
    assert fact["news_item_id"], "事实必须能回溯到承载它的资讯条目"

    # 无标题的数值条目不违反 news_items.title NOT NULL（用指标名兜底）
    resp = await client.get(f"/api/v1/news/{fact['news_item_id']}")
    assert resp.status_code == 200

    resp = await client.get("/api/v1/market/facts/count")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

    # 清理：只删本次造的连接器与其事实
    assert (await client.delete(f"/api/v1/connectors/{connector_id}")).status_code == 204
    from app.core.database import SessionLocal

    async with SessionLocal() as s:
        await s.execute(
            delete(MarketFact).where(MarketFact.source_connector_id == uuid.UUID(connector_id))
        )
        await s.execute(
            text("delete from news_items where connector_id = :cid"),
            {"cid": uuid.UUID(connector_id)},
        )
        await s.commit()
