"""M2 主链路集成测试：素材 → 批注 → 检查 → 体检 → 选题 → 触发写作。

需要 Postgres（infra/docker-compose.yml）且已执行 `alembic upgrade head`；
数据库不可用时整组跳过，不阻塞纯逻辑测试。

运行：
    uv run alembic upgrade head
    uv run pytest tests/test_workspace_flow.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from app.api.deps import DEV_USER_ID, ensure_user
from app.core.database import SessionLocal
from app.main import app
from app.models.enums import ConnectorStatus, ContentType
from app.models.ingest import SourceConnector
from app.models.news import NewsItem
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

BODY_V1 = "这次扩产是被动应对，因此股价必然下跌，这家公司的估值就是骗局。产能利用率 85%。"
BODY_V2 = "这次扩产我倾向于认为是被动应对；若 2027 年需求不及预期，产能利用率会承压。"


async def _db_ready() -> tuple[bool, str]:
    try:
        async with SessionLocal() as s:
            await s.execute(text("select 1 from materials limit 1"))
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:160]


@pytest.fixture
async def client():
    ok, reason = await _db_ready()
    if not ok:
        pytest.skip(f"数据库未就绪（{reason}）")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_news() -> uuid.UUID:
    """造一条资讯（含所属连接器），用于素材链路的输入。"""
    async with SessionLocal() as s:
        await ensure_user(s, DEV_USER_ID)
        # 连接器按 (owner, key) 唯一：复用已存在的，避免重复调用冲突
        connector = (
            await s.execute(
                select(SourceConnector).where(
                    SourceConnector.owner_id == DEV_USER_ID,
                    SourceConnector.key == "test.workspace",
                    SourceConnector.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if connector is None:
            connector = SourceConnector(
                owner_id=DEV_USER_ID,
                connector_type="tushare",
                key="test.workspace",
                display_name="集成测试源",
                status=ConnectorStatus.active,
                config={},
                capability={},
            )
            s.add(connector)
            await s.flush()
        news = NewsItem(
            connector_id=connector.id,
            content_type=ContentType.flash,
            title=f"集成测试 · 中芯国际扩产公告 {uuid.uuid4().hex[:6]}",
            summary="测试用摘要",
            content="测试用正文：拟投资 75 亿美元扩建 12 英寸产线。",
            published_at=datetime.now(),
            content_hash=uuid.uuid4().hex,
            source_name="测试来源",
            source_refs=[],
            market_scope=[],
            industries=[],
            entities=[],
            keywords=[],
        )
        s.add(news)
        await s.commit()
        return news.id


async def test_material_annotation_review_project_flow(client: AsyncClient):
    news_id = await _seed_news()

    # ---- 1. 标记素材（幂等 upsert + 主题） ----
    resp = await client.post(
        "/api/v1/materials",
        json={"news_id": str(news_id), "score": 8, "topics": ["扩产", "半导体"]},
    )
    assert resp.status_code == 201, resp.text
    material = resp.json()["material"]
    material_id = material["id"]
    assert material["score"] == 8
    assert set(material["topics"]) == {"扩产", "半导体"}
    assert material["annotation"] is None  # ★ 素材不要求有点评

    # 重复标记 = 更新，不新增
    resp = await client.post(
        "/api/v1/materials", json={"news_id": str(news_id), "score": 9, "topics": ["扩产"]}
    )
    assert resp.status_code == 201
    assert resp.json()["created"] is False
    assert resp.json()["material"]["score"] == 9

    # 列表按维度筛选
    resp = await client.get("/api/v1/materials", params={"min_score": 8, "topic": "扩产"})
    assert resp.status_code == 200
    assert any(m["id"] == material_id for m in resp.json())

    resp = await client.get("/api/v1/materials", params={"min_score": 10})
    assert all(m["id"] != material_id for m in resp.json())

    # 资讯列表带素材徽标
    resp = await client.get("/api/v1/news", params={"limit": 50})
    hit = next(n for n in resp.json() if n["id"] == str(news_id))
    assert hit["material"]["score"] == 9
    assert hit["annotation"] is None

    # ---- 2. 就地批注（写点评 → 版本） ----
    resp = await client.put(
        f"/api/v1/materials/{material_id}/annotation", json={"body": BODY_V1}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["version_created"] is True
    assert resp.json()["version_no"] == 1

    # 内容未变 → 不产生新版本
    resp = await client.put(
        f"/api/v1/materials/{material_id}/annotation", json={"body": BODY_V1}
    )
    assert resp.json()["version_created"] is False
    assert resp.json()["version_no"] == 1

    # ---- 2.5 事实基线（ResearcherAgent 的落库入口，fact 轨道的输入） ----
    resp = await client.put(
        f"/api/v1/news/{news_id}/fact-card",
        json={
            "context_notes": "集成测试用事实基线",
            "related_symbols": ["688981.SH"],
            "open_questions": ["国产设备占比口径待确认"],
            "claims": [
                {
                    "claim": "2026 年上半年营业收入同比 +12.4%",
                    "status": "verified",
                    "confidence": 0.97,
                    "evidence": [{"src": "公告 · anns_d", "date": "2026-09-19"}],
                },
                {
                    "claim": "市场流传的营收增长 30% 为含税口径",
                    "status": "contradicted",
                    "confidence": 0.6,
                    "evidence": [{"src": "第一财经", "date": "2026-09-19"}],
                },
                {
                    # ★ 硬约束：没有 evidence 的 claim 不允许标 verified
                    "claim": "设备国产化率已超五成",
                    "status": "verified",
                    "confidence": 0.9,
                    "evidence": [],
                },
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    card = resp.json()
    assert len(card["claims"]) == 3
    unverifiable = [c for c in card["claims"] if c["claim"].startswith("设备国产化率")]
    assert unverifiable[0]["status"] == "unverifiable"  # 被降级

    # ---- 3. 提交检查：合规红线 + 绝对化 + 无出处数值 ----
    resp = await client.post(
        "/api/v1/annotations/check", json={"material_ids": [material_id]}
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["verdict_summary"]["blocked"] == 1
    report_id = result["reports"][0]["id"]
    assert result["reports"][0]["findings_count"] >= 3

    resp = await client.get(f"/api/v1/reviews/{report_id}")
    assert resp.status_code == 200
    report = resp.json()
    assert report["verdict"] == "blocked"
    tracks = {f["track"] for f in report["findings"]}
    assert {"compliance", "logic", "fact"} <= tracks
    blocker = next(f for f in report["findings"] if f["severity"] == "blocker")
    logic = next(f for f in report["findings"] if f["track"] == "logic")
    # finding 必须可定位（前端划词高亮依赖它）
    assert blocker["quote"] and blocker["span_end"] > blocker["span_start"]

    # ---- 4. 红线未处置 → 不可写作 ----
    resp = await client.post(
        "/api/v1/projects", json={"title": "中芯扩产怎么看", "material_ids": [material_id]}
    )
    assert resp.status_code == 201, resp.text
    project = resp.json()
    project_id = project["id"]
    assert project["assessment"]["writable"] is False
    assert project["assessment"]["stats"]["with_blocker"] == 1

    resp = await client.post(f"/api/v1/projects/{project_id}/compose")
    assert resp.status_code == 409  # 准入校验拦住

    # ---- 5. 采纳建议（生成新版本，需复检） ----
    resp = await client.post(
        f"/api/v1/reviews/findings/{logic['id']}/resolve", json={"action": "accepted"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["needs_recheck"] is True

    # 驳回必须填理由
    resp = await client.post(
        f"/api/v1/reviews/findings/{blocker['id']}/resolve", json={"action": "dismissed"}
    )
    assert resp.status_code == 422
    resp = await client.post(
        f"/api/v1/reviews/findings/{blocker['id']}/resolve",
        json={"action": "dismissed", "reason": "引用的是公开报道原话，非我本人指控"},
    )
    assert resp.status_code == 200

    # 处置后 verdict 降级；但正文已被采纳建议改写 → 版本号 +1
    resp = await client.get(f"/api/v1/materials/{material_id}/annotation")
    assert resp.json()["annotation"]["version_no"] == 2

    # ---- 6. 复检 → 结论稳定后即可写作 ----
    resp = await client.post(
        "/api/v1/annotations/check", json={"material_ids": [material_id]}
    )
    assert resp.status_code == 200
    assert resp.json()["verdict_summary"]["blocked"] == 0

    resp = await client.get(f"/api/v1/projects/{project_id}")
    assessment = resp.json()["assessment"]
    assert assessment["writable"] is True
    assert assessment["mode"] in {"opinion", "digest"}

    resp = await client.post(f"/api/v1/projects/{project_id}/compose")
    assert resp.status_code == 202, resp.text
    assert resp.json()["run_id"]


async def test_material_without_annotation_is_writable(client: AsyncClient):
    """★ docs/06 §1 R4：素材可以没有点评，仍允许进入写作（综述模式）。"""
    news_id = await _seed_news()
    resp = await client.post(
        "/api/v1/materials", json={"news_id": str(news_id), "score": 6, "topics": ["政策"]}
    )
    material_id = resp.json()["material"]["id"]

    resp = await client.post(
        "/api/v1/projects", json={"title": "无点评选题", "material_ids": [material_id]}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["assessment"]["writable"] is True
    assert body["assessment"]["mode"] == "digest"
    assert body["assessment"]["stats"]["with_annotation"] == 0

    resp = await client.post(f"/api/v1/projects/{body['id']}/compose")
    assert resp.status_code == 202
    assert resp.json()["mode"] == "digest"


async def test_check_rejects_material_without_annotation(client: AsyncClient):
    news_id = await _seed_news()
    resp = await client.post("/api/v1/materials", json={"news_id": str(news_id)})
    material_id = resp.json()["material"]["id"]

    resp = await client.post("/api/v1/annotations/check", json={"material_ids": [material_id]})
    assert resp.status_code == 422


async def test_topics_and_stats(client: AsyncClient):
    resp = await client.get("/api/v1/topics")
    assert resp.status_code == 200
    assert any(t["is_system"] for t in resp.json())

    name = f"自定义主题{uuid.uuid4().hex[:4]}"
    resp = await client.post("/api/v1/topics", json={"name": name})
    assert resp.status_code == 201
    assert resp.json()["is_system"] is False
    # 重复创建幂等
    resp2 = await client.post("/api/v1/topics", json={"name": name})
    assert resp2.json()["id"] == resp.json()["id"]

    resp = await client.get("/api/v1/materials/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert {"total", "with_annotation", "avg_score", "by_topic", "score_buckets"} <= set(body)


async def test_prompts_seeded(client: AsyncClient):
    resp = await client.get("/api/v1/prompts")
    assert resp.status_code == 200
    rows = resp.json()
    cats = {p["category"] for p in rows}
    assert {"style", "structure", "taboo"} <= cats
    assert any(p["is_official"] for p in rows)
