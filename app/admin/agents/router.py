"""Agent Profile 与 Prompt Slot 管理 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.admin.agents.schemas import AgentProfileWrite, AgentPromptWrite
from app.admin.agents.service import AgentAdminService
from app.framework.result import Results
from app.system.audit.decorator import audit_log
from app.system.auth.deps import require_admin
from app.system.auth.models import LoginUser

router = APIRouter(
    prefix="/agents", tags=["agents"], dependencies=[Depends(require_admin)]
)


def _service(request: Request) -> AgentAdminService:
    return request.app.state.agent_admin_service


@router.get("")
async def list_agents(request: Request) -> dict:
    return Results.success(await _service(request).list_profiles()).model_dump(
        by_alias=True
    )


@router.post("")
@audit_log(
    biz_type="AGENT_PROFILE",
    op="CREATE",
    success_desc=lambda values, _: f"创建智能体：{values['body'].name.strip()}",
    fail_desc="创建智能体失败",
)
async def create_agent(
    body: AgentProfileWrite,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    return Results.success(
        await _service(request).create(body, user.user_id)
    ).model_dump(by_alias=True)


@router.put("/{agent_id}")
@audit_log(
    biz_type="AGENT_PROFILE",
    op="UPDATE",
    success_desc="更新智能体",
    fail_desc="更新智能体失败",
)
async def update_agent(
    agent_id: int,
    body: AgentProfileWrite,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    await _service(request).update(agent_id, body, user.user_id)
    return Results.success().model_dump(by_alias=True)


@router.delete("/{agent_id}")
@audit_log(
    biz_type="AGENT_PROFILE",
    op="DELETE",
    success_desc="删除智能体",
    fail_desc="删除智能体失败",
)
async def delete_agent(agent_id: int, request: Request) -> dict:
    await _service(request).delete(agent_id)
    return Results.success().model_dump(by_alias=True)


@router.post("/{agent_id}/activate")
@audit_log(
    biz_type="AGENT_PROFILE",
    op="ENABLE",
    success_desc="激活智能体",
    fail_desc="激活智能体失败",
)
async def activate_agent(
    agent_id: int,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    await _service(request).activate(agent_id, user.user_id)
    return Results.success().model_dump(by_alias=True)


@router.get("/{agent_id}/prompts")
async def agent_prompts(agent_id: int, request: Request) -> dict:
    return Results.success(await _service(request).prompts(agent_id)).model_dump(
        by_alias=True
    )


@router.get("/prompt-slots/{slot_key}/default")
async def default_prompt(slot_key: str, request: Request) -> dict:
    return Results.success(
        await _service(request).default_prompt(slot_key)
    ).model_dump(by_alias=True)


@router.put("/{agent_id}/prompts/{slot_key}")
@audit_log(
    biz_type="AGENT_PROFILE",
    op="UPDATE",
    success_desc="更新智能体 Prompt",
    fail_desc="更新智能体 Prompt 失败",
)
async def save_agent_prompt(
    agent_id: int,
    slot_key: str,
    body: AgentPromptWrite,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    await _service(request).save_prompt(
        agent_id, slot_key, body.content, user.user_id
    )
    return Results.success().model_dump(by_alias=True)
