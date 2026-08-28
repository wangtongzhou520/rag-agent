"""JWT 编解码。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

from app.framework.exceptions import ClientException
from app.framework.result import ErrorCode


def encode_token(user_id: int, secret: str, ttl_seconds: int) -> tuple[str, str]:
    now = datetime.now(UTC)
    jti = uuid4().hex
    token = jwt.encode(
        {
            "sub": str(user_id),
            "jti": jti,
            "iat": now,
            "exp": now + timedelta(seconds=ttl_seconds),
        },
        secret,
        algorithm="HS256",
    )
    return token, jti


def decode_token(token: str, secret: str) -> tuple[int, str]:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return int(payload["sub"]), str(payload["jti"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise ClientException(
            "未登录或登录已过期", code=ErrorCode.UNAUTHORIZED
        ) from exc
