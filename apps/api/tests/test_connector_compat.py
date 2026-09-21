"""注册表标识变更的兼容性测试。

背景：`tushare.news` 一个连接器原本覆盖 6 个接口（含快讯），现拆分为
`tushare.flash`（快讯）+ `tushare.article`（长文/公告/政策/研报）。

`source_connectors.key` 是**持久化在数据库里**的，所以老行必须继续可读可跑 ——
否则升级后同步会在"取连接器类"的那一刻直接抛 LookupError，
而不是给出人能看懂的迁移提示。
"""

from __future__ import annotations

import pytest
from app.api.deps import DEV_USER_ID
from app.connectors.registry import (
    all_keys,
    available_connectors,
    get_connector_class,
    is_alias,
    migration_hint,
    resolve_key,
)
from app.connectors.tushare.connector import TushareArticleConnector
from app.connectors.tushare.flash import TushareFlashConnector
from app.connectors.tushare.specs import ARTICLE_SPECS
from app.services.sync_service import empty_reason
from sqlalchemy import text

LEGACY_KEY = "tushare.news"


# ---------------------------------------------------------------- 别名解析


def test_current_keys_are_registered():
    keys = set(all_keys())
    assert {"tushare.flash", "tushare.article"} <= keys
    assert LEGACY_KEY not in keys, "旧 key 不应再作为独立连接器存在（否则两个类争同一功能）"


def test_legacy_key_resolves_to_article_connector():
    """★ 老 key 必须能取到类；且指向 article 而不是 flash。

    老行的配置是 `config.endpoints=[...]`（多接口），指向 article 能保留它原有的行为；
    指向 flash 则因为缺少 `srcs` 配置会立刻变成"未配置来源"错误。
    """
    assert is_alias(LEGACY_KEY) is True
    assert resolve_key(LEGACY_KEY) == "tushare.article"
    assert get_connector_class(LEGACY_KEY) is TushareArticleConnector


def test_alias_not_advertised_as_available():
    """别名只服务历史数据，不该出现在新建连接器的下拉里。"""
    assert LEGACY_KEY not in {c["key"] for c in available_connectors()}
    assert "tushare.flash" in {c["key"] for c in available_connectors()}


def test_migration_hint_is_human_readable():
    hint = migration_hint(LEGACY_KEY)
    assert hint is not None
    assert hint["from_key"] == LEGACY_KEY
    assert hint["to_key"] == "tushare.article"
    # 提示要告诉用户"接下来该做什么"，而不只是报一个 key
    assert "快讯" in hint["note"] and "Tushare 新闻快讯" in hint["note"]
    assert migration_hint("tushare.flash") is None


def test_unknown_key_still_raises_lookup_error():
    with pytest.raises(LookupError, match="未注册的数据源"):
        get_connector_class("nope.nothing")


def test_flash_connector_is_registered_class():
    assert get_connector_class("tushare.flash") is TushareFlashConnector


def test_article_specs_cover_all_endpoints_except_flash():
    """快讯必须从 article 连接器的接口表里移除，否则两个连接器会重复拉同一批数据。"""
    from app.connectors.tushare.connector import ENDPOINTS

    apis = {api for api, _gran, _ct in ENDPOINTS}
    assert "news" not in apis
    assert apis == set(ARTICLE_SPECS), "每个接口都必须有字段映射声明（归一化不再手写）"


# ---------------------------------------------------------------- empty_reason 钩子


def test_empty_reason_prefers_connector_hook():
    """判定依据因渠道而异，同步编排只负责问连接器，不负责懂 tushare。"""

    class WithHook:
        def empty_reason(self):
            return "配置的 2 个来源近 3 小时均无数据"

    class WithoutHook:
        config = {}

    assert empty_reason(WithHook()) == "配置的 2 个来源近 3 小时均无数据"
    assert "区间内无数据" in empty_reason(WithoutHook())


# ---------------------------------------------------------------- API 行为（真库）


@pytest.mark.asyncio
async def test_create_with_legacy_key_stores_resolved_key(client):
    """新建时用旧 key 提交，落库必须是现行 key —— 别名不该继续被写进库。"""
    resp = await client.get("/api/v1/connectors")
    for c in resp.json():
        if c["key"] in {LEGACY_KEY, "tushare.article"}:
            assert (await client.delete(f"/api/v1/connectors/{c['id']}")).status_code == 204

    resp = await client.post("/api/v1/connectors", json={"key": LEGACY_KEY})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["key"] == "tushare.article"
    # 新建的行不该带迁移提示（它本身已经是现行 key）
    assert body["key_migrated_to"] is None

    assert (await client.delete(f"/api/v1/connectors/{body['id']}")).status_code == 204


@pytest.mark.asyncio
async def test_list_surfaces_migration_note_for_legacy_rows(client, db_session):
    """历史行（库里仍是旧 key）必须继续可用，并在出参里带上迁移提示。"""
    from app.models.enums import ConnectorStatus
    from app.models.ingest import SourceConnector

    row = SourceConnector(
        owner_id=DEV_USER_ID,
        connector_type="tushare",
        key="tushare.news",  # 模拟升级前创建的存量行
        display_name="存量 Tushare 连接器",
        status=ConnectorStatus.active,
        config={},
        capability={},
    )
    db_session.add(row)
    await db_session.commit()
    try:
        # 1) 老行仍能构建出连接器实例（不抛 LookupError）
        from app.services.connector_factory import build_connector

        connector = build_connector(row)
        assert isinstance(connector, TushareArticleConnector)

        # 2) 出参带人话迁移提示
        resp = await client.get("/api/v1/connectors")
        assert resp.status_code == 200
        legacy = next(c for c in resp.json() if c["id"] == str(row.id))
        assert legacy["key_migrated_to"] == "tushare.article"
        assert "快讯" in legacy["migration_note"]

        # 3) 新行不带提示
        fresh = next((c for c in resp.json() if c["key"] == "tushare.article"), None)
        if fresh is not None:
            assert fresh["key_migrated_to"] is None
    finally:
        await db_session.execute(
            text("delete from source_connectors where id = :id"), {"id": row.id}
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_unknown_key_returns_400(client):
    resp = await client.post("/api/v1/connectors", json={"key": "nope.nothing"})
    assert resp.status_code == 400
    assert "未注册的数据源" in resp.json()["detail"]
