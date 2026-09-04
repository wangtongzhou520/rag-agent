"""业务变更审计查询接口。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from app.framework.exceptions import ClientException
from app.framework.result import Results
from app.system.audit.service import AuditQueryService
from app.system.auth.deps import require_user

router = APIRouter(
    prefix="/biz-change-logs",
    tags=["audit"],
    dependencies=[Depends(require_user)],
)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.now().astimezone().tzinfo
        )
    except ValueError as exc:
        raise ClientException("时间格式应为 yyyy-MM-dd HH:mm:ss") from exc


@router.get("")
async def page_logs(
    request: Request,
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    biz_type: str | None = Query(None, alias="bizType"),
    biz_id: str | None = Query(None, alias="bizId"),
    operation_type: str | None = Query(None, alias="operationType"),
    operator_id: str | None = Query(None, alias="operatorId"),
    operator_name: str | None = Query(None, alias="operatorName"),
    success: bool | None = None,
    begin_time: str | None = Query(None, alias="beginTime"),
    end_time: str | None = Query(None, alias="endTime"),
) -> dict:
    service: AuditQueryService = request.app.state.audit_query_service
    data = await service.page(
        current,
        size,
        biz_type=biz_type,
        biz_id=biz_id,
        operation_type=operation_type,
        operator_id=operator_id,
        operator_name=operator_name,
        success=success,
        begin_time=_parse_time(begin_time),
        end_time=_parse_time(end_time),
    )
    return Results.success(data).model_dump(by_alias=True)


@router.get("/{log_id}")
async def get_log(log_id: int, request: Request) -> dict:
    service: AuditQueryService = request.app.state.audit_query_service
    return Results.success(await service.get(log_id)).model_dump(by_alias=True)
