import pytest
from fastapi.routing import APIRoute

from app.framework.exceptions import ClientException
from app.system.audit.router import _parse_time
from app.system.audit.router import router as audit_router
from app.system.auth.deps import require_admin, require_user
from app.system.user.enums import UserRole
from app.system.user.router import router as user_router


def test_role_normalization_and_rejection() -> None:
    assert UserRole.normalize(None) is UserRole.USER
    assert UserRole.normalize(" ADMIN ") is UserRole.ADMIN
    with pytest.raises(ValueError, match="角色类型不合法"):
        UserRole.normalize("owner")


def test_audit_time_parser_contract() -> None:
    assert _parse_time(None) is None
    assert _parse_time("2026-09-04 12:30:45").tzinfo is not None
    with pytest.raises(ClientException, match="时间格式"):
        _parse_time("2026/09/04")


def test_user_and_audit_routes_have_expected_guards() -> None:
    for route in user_router.routes:
        assert isinstance(route, APIRoute)
        calls = {dependency.call for dependency in route.dependant.dependencies}
        if route.path == "/user/password":
            assert require_user in calls
            assert require_admin not in calls
        else:
            assert require_admin in calls
    for route in audit_router.routes:
        assert isinstance(route, APIRoute)
        assert require_user in {dependency.call for dependency in route.dependant.dependencies}
