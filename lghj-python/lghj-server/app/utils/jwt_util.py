"""JWT 工具模块。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/utils/JwtUtil.java

契约：HS256 算法，secret 为 UTF-8 字节（默认 itfeng），claims 中含
userId/userType，另写入标准声明 exp（原 setExpiration，毫秒时间戳）。
"""

from __future__ import annotations

from typing import Any

import jwt


def create_jwt(secret_key: str, ttl_millis: int, claims: dict[str, Any]) -> str:
    """生成 JWT（对应 JwtUtil.createJWT）。

    - 算法固定 HS256
    - exp = 当前毫秒时间 + ttlMillis（PyJWT 接受秒级时间戳或 datetime，此处换算为秒）
    """
    import time

    payload = dict(claims)
    payload["exp"] = int((time.time() * 1000 + ttl_millis) // 1000)
    return jwt.encode(payload, secret_key.encode("utf-8"), algorithm="HS256")


def parse_jwt(secret_key: str, token: str) -> dict[str, Any]:
    """解析 JWT（对应 JwtUtil.parseJWT）。

    校验失败（过期/签名错误/格式非法）时抛出 jwt.PyJWTError，
    与原 io.jsonwebtoken.JwtException 语义对应，由调用方捕获处理。
    """
    return jwt.decode(token, secret_key.encode("utf-8"), algorithms=["HS256"])
