"""声明式字段映射（ChannelSpec）—— 把「新增渠道 = 写代码」变成「新增渠道 = 写声明」。

## 为什么要有这一层

现在每个连接器都在自己的 `normalize()` 里手写字段映射。加一个渠道就要复制一遍
"取字段 / 多候选回退 / 解析时间 / 补常量"；上游一改字段名要改多处；
接 RSS / 公众号 / 交易所时还得再写一遍。声明式之后：

    具体渠道只声明「哪个字段从哪来」 → 通用实现负责执行

## 纯函数约束

`ChannelSpec.normalize()` 不碰 IO、**不读时钟**。所有时间都来自入参：
- 条目自身的时间由 `time` 字段解析
- 解析失败时退到 `ctx["fetched_at"]`（调用方从 RawItem 带进来，是数据不是环境）
- 两者都没有 → 抛错（这是调用方的编程错误，不该静默用 now() 掩盖，否则回放不可复现）

## 取值器语法

- 普通路径：`"content"`、`"data.items.title"`（支持嵌套 dict 与 list 下标）
- 上下文引用：`$channel` / `$api` / `$fetched_at`
  —— 上游返回里没有、但语义必需的字段（如 tushare `news` 不返回 `src`）走这里注入
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.connectors.base import Metric, NormalizedItem, Provenance, SourceKind
from app.lib.hash import sha256_hex
from app.models.enums import ContentType

DEFAULT_TZ = "Asia/Shanghai"

# 上游时间字段格式极不统一，统一在这里兜住（新增渠道优先声明自己的格式）
DEFAULT_TIME_FORMATS: list[str] = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y%m%d %H%M%S",
    "%Y%m%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
]

_INDEX_RE = re.compile(r"^\d+$")


# ---------------------------------------------------------------- 时间


def ensure_tz(value: datetime, tz: str = DEFAULT_TZ) -> datetime:
    """统一为带时区。

    ★ 上游时间几乎都是 naive，而库里是 timestamptz —— 不显式加时区就会被
      PG 按会话时区隐式解释，同一份数据在不同环境落到不同瞬间。
    """
    zone = ZoneInfo(tz)
    return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)


def parse_time(
    value: Any, formats: list[str] | None = None, tz: str = DEFAULT_TZ
) -> datetime | None:
    """把各种形态的时间值解析为带时区 datetime；无法解析返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return ensure_tz(value, tz)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if seconds > 1e11:  # 毫秒级时间戳
            seconds /= 1000.0
        return datetime.fromtimestamp(seconds, tz=ZoneInfo(tz))

    text = str(value).strip()
    for fmt in list(formats or []) + DEFAULT_TIME_FORMATS:
        try:
            return ensure_tz(datetime.strptime(text, fmt), tz)
        except ValueError:
            continue
    try:
        return ensure_tz(datetime.fromisoformat(text), tz)
    except ValueError:
        return None


def to_decimal(value: Any) -> Decimal | None:
    """数值型事实的统一转换；空值 / 非数字 / NaN 一律返回 None（不猜）。"""
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return None if result.is_nan() else result


