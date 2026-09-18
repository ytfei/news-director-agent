"""去重与哈希工具。

★ canonical_json：jsonb 序列化顺序不确定，必须先规范化再 hash，否则 ODS 幂等失效
（见 docs/05-database-schema.md §4.8）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_hash(payload: Any) -> str:
    """ODS 层：sha256(canonical_json(payload))"""
    return sha256_hex(canonical_json(payload))


def content_hash(title: str, content: str | None) -> str:
    """DWD 层：sha256(规范化后的 title + content)，用于精确去重。"""
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
    "payload_hash",
    "content_hash",
    "simhash64",
    "hamming_distance",
]
