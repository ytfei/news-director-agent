"""arq worker 包。

★ 必须导入 app.connectors 以触发连接器注册，否则注册表为空。
"""

from app.connectors import (  # noqa: F401
    TushareArticleConnector,
    TushareFlashConnector,
    available_connectors,
)

__all__ = [
    "TushareArticleConnector",
    "TushareFlashConnector",
    "available_connectors",
]
