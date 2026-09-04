import pytest
from fastapi import FastAPI, Request

from app.system.audit.context import AuditContext
from app.system.audit.decorator import audit_log
from app.system.audit.diff import collect_diff
from app.system.auth.models import LoginUser


def test_collect_diff_handles_nested_arrays_escaping_and_root() -> None:
    assert collect_diff({"a/b": {"~key": [1, 2]}}, {"a/b": {"~key": [1, 3, 4]}}) == [
        {"field": "/a~1b/~0key/1", "before": 2, "after": 3},
        {"field": "/a~1b/~0key/2", "before": None, "after": 4},
    ]
    assert collect_diff(None, {"enabled": True}) == [
        {"field": "/", "before": None, "after": {"enabled": True}}
    ]
    assert collect_diff({"same": 1}, {"same": 1}) == []


class RecordingAuditService:
    def __init__(self) -> None:
        self.records = []

    async def record(self, value) -> None:
        self.records.append(value)


def _request(service: RecordingAuditService) -> Request:
    app = FastAPI()
    app.state.audit_record_service = service
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 1234),
            "app": app,
        }
    )
    request.state.current_user = LoginUser(userId=7, username="operator", role="ADMIN")
    return request


async def test_audit_decorator_records_success_and_preserves_result() -> None:
    recorder = RecordingAuditService()

    @audit_log(biz_type="USER", op="CREATE", success_desc="created", fail_desc="failed")
    async def action(request: Request) -> str:
        AuditContext.put("42", None, {"username": "reader"})
        return "ok"

    assert await action(_request(recorder)) == "ok"
    assert len(recorder.records) == 1
    record = recorder.records[0]
    assert record.biz_id == "42"
    assert record.operator_name == "operator"
    assert record.success is True


async def test_audit_decorator_records_failure_and_reraises() -> None:
    recorder = RecordingAuditService()

    @audit_log(biz_type="USER", op="UPDATE", success_desc="updated", fail_desc="failed")
    async def action(request: Request) -> None:
        AuditContext.put("9", {"role": "user"}, None)
        raise ValueError("bad role")

    with pytest.raises(ValueError, match="bad role"):
        await action(_request(recorder))
    assert recorder.records[0].success is False
    assert recorder.records[0].error_message == "bad role"


async def test_audit_context_skip_prevents_record() -> None:
    recorder = RecordingAuditService()

    @audit_log(biz_type="USER", op="UPDATE", success_desc="updated", fail_desc="failed")
    async def action(request: Request) -> None:
        AuditContext.skip()

    await action(_request(recorder))
    assert recorder.records == []
