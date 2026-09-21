"""数据源接入层契约（**渠道无关**）。

设计见 docs/04-architecture.md §4：
- Connector 只负责"拿到原始数据"
- normalize() 必须是纯函数，便于回放与单测
- 新增数据源 = 新增一个 ChannelSpec + @register，不改调度器 / API / 前端

★ 为什么中间层不叫 "News"：
产品今天只有 tushare 快讯，明天要接 RSS / 公众号 / 雪球 / 交易所公告 / 板块行情。
这些源在**形状**上差异极大（长文本 vs 结构化行情），用「统一信封 + 双扩展通道」吸收：
    · attributes —— 键值型元信息（上游分类、公告类型、政策发文单位…）
    · metrics    —— 数值型事实（某标的价格 = 7.4 万元/吨），是"事实可核查"的最小单元
于是"文本资讯"和"市场数值"共用同一个骨架，落库分支数固定为「有 metrics / 无 metrics」，
而不是"每加一种数据类型就加一条分支"。
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import ContentType

# ---------------------------------------------------------------- 语义分类


class SourceKind(str, enum.Enum):
    """条目的语义类别（比 content_type 粗一档），用于决定落库分流。"""

    news = "news"  # 快讯 / 长文
    announcement = "announcement"
    policy = "policy"
    research = "research"
    social = "social"
    market = "market"  # 行情 / 资金流等数值型


# ---------------------------------------------------------------- 扩展通道


class Metric(BaseModel):
    """可核查的最小量化单元。

    来自任何渠道的数值型信息都归一到这里，将来"引用事实"与事实卡片都从这里取数，
    而不是去正文里正则撒网。
    """

    name: str  # 指标名，如 "电池级碳酸锂均价"
    value: Decimal
    unit: str | None = None  # 万元/吨、%、亿元
    period: str | None = None  # 时点 / 区间标识，如 "2026Q2"
    ts_code: str | None = None  # 标的，标准码 600519.SH
    observed_at: datetime | None = None  # 该数值本身的观测时间（可与条目发布时间不同）
    attributes: dict[str, Any] = Field(default_factory=dict)


class Provenance(BaseModel):
    """来源溯源：这一条到底从哪来。

    多源接入后，"这条数据是哪来的"是排查问题的第一手信息，不该靠猜。
    """

    connector_key: str | None = None  # 注册表 key，如 tushare.flash
    api: str | None = None  # 上游接口名，如 news
    channel: str | None = None  # 渠道标识，如 tushare 的 src=cls
    channel_label: str | None = None  # 渠道展示名，如 "财联社"
    fetched_at: datetime | None = None


# ---------------------------------------------------------------- 原始层


class RawItem(BaseModel):
    """原始条目：不做语义加工，只做必要的定位与幂等标识。"""

    external_id: str  # 源内唯一 id（没有则用内容 hash）
    payload: dict[str, Any]  # 原始结构原样保留
    fetched_at: datetime
    source_ref: str | None = None  # 原文 url / 文件 key
    content_type: ContentType = ContentType.flash
    # 条目来自哪个子渠道。一个连接器实例覆盖多个渠道时（如 tushare 快讯的 9 个 src）
    # 必须逐条声明，否则下游无法还原"这条是谁家报的"。
    channel: str | None = None


# ---------------------------------------------------------------- 统一信封


class NormalizedItem(BaseModel):
    """渠道无关的统一信封：Connector 尽力填，缺失由 Enricher 补。

    ★ `title` 可选 —— 数值型数据（行情、资金流）没有标题。
      落 DWD 时用 `display_title` 兜底（`news_items.title` 是 NOT NULL）。
    """

    external_id: str
    kind: SourceKind = SourceKind.news
    # 内容类型的**唯一来源**是 app/models/enums.py，此处不再重复定义 Literal
    content_type: ContentType = ContentType.flash

    title: str | None = None
    summary: str | None = None
    content: str | None = None
    author: str | None = None
    url: str | None = None
    published_at: datetime
    lang: str = "zh"
    source_name: str | None = None

    symbols: list[str] = Field(default_factory=list)  # 标准码 600519.SH
    industries: list[str] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    market_scope: list[str] = Field(default_factory=list)  # a_share / hk / us / macro

    # ---- 两个扩展通道（新渠道靠它们吸收形状差异，而不是新增模型） ----
    attributes: dict[str, Any] = Field(default_factory=dict)
    metrics: list[Metric] = Field(default_factory=list)

    provenance: Provenance = Field(default_factory=Provenance)
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def display_title(self) -> str:
        """落库用的展示标题。

        `news_items.title` 是 NOT NULL，而上游经常没有标题 ——
        快讯里"只有 content 没有 title"很常见（tushare 返回 NaN），数值型条目则根本没有标题。
        逐级兜底，保证任何渠道的数据都能落库，不需要给每条分支写兜底：

            正文摘要 → 指标名 + 数值 → external_id
        """
        if self.title and self.title.strip():
            return self.title.strip()
        if self.content and self.content.strip():
            body = " ".join(self.content.split())
            return body[:80] + ("…" if len(body) > 80 else "")
        if self.metrics:
            first = self.metrics[0]
            return f"{first.name} {first.value}{first.unit or ''}".strip()
        return self.external_id

    @property
    def has_metrics(self) -> bool:
        """落库分流的唯一判据：有数值事实 → 走数值事实表。"""
        return bool(self.metrics)


# 兼容过渡：旧名字指向同一个类。等所有调用点迁完再删（docs/04 §4.2）。
NewsDraft = NormalizedItem


# ---------------------------------------------------------------- 游标 / 能力


class SyncCursor(BaseModel):
    """增量游标：每个连接器独立持久化，支持断点续拉。

    `payload` 是自由字段：多来源连接器在这里存**按来源分组的独立进度**，
    这样一个来源失败不会把其他来源的进度一起拖回去（见 tushare.flash）。
    """

    last_external_id: str | None = None
    last_published_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ConfigField(BaseModel):
    """连接器配置项声明 —— 前端据此**动态渲染**配置表单。

    这是"新增数据源不改前端"的最后一块：连接器把要用户填什么声明出来，
    前端不需要认识任何具体的连接器。
    """

    key: str
    label: str
    type: Literal["text", "select", "multiselect", "number", "boolean"] = "text"
    options: list[dict[str, str]] = Field(default_factory=list)  # [{value, label}]
    default: Any = None
    required: bool = False
    help: str | None = None


class ConnectorCapability(BaseModel):
    """连接器能力声明——调度器据此决定同步策略，前端据此渲染配置与展示。"""

    content_types: list[str] = Field(default_factory=list)
    supports_incremental: bool = True
    supports_backfill: bool = True
    rate_limit_per_min: int | None = None
    requires_credentials: bool = False
    # ★ 配置项声明（默认空 = 不需要配置，保持既有连接器零改动）
    config_schema: list[ConfigField] = Field(default_factory=list)
    # 该连接器产生的数值事实会进这张"逻辑表"，供 UI 提示与未来的数据分区
    emits_metrics: bool = False


# ---------------------------------------------------------------- 契约


class DataSourceConnector(ABC):
    """所有数据源必须实现的契约。"""

    key: str  # 唯一标识，如 "tushare.flash"
    display_name: str
    capability: ConnectorCapability

    def __init__(self, config: dict[str, Any], credentials: dict[str, Any] | None = None) -> None:
        self.config = config
        self.credentials = credentials or {}

    @abstractmethod
    async def validate(self) -> tuple[bool, str]:
        """凭据/权限/连通性自检。返回 (是否可用, 人话说明)。"""

    @abstractmethod
    def fetch(
        self, cursor: SyncCursor, window: tuple[datetime, datetime]
    ) -> AsyncIterator[RawItem]:
        """拉取原始数据流。必须支持分段，避免长区间一次性拉取。"""

    @abstractmethod
    def normalize(self, raw: RawItem) -> NormalizedItem:
        """原始 → 统一信封。必须是纯函数，便于回放与单测。"""

    def empty_reason(self) -> str | None:
        """同步结果为空时的人话原因；返回 None 表示走通用兜底文案。

        必须区分「无权限 / 区间无数据 / 非交易日」，否则用户会以为系统坏了
        （docs/03 §3 步骤① 失败处理表）。各渠道的判定依据不同，由连接器自己给。
        """
        return None

    async def close(self) -> None:
        return None


__all__ = [
    "ConnectorCapability",
    "ConfigField",
    "RawItem",
    "Metric",
    "NormalizedItem",
    "NewsDraft",
    "Provenance",
    "SourceKind",
    "SyncCursor",
    "DataSourceConnector",
]
