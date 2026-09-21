"""tushare 各接口的字段映射声明。

新增一个 tushare 接口 = 在这里加一个 `ChannelSpec`，不需要写 normalize 代码。

## tushare `news`（新闻快讯，doc_id=143）的关键事实

官方规格（https://tushare.pro/document/2?doc_id=143）：

- 输入：`src`（**必选**，9 个来源之一）+ `start_date` / `end_date`
  （格式 `2018-11-20 09:00:00`，即 `%Y-%m-%d %H:%M:%S`）
- 输出：`datetime` / `content` / `title` / `channels`
  —— **没有 id、没有 src、没有 url**
- 限量：单次最大 1500 条
- 权限：需单独开通，与积分无关

由此推出的三个工程结论（都体现在下面的声明里）：

1. `src` 不在返回值里 → 渠道身份必须由连接器注入（`$channel`），
   否则 9 个来源的资讯会全部退化成同一个 `source_name`。
2. 没有 id → 幂等键只能用**稳定字段组合**（渠道 + 时间 + 标题），
   不能用全字段 hash（上游多回一个字段就会漂移成新条目）。
3. 时间是无时区的字符串 → 统一按东八区补时区后再落库。
"""

from __future__ import annotations

from app.connectors.base import SourceKind
from app.connectors.spec import ChannelSpec, FieldRef, MetricSpec
from app.connectors.tushare.base import to_standard_code
from app.models.enums import ContentType

# `src` → 中文来源名。上游返回里没有 src，所以这张表是渠道身份的唯一来源。
SRC_LABELS: dict[str, str] = {
    "sina": "新浪财经",
    "wallstreetcn": "华尔街见闻",
    "10jqka": "同花顺",
    "eastmoney": "东方财富",
    "yuncaijing": "云财经",
    "fenghuang": "凤凰新闻",
    "jinrongjie": "金融界",
    "cls": "财联社",
    "yicai": "第一财经",
}


def src_label(src: str | None) -> str | None:
    if not src:
        return None
    return SRC_LABELS.get(src, src)


# 接口名 → 人话名（进 provenance.channel_label，用于按渠道排查）
API_LABELS: dict[str, str] = {
    "news": "Tushare 快讯",
    "major_news": "Tushare 长文",
    "cctv_news": "央视新闻联播",
    "anns_d": "交易所公告",
    "npr": "国家政策库",
    "research_report": "券商研报",
}


def api_label(api: str | None) -> str | None:
    if not api:
        return None
    return API_LABELS.get(api, api)


# tushare 快讯返回的时间字段格式实测可能是 `%Y-%m-%d %H:%M:%S`，
# 但历史上同类接口也出现过 `%Y%m%d %H%M%S`，两种都声明上，避免因格式差异整段丢弃。
NEWS_TIME_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y%m%d %H%M%S"]

# tushare `news` 单次返回上限（官方限量），达到即视为可能截断，需要细分窗口重拉
NEWS_MAX_ROWS = 1500

NEWS_SPEC = ChannelSpec(
    key="news",
    kind=SourceKind.news,
    content_type=ContentType.flash,
    title=FieldRef.of("title"),
    content=FieldRef.of("content", "text"),
    # ★ 渠道名由连接器注入：上游返回里没有 src，写 p.get("src") 只会永远落到兜底值
    source_name=FieldRef.of("$channel_label"),
    time=FieldRef.of("datetime", "pub_time", "time"),
    time_formats=NEWS_TIME_FORMATS,
    # 上游分类字段进 attributes 扩展通道（不参与检索，但可展示与回溯）
    attributes={"channels": FieldRef.of("channels")},
    static_attributes={"upstream_api": "news"},
    market_scope=["a_share"],
    # 幂等键 = 渠道 + 发布时间 + 标题：跨次拉取稳定，且不受上游字段增减影响
    external_id_fields=["$channel", "datetime", "title"],
)

# 本期快讯不产出数值事实；此处保留一个示例声明，说明数值通道怎么用，
# 将来接行情/资金流时按同样方式声明即可（届时由 market 连接器使用）。
NEWS_METRIC_SPECS: list[MetricSpec] = []


# ---------------------------------------------------------------- 长文 / 公告 / 政策 / 研报
#
# 这 5 个接口的**字段名没有逐一真机验证**（Spike #1：anns_d / npr / research_report 无权限，
# major_news / cctv_news 可用但当时是手写映射）。
# 因此一律用「多候选回退」声明：取到哪个算哪个，取不到就是 None ——
# 这正是声明式映射的价值：上游改字段名只需要在这里加一个候选，不用改代码逻辑。

