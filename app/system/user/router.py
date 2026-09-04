"""用户管理与本人改密接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.framework.result import Results
from app.system.audit.decorator import audit_log
from app.system.auth.deps import require_admin, require_user
from app.system.auth.models import LoginUser
from app.system.user.schemas import (
    PasswordChangeRequest,
    UserCreateRequest,
    UserUpdateRequest,
)
from app.system.user.service import UserService

router = APIRouter(tags=["users"])


def _service(request: Request) -> UserService:
    return request.app.state.user_service


@router.get("/users", dependencies=[Depends(require_admin)])
async def page_users(
    request: Request,
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
) -> dict:
    return Results.success(
        await _service(request).page(current, size, keyword)
    ).model_dump(by_alias=True)


@router.post("/users", dependencies=[Depends(require_admin)])
@audit_log(
    biz_type="USER",
    op="CREATE",
    success_desc=lambda values, _: f"创建用户：{values['body'].username.strip()}",
    fail_desc=lambda values, _: f"创建用户失败：{values['body'].username.strip()}",
)
async def create_user(body: UserCreateRequest, request: Request) -> dict:
    user_id = await _service(request).create(body)
    return Results.success(str(user_id)).model_dump(by_alias=True)


@router.put("/users/{user_id}", dependencies=[Depends(require_admin)])
@audit_log(
    biz_type="USER",
    op="UPDATE",
    success_desc="更新用户",
    fail_desc="更新用户失败",
)
async def update_user(user_id: int, body: UserUpdateRequest, request: Request) -> dict:
    await _service(request).update(user_id, body)
    return Results.success().model_dump(by_alias=True)


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
@audit_log(
    biz_type="USER",
    op="DELETE",
    success_desc="删除用户",
    fail_desc="删除用户失败",
)
async def delete_user(user_id: int, request: Request) -> dict:
    await _service(request).delete(user_id)
    return Results.success().model_dump(by_alias=True)


@router.put("/user/password")
@audit_log(
    biz_type="USER",
    op="UPDATE",
    success_desc="修改本人密码",
    fail_desc="修改本人密码失败",
)
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
) -> dict:
    await _service(request).change_password(
        user.user_id, body.current_password, body.new_password
    )
    return Results.success().model_dump(by_alias=True)
