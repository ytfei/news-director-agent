"""数据源接入层契约。

设计见 docs/04-architecture.md §4：
- Connector 只负责"拿到原始数据"
- normalize() 必须是纯函数，便于回放与单测
- 新增数据源 = 新增一个文件 + @register，不改调度器 / API / 前端
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConnectorCapability(BaseModel):
    """连接器能力声明——调度器据此决定同步策略与 UI 展示。"""

    content_types: list[str] = Field(default_factory=list)
    supports_incremental: bool = True
    supports_backfill: bool = True
    rate_limit_per_min: int | None = None
    requires_credentials: bool = False


class RawItem(BaseModel):
    """原始条目：不做语义加工，只做必要的定位与幂等标识。"""

    external_id: str  # 源内唯一 id（没有则用内容 hash）
    payload: dict[str, Any]  # 原始结构原样保留
    fetched_at: datetime
    source_ref: str | None = None  # 原文 url / 文件 key
    content_type: str = "flash"


class NewsDraft(BaseModel):
    """归一化中间态：Connector 尽力填，缺失由 Enricher 补。"""

    external_id: str
    content_type: Literal[
        "flash",
        "article",
        "announcement",
        "policy",
        "research_report",
        "interactive_qa",
        "social_post",
        "market_data",
    ]
    title: str
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
    market_scope: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class SyncCursor(BaseModel):
    """增量游标：每个连接器独立持久化，支持断点续拉。"""

    last_external_id: str | None = None
    last_published_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class DataSourceConnector(ABC):
    """所有数据源必须实现的契约。"""

    key: str  # 唯一标识，如 "tushare.news"
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
    def normalize(self, raw: RawItem) -> NewsDraft:
        """原始 → 归一化。必须是纯函数，便于回放与单测。"""

    async def close(self) -> None:
        return None


__all__ = [
    "ConnectorCapability",
    "RawItem",
    "NewsDraft",
    "SyncCursor",
    "DataSourceConnector",
]