def text_of(value: Any) -> str | None:
    """任意值 → 去空白后的字符串；空值返回 None（避免入库一堆空串）。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------- 取值器


def dig(payload: Any, path: str) -> Any:
    """按点分路径取值，支持 dict 键与 list 下标：`data.items.0.title`。"""
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and _INDEX_RE.match(part):
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
        else:
            return None
        if current is None:
            return None
    return current


class FieldRef(BaseModel):
    """一个字段的取值声明：按序回退的候选路径 + 常量注入 + 默认值。"""

    candidates: list[str] = Field(default_factory=list)
    constant: Any = None
    default: Any = None

    @classmethod
    def of(cls, *paths: str) -> FieldRef:
        """最常用写法：`FieldRef.of("title", "name")` = 按序取第一个非空。"""
        return cls(candidates=list(paths))

    @classmethod
    def const(cls, value: Any) -> FieldRef:
        return cls(constant=value)


class MetricSpec(BaseModel):
    """数值型事实的取值声明（一行一个指标）。"""

    name: FieldRef
    value: FieldRef
    unit: FieldRef | None = None
    period: FieldRef | None = None
    ts_code: FieldRef | None = None
    observed_at: FieldRef | None = None
    attributes: dict[str, FieldRef] = Field(default_factory=dict)


# ---------------------------------------------------------------- 渠道声明


class ChannelSpec(BaseModel):
    """一个上游接口的完整字段映射声明。新增渠道只写这个。"""

    key: str  # 渠道/接口标识，进 provenance.api
    kind: SourceKind = SourceKind.news
    content_type: ContentType = ContentType.flash

    title: FieldRef | None = None
    content: FieldRef | None = None
    summary: FieldRef | None = None
    author: FieldRef | None = None
    url: FieldRef | None = None
    source_name: FieldRef | None = None
    time: FieldRef | None = None
    time_formats: list[str] = Field(default_factory=list)
    tz: str = DEFAULT_TZ

    # 键值扩展通道：上游专属字段（如 tushare 的 channels 分类）
    attributes: dict[str, FieldRef] = Field(default_factory=dict)
    static_attributes: dict[str, Any] = Field(default_factory=dict)

    # 静态标签与标的
    market_scope: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    symbol_fields: list[str] = Field(default_factory=list)
    symbol_transform: Callable[[str], str | None] | None = None

    # 数值事实通道
    metric_specs: list[MetricSpec] = Field(default_factory=list)

    # 幂等键：用**稳定字段**组合，而不是全字段 hash
    # （全字段 hash 会因为上游多回一个无关字段就产生新 id、重复占原始层）
    external_id_fields: list[str] = Field(default_factory=list)

    # ---- 取值 ----

    def resolve(self, ref: FieldRef | None, payload: dict, ctx: dict | None = None) -> Any:
        if ref is None:
            return None
        for path in ref.candidates:
            value = self._resolve_one(path, payload, ctx)
            if value is not None and value != "":
                return value
        if ref.constant is not None:
            return ref.constant
        return ref.default

    def _resolve_one(self, path: str, payload: dict, ctx: dict | None) -> Any:
        if path.startswith("$"):
            return (ctx or {}).get(path[1:])
        return dig(payload, path)

    @staticmethod
    def _text(value: Any) -> str | None:
        return text_of(value)

    # ---- 幂等键 ----

    def build_external_id(self, payload: dict, ctx: dict | None = None) -> str:
        """由稳定字段派生幂等键。

        上游没有 id 时（tushare 快讯就是），这是唯一能保证"跨次拉取同一条是同一个 id"
        又"不会因为无关字段变化而漂移"的做法。
        """
        parts = [str(self._resolve_one(f, payload, ctx) or "") for f in self.external_id_fields]
        if any(parts):
            return sha256_hex("|".join([self.key, *parts]))[:32]
        # 未声明幂等字段：退化成内容指纹（调用方应尽量声明）
        fallback = "|".join(
            [
                self.key,
                str(self.resolve(self.title, payload, ctx) or ""),
                str(self.resolve(self.content, payload, ctx) or ""),
            ]
        )
        return sha256_hex(fallback)[:32]

    # ---- 归一化 ----

    def normalize(
        self,
        payload: dict,
        *,
        ctx: dict | None = None,
        external_id: str | None = None,
        provenance: Provenance | None = None,
        source_ref: str | None = None,
        extra: dict | None = None,
    ) -> NormalizedItem:
        """原始 payload → 统一信封。纯函数：不碰 IO、不读时钟。"""
        scope = dict(ctx or {})
        scope.setdefault("api", self.key)

        published_at = parse_time(
            self.resolve(self.time, payload, scope), self.time_formats, self.tz
        )
        if published_at is None:
            published_at = parse_time(scope.get("fetched_at"), None, self.tz)
        if published_at is None:
            raise ValueError(
                f"{self.key}: 时间字段无法解析且未提供 ctx['fetched_at']"
                f"（time={self.time!r} payload_keys={sorted(payload.keys())}）"
            )

        attributes = {
            name: value
            for name, ref in self.attributes.items()
            if (value := self.resolve(ref, payload, scope)) is not None
        }
        attributes.update(self.static_attributes)

        symbols: list[str] = []
        for path in self.symbol_fields:
            raw_code = self._text(dig(payload, path))
            if not raw_code:
                continue
            code = self.symbol_transform(raw_code) if self.symbol_transform else raw_code
            if code and code not in symbols:
                symbols.append(code)

        metrics: list[Metric] = []
        for spec in self.metric_specs:
            metric = self._build_metric(spec, payload, scope)
            if metric is not None:
                metrics.append(metric)

        return NormalizedItem(
            external_id=external_id or self.build_external_id(payload, scope),
            kind=self.kind,
            content_type=self.content_type,
            title=self._text(self.resolve(self.title, payload, scope)),
            summary=self._text(self.resolve(self.summary, payload, scope)),
            content=self._text(self.resolve(self.content, payload, scope)),
            author=self._text(self.resolve(self.author, payload, scope)),
            url=self._text(self.resolve(self.url, payload, scope)) or source_ref,
            published_at=published_at,
            source_name=self._text(self.resolve(self.source_name, payload, scope)),
            symbols=symbols,
            industries=list(self.industries),
            market_scope=list(self.market_scope),
            attributes=attributes,
            metrics=metrics,
            provenance=provenance or Provenance(api=self.key),
            extra={**(extra or {}), "upstream_keys": sorted(payload.keys())},
        )

    def _build_metric(self, spec: MetricSpec, payload: dict, ctx: dict) -> Metric | None:
        value = to_decimal(self.resolve(spec.value, payload, ctx))
        if value is None:
            return None  # 取不到数值就不产出这条事实，不猜
        name = self._text(self.resolve(spec.name, payload, ctx)) or spec.name.candidates[0]
        observed = self.resolve(spec.observed_at, payload, ctx) if spec.observed_at else None
        return Metric(
            name=name,
            value=value,
            unit=self._text(self.resolve(spec.unit, payload, ctx)) if spec.unit else None,
            period=self._text(self.resolve(spec.period, payload, ctx)) if spec.period else None,
            ts_code=self._text(self.resolve(spec.ts_code, payload, ctx)) if spec.ts_code else None,
            observed_at=parse_time(observed, self.time_formats, self.tz) if observed else None,
            attributes={
                k: v
                for k, ref in spec.attributes.items()
                if (v := self.resolve(ref, payload, ctx)) is not None
            },
        )


__all__ = [
    "DEFAULT_TIME_FORMATS",
    "DEFAULT_TZ",
    "ChannelSpec",
    "FieldRef",
    "MetricSpec",
    "dig",
    "ensure_tz",
    "parse_time",
    "text_of",
    "to_decimal",
]
