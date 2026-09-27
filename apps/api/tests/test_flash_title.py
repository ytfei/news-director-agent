"""快讯标题兜底测试（不需要网络 / 数据库）。

背景：新浪财经与华尔街见闻的 `news` 返回里 `title` 恒为 None，正文就是一句话新闻。
"""

from __future__ import annotations

from app.connectors.tushare.flash import title_from_content


def test_extract_first_sentence():
    text = "以色列军方称，今日早些时候袭击了黎巴嫩南部萨杰德地区一处真主党武器库。"
    assert title_from_content(text) == text


def test_strip_bracket_prefix():
    """东方财富风格：正文以【标题】开头，提标题时要先剥掉，避免标题重复。"""
    text = "【巴布亚新几内亚发生5.6级地震】据欧洲-地中海地震中心测定，当地时间9月27日0时08分发生地震。"
    assert title_from_content(text).startswith("据欧洲-地中海")


def test_truncate_long_text():
    text = "没有句号的一段很长很长的文字" * 20
    assert len(title_from_content(text)) <= 80


def test_empty():
    assert title_from_content(None) == ""
    assert title_from_content("") == ""
    assert title_from_content("   ") == ""


def test_break_on_newline():
    assert title_from_content("第一行标题\n第二行正文内容") == "第一行标题\n"
