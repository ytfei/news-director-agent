"""数据源接入层。

★ 导入本包即注册所有内置连接器。worker（arq）与 API 都必须经过这里，
否则注册表为空、`build_connector` 会抛 "未注册的数据源"。
"""

from __future__ import annotations

from app.connectors.base import (  # noqa: F401
    ConfigField,
    ConnectorCapability,
    DataSourceConnector,
    Metric,
    NewsDraft,
    NormalizedItem,
    Provenance,
    RawItem,
    SourceKind,
    SyncCursor,
)
from app.connectors.registry import (  # noqa: F401
    alias,
    alias_keys,
    all_keys,
    available_connectors,
    get_connector_class,
    is_alias,
    migration_hint,
    register,
    resolve_key,
)

# 内置连接器：新增数据源时在此追加导入（配合 @register 即可）
from app.connectors.tushare import (  # noqa: F401
    TushareArticleConnector,
    TushareFlashConnector,
)

__all__ = [
    "ConfigField",
    "ConnectorCapability",
    "DataSourceConnector",
    "Metric",
    "NewsDraft",
    "NormalizedItem",
    "Provenance",
    "RawItem",
    "SourceKind",
    "SyncCursor",
    "register",
    "alias",
    "resolve_key",
    "is_alias",
    "migration_hint",
    "get_connector_class",
    "available_connectors",
    "all_keys",
    "alias_keys",
    "TushareArticleConnector",
    "TushareFlashConnector",
]
