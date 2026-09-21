"""tushare 系连接器。

导入本模块即完成注册（`@register` 在类定义时执行）。
新增 tushare 接口时：在 `specs.py` 写一个 `ChannelSpec`，必要时加一个连接器类，并在此导出。

## 历史 key 的兼容

原 `tushare.news` 一个连接器覆盖 6 个接口（含快讯），现已拆分：

    tushare.flash    快讯（doc 143，按 src 分组）
    tushare.article  长文 / 公告 / 政策 / 研报

`source_connectors.key` 是**持久化在数据库里**的，所以老行必须继续可读可跑，
否则升级后同步会在取连接器类的那一刻直接抛 LookupError（而不是给出可读提示）。

别名指向 `tushare.article` 而不是 `tushare.flash`：老行的配置是
`config.endpoints=[...]`（多接口），指向 article 能**保留它原有的行为**；
指向 flash 则因为缺少 `srcs` 配置会立刻变成"未配置来源"错误。
"""

from app.connectors.registry import alias
from app.connectors.tushare.connector import TushareArticleConnector
from app.connectors.tushare.flash import TushareFlashConnector

# 必须在两个类都注册完之后再声明别名
alias(
    "tushare.news",
    "tushare.article",
    note=(
        "该连接器已拆分：快讯请新建「Tushare 新闻快讯」（可选来源），"
        "本连接器继续负责长文 / 公告 / 政策 / 研报"
    ),
)

__all__ = ["TushareArticleConnector", "TushareFlashConnector"]
