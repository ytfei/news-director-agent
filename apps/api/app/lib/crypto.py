"""连接器凭据加密存储。

生产用 KMS；单机/私有化用 Fernet（密钥由环境变量注入）。
库里只存密文引用，绝不存明文（docs/05-database-schema.md §4.7）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet

_SECRET_KEY_ENV = "NDA_SECRET_KEY"


def _fernet() -> Fernet:
    raw = os.getenv(_SECRET_KEY_ENV)
    if not raw:
        # 开发兜底：由固定盐派生，重启后仍可解密，但**生产必须注入 NDA_SECRET_KEY**
        raw = base64.urlsafe_b64encode(
            hashlib.sha256(b"nda-dev-only-secret").digest()
        ).decode()
        return Fernet(raw)
    if raw.startswith("fernet:"):
        return Fernet(raw.removeprefix("fernet:").encode())
    # 任意字符串 → 派生成合法 32 字节 key
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))


def encrypt_secret(payload: dict) -> str:
    token = _fernet().encrypt(json.dumps(payload, separators=(",", ":")).encode())
    return f"fernet:{token.decode()}"


def decrypt_secret(ref: str) -> dict:
    token = ref.removeprefix("fernet:")
    return json.loads(_fernet().decrypt(token.encode()).decode())


__all__ = ["encrypt_secret", "decrypt_secret"]
