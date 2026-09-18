"""数据源注册表（插件式）。

新增数据源 = 新增一个文件 + @register 装饰器，不需要改调度器、API、前端。
"""

from __future__ import annotations

from app.connectors.base import DataSourceConnector

_REGISTRY: dict[str, type[DataSourceConnector]] = {}


def register(cls: type[DataSourceConnector]) -> type[DataSourceConnector]:
    if not getattr(cls, "key", None):
        raise ValueError(f"connector must define `key`: {cls.__name__}")
    if cls.key in _REGISTRY:
        raise ValueError(f"duplicate connector key: {cls.key}")
    _REGISTRY[cls.key] = cls
    return cls


def get_connector_class(key: str) -> type[DataSourceConnector]:
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        raise LookupError(f"未注册的数据源: {key}") from exc


def available_connectors() -> list[dict]:
    """供 GET /connectors/available 动态渲染配置表单。"""
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


__all__ = ["register", "get_connector_class", "available_connectors", "all_keys"]
