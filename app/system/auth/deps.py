"""FastAPI 认证依赖。"""

from typing import Annotated

from fastapi import Header, Request

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
