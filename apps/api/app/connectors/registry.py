"""数据源注册表（插件式）。

新增数据源 = 新增一个文件 + @register 装饰器，不需要改调度器、API、前端。

★ 为什么还需要"别名"：
注册表 key 是**持久化在数据库里**的（`source_connectors.key`）。
一旦某个连接器被拆分/改名，历史行就会让 `get_connector_class()` 抛 LookupError，
表现为"升级后同步直接失败"——而且是运行到那一刻才炸。
别名让老数据继续能跑，同时给出人话迁移提示，让用户自己决定何时重建。
"""

from __future__ import annotations

from app.connectors.base import DataSourceConnector

_REGISTRY: dict[str, type[DataSourceConnector]] = {}
# 历史 key → 现行 key
_ALIASES: dict[str, tuple[str, str]] = {}


def register(cls: type[DataSourceConnector]) -> type[DataSourceConnector]:
    if not getattr(cls, "key", None):
        raise ValueError(f"connector must define `key`: {cls.__name__}")
    if cls.key in _REGISTRY:
        raise ValueError(f"duplicate connector key: {cls.key}")
    if cls.key in _ALIASES:
        raise ValueError(f"connector key 与历史别名冲突: {cls.key}")
    _REGISTRY[cls.key] = cls
    return cls


def alias(old_key: str, new_key: str, note: str = "") -> None:
    """登记一个历史 key → 现行 key 的映射。

    `note` 是给用户看的人话说明（会随 API 出参返回），例如
    "该连接器已拆分：快讯请新建「Tushare 新闻快讯」"。
    """
    if old_key in _REGISTRY:
        raise ValueError(f"alias 的旧 key 仍是已注册连接器: {old_key}")
    if new_key not in _REGISTRY:
        raise ValueError(f"alias 指向未注册的 key: {new_key}（注意：必须先 import 目标连接器）")
    _ALIASES[old_key] = (new_key, note)


def resolve_key(key: str) -> str:
    """把历史 key 解析为现行 key；不是别名则原样返回。"""
    entry = _ALIASES.get(key)
    return entry[0] if entry else key


def is_alias(key: str) -> bool:
    return key in _ALIASES


def migration_hint(key: str) -> dict | None:
    """历史 key 的迁移提示；不是别名返回 None。"""
    entry = _ALIASES.get(key)
    if entry is None:
        return None
    new_key, note = entry
    return {
        "from_key": key,
        "to_key": new_key,
        "note": note or f"该连接器标识已迁移为 {new_key}，建议在数据源管理中重建以使用新能力",
    }


def get_connector_class(key: str) -> type[DataSourceConnector]:
    try:
        return _REGISTRY[resolve_key(key)]
    except KeyError as exc:
        raise LookupError(f"未注册的数据源: {key}") from exc


def available_connectors() -> list[dict]:
    """供 GET /connectors/available 动态渲染配置表单（只列现行 key，不含别名）。"""
    return [
        {
            "key": c.key,
            "name": c.display_name,
            "capability": c.capability.model_dump(),
        }
        for c in _REGISTRY.values()
    ]


def all_keys() -> list[str]:
    return list(_REGISTRY)


def alias_keys() -> list[str]:
    return list(_ALIASES)


__all__ = [
    "alias",
    "alias_keys",
    "all_keys",
    "available_connectors",
    "get_connector_class",
    "is_alias",
    "migration_hint",
    "register",
    "resolve_key",
]
