"""M1 冒烟测试：注册表 → 归一化 → 真机同步 → API 查询。

运行：
    uv run pytest tests/test_smoke.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.connectors.registry import available_connectors, get_connector_class
from app.connectors.tushare.connector import TushareNewsConnector, to_standard_code
from app.main import app

HAS_TOKEN = bool(os.getenv("TUSHARE_TOKEN"))


def test_registry_contains_tushare():
    """新增数据源 = @register，注册表应自动发现。"""
    keys = [c["key"] for c in available_connectors()]
    assert "tushare.news" in keys
    assert get_connector_class("tushare.news") is TushareNewsConnector


def test_code_completion():
    """tushare 6 位代码 → 标准码。"""
    assert to_standard_code("600519") == "600519.SH"
    assert to_standard_code("000001") == "000001.SZ"
    assert to_standard_code("300750") == "300750.SZ"
    assert to_standard_code("600519.SH") == "600519.SH"
    assert to_standard_code(None) is None


def test_normalize_is_pure():
    """normalize 必须是纯函数（可回放、可单测）。"""
    from app.connectors.base import RawItem

    conn = TushareNewsConnector(config={})
    raw = RawItem(
        external_id="news:1",
        payload={"title": "央行宣布降准", "content": "具体内容", "datetime": "20260918 103000", "src": "证券时报"},
        fetched_at=datetime.now(),
        content_type="flash",
    )
    draft1 = conn.normalize(raw)
    draft2 = conn.normalize(raw)
    assert draft1 == draft2
    assert draft1.title == "央行宣布降准"
    assert draft1.published_at == datetime(2026, 9, 18, 10, 30, 0)
    assert draft1.source_name == "证券时报"


@pytest.mark.asyncio
async def test_health_and_available():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        resp = await client.get("/api/v1/connectors/available")
        assert resp.status_code == 200
        assert any(c["key"] == "tushare.news" for c in resp.json())


@pytest.mark.skipif(not HAS_TOKEN, reason="需要 TUSHARE_TOKEN")
@pytest.mark.asyncio
async def test_end_to_end_sync():
    """Spike #1：tushare 资讯接口真机验证 + 全链路落库。"""
    from app.core.database import SessionLocal
    from app.models.enums import SyncStatus
    from app.repositories.ingest_repo import ConnectorRepository, SyncRunRepository
    from app.services.sync_service import run_sync

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 创建连接器（凭据走环境变量回退；endpoints 不指定 → 由权限探测自动决定）
        #    幂等：先软删旧的（同 owner 同 key 只允许一条活跃行），再创建
        resp = await client.get("/api/v1/connectors")
        for c in resp.json():
            if c["key"] == "tushare.news":
                assert (await client.delete(f"/api/v1/connectors/{c['id']}")).status_code == 204

        resp = await client.post("/api/v1/connectors", json={"key": "tushare.news"})
        assert resp.status_code == 201, resp.text
        connector_id = uuid.UUID(resp.json()["id"])

        # 2. 凭据自检
        resp = await client.post(f"/api/v1/connectors/{connector_id}/validate")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True, resp.json()["message"]

        # 3. 触发同步（最近 2 天，避免拉太多）
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

        # 4. 校验落库
        async with SessionLocal() as session:
            rows = await SyncRunRepository(session).list_runs(connector_id, limit=1)
            assert rows, "应产生 sync_run 记录"
            assert rows[0].fetched_count == stats["fetched"]

            connector = await ConnectorRepository(session).get(connector_id)
            assert connector.consecutive_failures == 0

        # 5. 资讯列表可读
        resp = await client.get("/api/v1/news?limit=5")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        print("[news sample]", items[0]["title"][:40], "| sources:", len(items[0].get("source_refs", [])))

        # 6. 详情：跨源 siblings
        resp = await client.get(f"/api/v1/news/{items[0]['id']}")
        assert resp.status_code == 200

        # 7. 行为流：read 可多次，star 只保留最新
        news_id = items[0]["id"]
        for _ in range(2):
            r = await client.post(f"/api/v1/news/{news_id}/actions", json={"action": "read"})
            assert r.status_code == 201
        r1 = await client.post(f"/api/v1/news/{news_id}/actions", json={"action": "star"})
        r2 = await client.post(f"/api/v1/news/{news_id}/actions", json={"action": "star"})
        assert r1.status_code == 201 and r2.status_code == 201
        assert r2.json()["updated"] is True
