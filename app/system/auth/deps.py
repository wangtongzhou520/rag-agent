"""FastAPI 认证依赖。"""

from typing import Annotated

from fastapi import Depends, Header, Request

from app.framework.exceptions import ClientException
from app.framework.result import ErrorCode
from app.system.auth.models import LoginUser
from app.system.auth.service import AuthService


async def require_user(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> LoginUser:
    service: AuthService = request.app.state.auth_service
    user, _ = await service.authenticate(authorization or "")
    request.state.current_user = user
    return user


async def require_admin(
    user: Annotated[LoginUser, Depends(require_user)],
) -> LoginUser:
    if user.role.strip().upper() != "ADMIN":
        raise ClientException("无管理员权限", code=ErrorCode.FORBIDDEN)
    return user
