"""M3 写作的纯逻辑测试（不碰真实 LLM，理由同 test_review_llm）。

覆盖最容易写错的三处：
- 大纲解析（模型返回脏数据是常态）
- 正文拼装与「段落 → 素材」映射（可追溯视图依赖它）
- brief/outline 的断点序列化往返（HITL 中断后要能原样恢复）
"""

from __future__ import annotations

import uuid

from app.services.compose_service import (
    Brief,
    Outline,
    Section,
    assemble_markdown,
    brief_from_dict,
    brief_to_dict,
    outline_from_dict,
    outline_to_dict,
)


def test_parse_outline_skips_dirty() -> None:
    from app.services.compose_service import _parse_outline

    assert _parse_outline(None) is None
    assert _parse_outline({"sections": []}) is None
    assert _parse_outline({"sections": "nope"}) is None

    outline = _parse_outline(
        {
            "title_candidates": ["标题A", "标题B"],
            "sections": [
                {"heading": "第一段", "key_points": ["要点"], "material_refs": [1], "target_words": 300},
                {"heading": "   ", "key_points": []},  # 空标题
                "not-a-dict",
            ],
        }
    )
    assert outline is not None
    assert len(outline.sections) == 1, "空标题与非 dict 都要跳过"
    assert outline.title_candidates == ["标题A", "标题B"]


def test_assemble_markdown_builds_citation() -> None:
    """★ citation_map 是「这段话依据什么」的追溯链路，不能丢。"""
    outline = Outline(
        title_candidates=["测试标题"],
        sections=[
            Section(heading="背景", key_points=[], material_refs=[1, 2], target_words=100,
                    content="第一段正文"),
            Section(heading="推演", key_points=[], material_refs=[3], target_words=100,
                    content="第二段正文"),
        ],
    )
    content, citation = assemble_markdown("测试标题", outline.sections)

    assert content.startswith("# 测试标题")
    assert "## 背景" in content and "第一段正文" in content
    assert citation["section_1"]["material_refs"] == [1, 2]
    assert citation["section_2"]["heading"] == "推演"


def test_brief_roundtrip() -> None:
    """HITL 中断后要能从 dict 原样恢复 brief。"""
    brief = Brief(
        project_id=uuid.uuid4(),
        title="选题A",
        mode="opinion",
        platform="xhs",
        target_words=1500,
        annotations=[{"news_title": "新闻1", "body": "我的观点"}],
        materials=[{"id": "1", "title": "素材1", "source_name": "来源", "summary": "摘要", "content": "正文"}],
        prompts=[{"name": "风格", "description": "克制", "category": "style"}],
    )
    restored = brief_from_dict(brief_to_dict(brief))
    assert restored.title == brief.title
    assert restored.mode == "opinion"
    assert restored.target_words == 1500
    assert restored.annotations == brief.annotations
    assert restored.project_id == brief.project_id


def test_outline_roundtrip() -> None:
    outline = Outline(
        title_candidates=["A", "B"],
        sections=[Section(heading="h", key_points=["k"], material_refs=[1], target_words=200)],
    )
    restored = outline_from_dict(outline_to_dict(outline))
    assert restored.title_candidates == ["A", "B"]
    assert len(restored.sections) == 1
    assert restored.sections[0].material_refs == [1]
    assert restored.sections[0].content == "", "恢复时正文还没写"


def test_digest_mode_has_no_annotation() -> None:
    """没有点评 → digest 模式，brief 里不能凭空冒出观点。"""
    brief = Brief(project_id=uuid.uuid4(), title="t", mode="digest")
    assert brief.annotations == []
    assert brief.mode == "digest"
