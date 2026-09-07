"""运行时与模型设置只读管理 API。"""

from fastapi import APIRouter, Depends, Request

from app.admin.runtime.service import RuntimeSettingsService
from app.framework.result import Results
from app.system.auth.deps import require_admin

router = APIRouter(
    prefix="/rag/settings",
    tags=["runtime-settings"],
    dependencies=[Depends(require_admin)],
)


def _service(request: Request) -> RuntimeSettingsService:
    return request.app.state.runtime_settings_service


@router.get("")
async def runtime_settings(request: Request) -> dict:
    return Results.success(await _service(request).snapshot()).model_dump(
        by_alias=True
    )
