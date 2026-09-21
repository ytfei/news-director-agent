"""去重与哈希工具。

★ canonical_json：jsonb 序列化顺序不确定，必须先规范化再 hash，否则 ODS 幂等失效
（见 docs/05-database-schema.md §4.8）。

★ json_safe：pandas / numpy 的产物里有**非法 JSON 值**，必须在进入本系统时归一，
  否则 ODS 写入会直接失败（见下）。
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

# pandas 的 NaT / NA（不 import pandas 也能识别）
_MISSING_TYPE_NAMES = {"NaTType", "NAType"}


def json_safe(value: Any) -> Any:
    """递归把值转成**合法** JSON 可序列化的形态。

    ★ 为什么必须有这一层：tushare SDK 走 pandas，缺失字段是 `float('nan')`。
      `json.dumps` 默认输出裸 `NaN`（不是合法 JSON），PostgreSQL 的 jsonb 直接拒收：

          invalid input syntax for type json: Token "NaN" is invalid

      这不是理论问题——快讯里"没有标题"的行很常见，真实同步时就会撞上。
      上游的脏值只能在我们这一层归一，不能指望数据源干净。
    """
    if value is None:
        return None
    if isinstance(value, str):
        # 纯 NaN/inf 字符串同样非法，但更常见的是"真的叫 NaN"的业务值 → 不在这里处理
        return value
    if isinstance(value, bool):
        return value
    # ★ 必须在 datetime 判断**之前**：pandas 的 NaT 是 datetime 的子类，
    #   否则会被 isoformat() 变成一个看着很正常的字符串 "NaT" —— 脏数据伪装成有效值。
    if type(value).__name__ in _MISSING_TYPE_NAMES:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, Sequence):
        return [json_safe(v) for v in value]

    # numpy 标量（np.int64 / np.bool_ / np.float32…）：JSON 编码器不认，先降回 Python
    item = getattr(value, "item", None)
    if callable(item) and getattr(value, "shape", None) == ():
        try:
            return json_safe(item())
        except Exception:  # noqa: BLE001 降级失败就走下面的 str()
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def canonical_json(payload: Any) -> str:
    return json.dumps(
        json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_hash(payload: Any) -> str:
    """ODS 层：sha256(canonical_json(payload))

    canonical_json 内部已做 json_safe，所以"入库的形态"与"参与 hash 的形态"一致，
    否则同一份 payload 因为 NaN 的存在会算出与库里内容不匹配的 hash。
    """
    return sha256_hex(canonical_json(payload))


def content_hash(title: str | None, content: str | None) -> str:
    """DWD 层：sha256(规范化后的 title + content)，用于精确去重。

    title 可为 None：数值型条目（行情/资金流）没有标题，
    此时去重完全依赖 content，调用方需保证 content 足以区分。
    """
    normalized_title = " ".join((title or "").split())
    normalized_content = " ".join((content or "").split()) if content else ""
    return sha256_hex(f"{normalized_title}\n{normalized_content}")


def simhash64(text: str) -> int:
    """64 位 simhash，用于近似去重候选召回（汉明距离）。

    简化实现：按 2-gram 切分（对中文友好），每个 token 一个 64 位指纹后按位投票。
    """
    if not text:
        return 0
    cleaned = " ".join(text.split())
    tokens = [cleaned[i : i + 2] for i in range(len(cleaned) - 1)] or [cleaned]
    bits = [0] * 64
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for i in range(64):
            bits[i] += 1 if (value >> i) & 1 else -1
    out = 0
    for i in range(64):
        if bits[i] > 0:
            out |= 1 << i
    # 转成有符号 64 位，适配 bigint 列
    return out - (1 << 64) if out >= (1 << 63) else out


def hamming_distance(a: int, b: int) -> int:
    return bin((a ^ b) & ((1 << 64) - 1)).count("1")


__all__ = [
    "canonical_json",
    "sha256_hex",
    "json_safe",
    "payload_hash",
    "content_hash",
    "simhash64",
    "hamming_distance",
]
