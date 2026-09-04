"""M1 认证与权限守卫测试。"""

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.admin.dashboard import router as dashboard_router
from app.framework.exceptions import ClientException
from app.framework.result import ErrorCode
from app.knowledge.router import router as knowledge_router
from app.main import app
from app.rag.intent.router import router as intent_router
from app.rag.rewrite.router import router as rewrite_router
from app.rag.trace.router import router as trace_router
from app.system.auth.deps import require_admin, require_user
from app.system.auth.jwt import decode_token, encode_token
from app.system.auth.models import LoginUser
from app.system.auth.password import hash_password, verify_password
from app.system.user.router import router as user_router


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct horse")
    assert encoded != "correct horse"
    assert verify_password("correct horse", encoded)
    assert not verify_password("wrong", encoded)


def test_jwt_round_trip_and_signature_rejection() -> None:
    secret_a = "a" * 32
    secret_b = "b" * 32
    token, jti = encode_token(42, secret_a, 60)
    assert decode_token(token, secret_a) == (42, jti)
    try:
        decode_token(token, secret_b)
    except ClientException as exc:
        assert "未登录" in exc.message
    else:
        raise AssertionError("expected ClientException")


async def test_require_admin_accepts_role_case_insensitively() -> None:
    user = LoginUser(userId=1, username="admin", role="admin")

    assert await require_admin(user) is user


async def test_require_admin_rejects_regular_users_with_forbidden_code() -> None:
    user = LoginUser(userId=2, username="reader", role="USER")

    with pytest.raises(ClientException) as caught:
        await require_admin(user)

    assert caught.value.code == str(ErrorCode.FORBIDDEN)
    assert caught.value.message == "无管理员权限"


async def test_regular_user_cannot_access_management_routes(client: AsyncClient) -> None:
    async def regular_user() -> LoginUser:
        return LoginUser(userId=2, username="reader", role="USER")

    app.dependency_overrides[require_user] = regular_user
    try:
        for path in (
            "/knowledge-base",
            "/intent-tree/trees",
            "/mappings",
            "/rag/traces/runs",
            "/admin/dashboard/overview",
            "/users",
        ):
            response = await client.get(path)
            assert response.json()["code"] == str(ErrorCode.FORBIDDEN), path
    finally:
        app.dependency_overrides.pop(require_user, None)


async def test_regular_user_can_preview_answer_source(client: AsyncClient) -> None:
    class PreviewService:
        async def preview_document(self, doc_id: int) -> str:
            assert doc_id == 7
            return "可供普通用户查看的来源内容"

    async def regular_user() -> LoginUser:
        return LoginUser(userId=2, username="reader", role="USER")

    original_service = app.state.knowledge_service
    app.state.knowledge_service = PreviewService()
    app.dependency_overrides[require_user] = regular_user
    try:
        response = await client.get("/knowledge-base/docs/7/preview")
        assert response.json()["code"] == str(ErrorCode.SUCCESS)
        assert response.json()["data"] == "可供普通用户查看的来源内容"
    finally:
        app.state.knowledge_service = original_service
        app.dependency_overrides.pop(require_user, None)


def test_all_management_routes_declare_admin_guard() -> None:
    public_knowledge_paths = {
        "/knowledge-base/docs/{doc_id}/preview",
        "/knowledge-base/docs/{doc_id}/file",
    }
    checked = 0
    for router in (
        knowledge_router,
        intent_router,
        rewrite_router,
        trace_router,
        dashboard_router,
        user_router,
    ):
        for route in router.routes:
            assert isinstance(route, APIRoute)
            calls = {dependency.call for dependency in route.dependant.dependencies}
            if (router is knowledge_router and route.path in public_knowledge_paths) or (
                router is user_router and route.path == "/user/password"
            ):
                assert require_admin not in calls
                assert require_user in calls
            else:
                assert require_admin in calls
            checked += 1
    assert checked >= 30
