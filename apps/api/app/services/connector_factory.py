"""按注册表实例化连接器，并解密凭据。"""

from __future__ import annotations

from typing import Any

from app.connectors.base import DataSourceConnector
from app.connectors.registry import get_connector_class
from app.lib.crypto import decrypt_secret
from app.models.enums import ConnectorStatus
from app.models.ingest import SourceConnector


def build_connector(row: SourceConnector) -> DataSourceConnector:
    cls = get_connector_class(row.key)
    credentials: dict[str, Any] = {}
    if row.credentials_ref:
        try:
            credentials = decrypt_secret(row.credentials_ref)
        except Exception:  # noqa: BLE001 凭据解不开时降级为无凭据，由 validate 给出人话提示
            credentials = {}
    return cls(config=row.config or {}, credentials=credentials)


def connector_type_of(key: str) -> str:
    """从注册 key 推断 connector_type 枚举值（如 'tushare.news' -> 'tushare'）。"""
    return key.split(".", 1)[0]


__all__ = ["build_connector", "connector_type_of", "ConnectorStatus"]
