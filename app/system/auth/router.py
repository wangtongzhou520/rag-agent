"""登录、登出和当前用户接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.framework.result import Results
from app.system.auth.deps import require_user
from app.system.auth.models import LoginRequest, LoginUser
from app.system.auth.service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
async def login(body: LoginRequest, request: Request) -> dict:
    service: AuthService = request.app.state.auth_service
    result = await service.login(body.username, body.password)
    return Results.success(result).model_dump(by_alias=True)


@router.post("/auth/logout")
async def logout(
    request: Request,
    token: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict:
    service: AuthService = request.app.state.auth_service
    await service.logout(token or "")
    return Results.success().model_dump(by_alias=True)


@router.get("/user/me")
async def me(user: Annotated[LoginUser, Depends(require_user)]) -> dict:
    return Results.success(user).model_dump(by_alias=True)
