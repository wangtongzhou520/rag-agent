"""认证服务：用户校验、JWT 签发和 Redis 白名单。"""

import json

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.config import AuthSettings, RedisSettings
from app.framework.exceptions import ClientException, ServiceException
from app.framework.result import ErrorCode
from app.system.auth.jwt import decode_token, encode_token
from app.system.auth.models import LoginUser, LoginVO
from app.system.auth.password import verify_password
from app.system.user.models import User


class AuthService:
    def __init__(
        self,
        engine: AsyncEngine,
        redis: Redis,
        settings: AuthSettings,
        redis_settings: RedisSettings,
    ) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._redis = redis
        self._settings = settings
        self._prefix = redis_settings.key_prefix

    def development_user(self) -> LoginUser:
        return LoginUser(
            user_id=self._settings.development_user_id,
            username="development",
            role="ADMIN",
        )

    async def login(self, username: str, password: str) -> LoginVO:
        if not self._settings.enabled:
            raise ServiceException("认证尚未启用")
        if not self._settings.jwt_secret:
            raise ServiceException("认证密钥未配置")
        username = username.strip()
        if not username or not password:
            raise ClientException("用户名或密码不能为空")
        async with self._sessions() as session:
            user = await session.scalar(
                select(User).where(
                    User.username == username,
                    User.enabled == 1,
                    User.deleted == 0,
                )
            )
        if user is None or not verify_password(password, user.password_hash):
            raise ClientException("用户名或密码错误")
        token, jti = encode_token(
            user.id, self._settings.jwt_secret, self._settings.token_ttl_seconds
        )
        snapshot = LoginUser(
            user_id=user.id,
            username=user.username,
            role=user.role,
            avatar=user.avatar or self._settings.default_avatar or None,
        )
        await self._redis.set(
            f"{self._prefix}auth:session:{jti}",
            snapshot.model_dump_json(by_alias=True),
            ex=self._settings.token_ttl_seconds,
        )
        user_sessions = f"{self._prefix}auth:user-sessions:{user.id}"
        await self._redis.sadd(user_sessions, jti)
        await self._redis.expire(user_sessions, self._settings.token_ttl_seconds)
        return LoginVO(
            user_id=user.id, role=user.role, token=token, avatar=snapshot.avatar
        )

    async def authenticate(self, token: str) -> tuple[LoginUser, str]:
        if not self._settings.enabled:
            return self.development_user(), ""
        if not token or not self._settings.jwt_secret:
            raise ClientException("未登录或登录已过期", code=ErrorCode.UNAUTHORIZED)
        user_id, jti = decode_token(token, self._settings.jwt_secret)
        try:
            raw = await self._redis.get(f"{self._prefix}auth:session:{jti}")
        except Exception as exc:
            raise ClientException(
                "未登录或登录已过期", code=ErrorCode.UNAUTHORIZED
            ) from exc
        if not raw:
            raise ClientException("未登录或登录已过期", code=ErrorCode.UNAUTHORIZED)
        user = LoginUser.model_validate(json.loads(raw))
        if user.user_id != user_id:
            raise ClientException("未登录或登录已过期", code=ErrorCode.UNAUTHORIZED)
        return user, jti

    async def logout(self, token: str) -> None:
        if not self._settings.enabled or not token:
            return
        user_id, jti = decode_token(token, self._settings.jwt_secret)
        await self._redis.delete(f"{self._prefix}auth:session:{jti}")
        await self._redis.srem(f"{self._prefix}auth:user-sessions:{user_id}", jti)

    async def invalidate_user_sessions(self, user_id: int) -> None:
        """角色、身份或密码变化后立即注销该用户全部 token。"""
        user_sessions = f"{self._prefix}auth:user-sessions:{user_id}"
        session_ids = await self._redis.smembers(user_sessions)
        keys = [f"{self._prefix}auth:session:{jti}" for jti in session_ids]
        if keys:
            await self._redis.delete(*keys)
        await self._redis.delete(user_sessions)
