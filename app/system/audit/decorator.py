"""业务函数审计装饰器。"""

import inspect
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any

from fastapi import Request

from app.framework.logging import get_logger
from app.system.audit.context import AuditContext
from app.system.audit.service import AuditRecord, AuditRecordService

logger = get_logger(__name__)
Description = str | Callable[[Mapping[str, Any], Any], str]


def audit_log(
    *, biz_type: str, op: str, success_desc: Description, fail_desc: Description
) -> Callable:
    def decorate(function: Callable) -> Callable:
        signature = inspect.signature(function)

        @wraps(function)
        async def wrapped(*args, **kwargs):
            values = signature.bind(*args, **kwargs).arguments
            request = next((value for value in values.values() if isinstance(value, Request)), None)
            token = AuditContext.begin()
            try:
                result = await function(*args, **kwargs)
            except Exception as exc:
                state = AuditContext.current()
                if not state.skipped:
                    await _record(
                        request,
                        state,
                        function,
                        biz_type,
                        op,
                        _description(fail_desc, values, exc),
                        False,
                        str(exc),
                    )
                raise
            else:
                state = AuditContext.current()
                if not state.skipped:
                    await _record(
                        request,
                        state,
                        function,
                        biz_type,
                        op,
                        _description(success_desc, values, result),
                        True,
                        None,
                    )
                return result
            finally:
                AuditContext.reset(token)

        return wrapped

    return decorate


def _description(value: Description, arguments: Mapping[str, Any], result: Any) -> str:
    return value(arguments, result) if callable(value) else value


async def _record(
    request: Request | None,
    state,
    function: Callable,
    biz_type: str,
    op: str,
    description: str,
    success: bool,
    error_message: str | None,
) -> None:
    if request is None:
        return
    service: AuditRecordService | None = getattr(request.app.state, "audit_record_service", None)
    if service is None:
        return
    user = getattr(request.state, "current_user", None)
    forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    ip = forwarded or request.headers.get("X-Real-IP") or (request.client.host if request.client else None)
    try:
        await service.record(
            AuditRecord(
                biz_type=biz_type,
                biz_id=state.biz_id,
                operation_type=op,
                action_desc=description,
                before=state.before,
                after=state.after,
                operator_id=str(user.user_id) if user else "SYSTEM",
                operator_name=user.username if user else None,
                operator_role=user.role if user else None,
                success=success,
                error_message=error_message,
                class_name=function.__module__,
                method_name=function.__qualname__,
                ip=ip,
                user_agent=request.headers.get("User-Agent"),
            )
        )
    except Exception:
        logger.warning("audit record write failed", exc_info=True)
