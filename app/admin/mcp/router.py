"""MCP 服务发现、启停和调试 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.admin.mcp.schemas import McpDebugRequest, McpEnabledWrite
from app.admin.mcp.service import McpAdminService
from app.framework.result import Results
from app.system.audit.decorator import audit_log
from app.system.auth.deps import require_admin
from app.system.auth.models import LoginUser

router = APIRouter(prefix="/mcp", tags=["mcp"], dependencies=[Depends(require_admin)])


def _service(request: Request) -> McpAdminService:
    return request.app.state.mcp_admin_service


@router.get("/servers")
async def list_servers(request: Request) -> dict:
    return Results.success(await _service(request).list_servers()).model_dump(by_alias=True)


@router.post("/servers/{server_name}/refresh")
@audit_log(
    biz_type="MCP_SERVER",
    op="RUN",
    success_desc="重新发现 MCP Server",
    fail_desc="重新发现 MCP Server 失败",
)
async def refresh_server(server_name: str, request: Request) -> dict:
    return Results.success(await _service(request).refresh(server_name)).model_dump(by_alias=True)


@router.put("/servers/{server_name}/enabled")
@audit_log(
    biz_type="MCP_SERVER",
    op="UPDATE",
    success_desc="更新 MCP Server 状态",
    fail_desc="更新 MCP Server 状态失败",
)
async def set_server_enabled(
    server_name: str,
    body: McpEnabledWrite,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    await _service(request).set_server_enabled(server_name, body.enabled, user.user_id)
    return Results.success().model_dump(by_alias=True)


@router.get("/tools")
async def list_tools(request: Request) -> dict:
    return Results.success(await _service(request).list_tools()).model_dump(by_alias=True)


@router.put("/tools/{server_name}/{tool_name}/enabled")
@audit_log(
    biz_type="MCP_TOOL",
    op="UPDATE",
    success_desc="更新 MCP 工具状态",
    fail_desc="更新 MCP 工具状态失败",
)
async def set_tool_enabled(
    server_name: str,
    tool_name: str,
    body: McpEnabledWrite,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    await _service(request).set_tool_enabled(
        f"{server_name}:{tool_name}", body.enabled, user.user_id
    )
    return Results.success().model_dump(by_alias=True)


@router.post("/tools/{server_name}/{tool_name}/debug")
@audit_log(
    biz_type="MCP_TOOL",
    op="RUN",
    success_desc="调试 MCP 工具",
    fail_desc="调试 MCP 工具失败",
)
async def debug_tool(
    server_name: str,
    tool_name: str,
    body: McpDebugRequest,
    request: Request,
) -> dict:
    return Results.success(
        await _service(request).debug(f"{server_name}:{tool_name}", body.parameters)
    ).model_dump(by_alias=True)