_ARTICLE_TIME_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y%m%d %H%M%S", "%Y-%m-%d", "%Y%m%d"]

MAJOR_NEWS_SPEC = ChannelSpec(
    key="major_news",
    kind=SourceKind.news,
    content_type=ContentType.article,
    title=FieldRef.of("title"),
    content=FieldRef.of("content", "text"),
    summary=FieldRef.of("summary", "abstract"),
    source_name=FieldRef.of("src", "$channel_label"),
    time=FieldRef.of("pub_time", "datetime", "pub_date", "date"),
    time_formats=_ARTICLE_TIME_FORMATS,
    url=FieldRef.of("url", "link"),
    market_scope=["a_share"],
    external_id_fields=["$channel", "pub_time", "title"],
)

CCTV_NEWS_SPEC = ChannelSpec(
    key="cctv_news",
    kind=SourceKind.news,
    content_type=ContentType.article,
    title=FieldRef.of("title"),
    content=FieldRef.of("content"),
    source_name=FieldRef.const("央视新闻联播"),
    time=FieldRef.of("date", "pub_time", "datetime"),
    time_formats=_ARTICLE_TIME_FORMATS,
    market_scope=["a_share"],
    external_id_fields=["$channel", "date", "title"],
)

ANNS_D_SPEC = ChannelSpec(
    key="anns_d",
    kind=SourceKind.announcement,
    content_type=ContentType.announcement,
    title=FieldRef.of("title", "name"),
    content=FieldRef.of("content"),
    author=FieldRef.of("name"),
    source_name=FieldRef.const("交易所公告"),
    time=FieldRef.of("ann_date", "datetime", "date"),
    time_formats=_ARTICLE_TIME_FORMATS,
    url=FieldRef.of("url"),
    attributes={"ann_type": FieldRef.of("ann_type")},
    market_scope=["a_share"],
    symbol_fields=["ts_code"],
    symbol_transform=to_standard_code,
    external_id_fields=["$channel", "ts_code", "ann_date", "title"],
)

NPR_SPEC = ChannelSpec(
    key="npr",
    kind=SourceKind.policy,
    content_type=ContentType.policy,
    title=FieldRef.of("title"),
    content=FieldRef.of("content"),
    author=FieldRef.of("puborg"),
    source_name=FieldRef.of("puborg", "$channel_label"),
    time=FieldRef.of("pubtime", "pub_time", "date", "datetime"),
    time_formats=_ARTICLE_TIME_FORMATS,
    url=FieldRef.of("url"),
    attributes={"ptype": FieldRef.of("ptype"), "pcode": FieldRef.of("pcode")},
    market_scope=["a_share", "macro"],
    external_id_fields=["$channel", "pcode", "pubtime", "title"],
)

RESEARCH_REPORT_SPEC = ChannelSpec(
    key="research_report",
    kind=SourceKind.research,
    content_type=ContentType.research_report,
    title=FieldRef.of("title"),
    content=FieldRef.of("content"),
    summary=FieldRef.of("summary"),
    author=FieldRef.of("author", "researcher"),
    source_name=FieldRef.of("org_name", "org_sname", "$channel_label"),
    time=FieldRef.of("pub_time", "datetime", "date"),
    time_formats=_ARTICLE_TIME_FORMATS,
    url=FieldRef.of("url"),
    market_scope=["a_share"],
    symbol_fields=["ts_code"],
    symbol_transform=to_standard_code,
    external_id_fields=["$channel", "pub_time", "org_name", "title"],
)

# 接口名 → 映射声明。新增 tushare 接口时只在这里加一行。
ARTICLE_SPECS: dict[str, ChannelSpec] = {
    "major_news": MAJOR_NEWS_SPEC,
    "cctv_news": CCTV_NEWS_SPEC,
    "anns_d": ANNS_D_SPEC,
    "npr": NPR_SPEC,
    "research_report": RESEARCH_REPORT_SPEC,
}


__all__ = [
    "ANNS_D_SPEC",
    "API_LABELS",
    "ARTICLE_SPECS",
    "CCTV_NEWS_SPEC",
    "MAJOR_NEWS_SPEC",
    "NEWS_MAX_ROWS",
    "NEWS_METRIC_SPECS",
    "NEWS_SPEC",
    "NEWS_TIME_FORMATS",
    "NPR_SPEC",
    "RESEARCH_REPORT_SPEC",
    "SRC_LABELS",
    "api_label",
    "src_label",
]
