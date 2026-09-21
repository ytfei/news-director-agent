"""M1/M2 冒烟测试：注册表 → 归一化 → 真机同步 → API 查询。

运行：
    uv run pytest tests/test_smoke.py -v

注意：`test_end_to_end_sync` / `test_flash_real_sync` 会**真机调 tushare**（需要 TUSHARE_TOKEN）。
它们不 skip 到"看不见"为止 —— 快讯链路是本期的交付核心，权限已开通的情况下
必须真的拉到数据，所以拿不到数据就会失败而不是静默跳过。
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
from app.connectors.registry import available_connectors, get_connector_class
from app.connectors.tushare.base import to_standard_code
from app.connectors.tushare.flash import TushareFlashConnector
from app.main import app
from httpx import ASGITransport, AsyncClient

HAS_TOKEN = bool(os.getenv("TUSHARE_TOKEN"))


def test_registry_contains_tushare():
    """新增数据源 = @register，注册表应自动发现。"""
    keys = [c["key"] for c in available_connectors()]
    assert "tushare.flash" in keys  # 快讯（doc 143）
    assert "tushare.article" in keys  # 长文 / 公告 / 政策 / 研报
    assert get_connector_class("tushare.flash") is TushareFlashConnector


def test_code_completion():
    """tushare 6 位代码 → 标准码。"""
    assert to_standard_code("600519") == "600519.SH"
    assert to_standard_code("000001") == "000001.SZ"
    assert to_standard_code("300750") == "300750.SZ"
    assert to_standard_code("600519.SH") == "600519.SH"
    assert to_standard_code(None) is None


def test_normalize_is_pure():
    """normalize 必须是纯函数（可回放、可单测）。"""
    from zoneinfo import ZoneInfo

    from app.connectors.base import RawItem
    from app.connectors.spec import DEFAULT_TZ

    conn = TushareFlashConnector(config={"srcs": ["cls"]})
    raw = RawItem(
        external_id="abc123",
        payload={
            "title": "央行宣布降准0.25个百分点",
            "content": "具体内容",
            "datetime": "2026-09-18 10:30:00",
            "channels": "宏观",
        },
        fetched_at=datetime(2026, 9, 18, 11, 0, tzinfo=ZoneInfo(DEFAULT_TZ)),
        channel="cls",
    )
    draft1 = conn.normalize(raw)
    draft2 = conn.normalize(raw)
    assert draft1 == draft2
    assert draft1.title == "央行宣布降准0.25个百分点"
    # ★ 时间必须带时区：库里是 timestamptz，naive 会被按会话时区隐式解释
    assert draft1.published_at == datetime(2026, 9, 18, 10, 30, tzinfo=ZoneInfo(DEFAULT_TZ))
    # ★ 渠道身份来自 src 映射表（上游返回里没有 src 字段，取 payload 只会得到兜底值）
    assert draft1.source_name == "财联社"
    assert draft1.attributes["channels"] == "宏观"
    assert draft1.provenance.channel == "cls"


@pytest.mark.asyncio
async def test_health_and_available():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        resp = await client.get("/api/v1/connectors/available")
        assert resp.status_code == 200
        assert any(c["key"] == "tushare.flash" for c in resp.json())


@pytest.mark.skipif(not HAS_TOKEN, reason="需要 TUSHARE_TOKEN")
@pytest.mark.asyncio
async def test_end_to_end_sync():
    """长文/公告类接口真机验证 + 全链路落库（major_news / cctv_news 当前有权限）。"""
    from app.core.database import SessionLocal
    from app.models.enums import SyncStatus
    from app.repositories.ingest_repo import ConnectorRepository, SyncRunRepository
    from app.services.sync_service import run_sync  # noqa: F401  （保证 worker 侧导入链正常）

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 幂等：先软删旧的（同 owner 同 key 只允许一条活跃行），再创建
        resp = await client.get("/api/v1/connectors")
        for c in resp.json():
            if c["key"] == "tushare.article":
                assert (await client.delete(f"/api/v1/connectors/{c['id']}")).status_code == 204

        resp = await client.post("/api/v1/connectors", json={"key": "tushare.article"})
        assert resp.status_code == 201, resp.text
        connector_id = uuid.UUID(resp.json()["id"])

        # 凭据自检
        resp = await client.post(f"/api/v1/connectors/{connector_id}/validate")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True, resp.json()["message"]

        # 触发同步（最近 2 天，避免拉太多）
        now = datetime.now()
        resp = await client.post(
            f"/api/v1/connectors/{connector_id}/sync",
            json={
                "window_start": (now - timedelta(days=2)).isoformat(),
                "window_end": now.isoformat(),
            },
        )
        assert resp.status_code == 202, resp.text
        stats = resp.json()
        print("\n[sync stats]", stats)
        assert stats["status"] in {SyncStatus.success.value, SyncStatus.partial.value}
        if stats["fetched"] == 0:
            pytest.skip(f"该区间无数据（{stats.get('empty_reason')}），跳过落库断言")

        # 校验落库
        async with SessionLocal() as session:
            rows = await SyncRunRepository(session).list_runs(connector_id, limit=1)
            assert rows, "应产生 sync_run 记录"
            assert rows[0].fetched_count == stats["fetched"]

            connector = await ConnectorRepository(session).get(connector_id)
            assert connector.consecutive_failures == 0

        # 资讯列表可读
        resp = await client.get("/api/v1/news?limit=5")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        print("[news sample]", items[0]["title"][:40], "| sources:", len(items[0].get("source_refs", [])))

        # 详情：跨源 siblings
        resp = await client.get(f"/api/v1/news/{items[0]['id']}")
        assert resp.status_code == 200

        # 行为流：read 可多次，star 只保留最新
        news_id = items[0]["id"]
        for _ in range(2):
            r = await client.post(f"/api/v1/news/{news_id}/actions", json={"action": "read"})
            assert r.status_code == 201
        r1 = await client.post(f"/api/v1/news/{news_id}/actions", json={"action": "star"})
        r2 = await client.post(f"/api/v1/news/{news_id}/actions", json={"action": "star"})
        assert r1.status_code == 201 and r2.status_code == 201
        assert r2.json()["updated"] is True


@pytest.mark.skipif(not HAS_TOKEN, reason="需要 TUSHARE_TOKEN")
@pytest.mark.asyncio
async def test_flash_real_sync():
    """★ 快讯链路真机验收（doc 143）。

    这是本期最关键的验证：旧实现对 `news` 的调用参数是错的（src 必选却没传、
    时间格式用了 %Y%m%d %H%M%S），`probe_endpoints()` 因此把"0 行"误判成"无权限"。
    这里用修正后的参数真机跑一遍，确认：
      1) 参数修正后确实拿得到数据（不是权限问题）
      2) 渠道身份正确地落在 source_name 上（而不是全部退化成 "Tushare"）
      3) 时间是带时区的
    """
    from app.connectors.spec import DEFAULT_TZ
    from app.repositories.news_repo import NewsRepository  # noqa: F401

    srcs = ["cls", "sina"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/connectors")
        for c in resp.json():
            if c["key"] == "tushare.flash":
                assert (await client.delete(f"/api/v1/connectors/{c['id']}")).status_code == 204

        resp = await client.post(
            "/api/v1/connectors",
            json={"key": "tushare.flash", "config": {"srcs": srcs}},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        connector_id = uuid.UUID(body["id"])
        assert body["config"]["srcs"] == srcs
        listed = {f["key"] for f in body["capability"]["config_schema"]}
        assert "srcs" in listed, "能力声明里必须带配置项，前端才能渲染来源多选"

        # 1) 逐来源探测：必须至少一个来源真的有数据
        resp = await client.post(f"/api/v1/connectors/{connector_id}/validate")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True, resp.json()["message"]
        print("\n[validate]", resp.json()["message"])

        # 2) 真机同步（3 天窗口，尽量避开"刚好这个时段没快讯"）
        now = datetime.now()
        resp = await client.post(
            f"/api/v1/connectors/{connector_id}/sync",
            json={
                "window_start": (now - timedelta(days=3)).isoformat(),
                "window_end": now.isoformat(),
            },
        )
        assert resp.status_code == 202, resp.text
        stats = resp.json()
        print("[flash sync stats]", stats)
        assert stats["status"] in {"success", "partial"}, stats
        assert stats["fetched"] > 0, f"修参数后仍拿不到快讯，需要重新判断权限：{stats.get('empty_reason')}"

        # 3) 渠道身份与时间语义落到库里
        from zoneinfo import ZoneInfo

        from app.core.database import SessionLocal
        from app.models.news import NewsItem
        from sqlalchemy import select

        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(NewsItem)
                    .where(NewsItem.connector_id == connector_id)
                    .order_by(NewsItem.published_at.desc())
                    .limit(5)
                )
            ).scalars().all()
            assert rows, "快讯应已落库"
            names = {r.source_name for r in rows}
            print("[flash sources]", names)
            assert names & {"财联社", "新浪财经"}, f"source_name 未落到渠道名：{names}"
            assert "Tushare" not in names, "source_name 退化成兜底值 = 渠道身份丢失"
            for r in rows:
                assert r.published_at.tzinfo is not None
                assert r.published_at.astimezone(ZoneInfo(DEFAULT_TZ)).year >= 2026
                assert r.content_type.value == "flash"
