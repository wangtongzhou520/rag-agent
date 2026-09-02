"""意图树管理 REST 接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.framework.exceptions import ClientException
from app.framework.result import Results
from app.rag.intent.node import IntentNode
from app.rag.intent.schemas import IntentNodeBatch, IntentNodeVO, IntentNodeWrite
from app.rag.intent.service import IntentTreeService
from app.system.auth.deps import require_admin
from app.system.auth.models import LoginUser

router = APIRouter(prefix="/intent-tree", tags=["intent"], dependencies=[Depends(require_admin)])


def _service(request: Request) -> IntentTreeService:
    return request.app.state.intent_tree_service


def _vo(node: IntentNode) -> IntentNodeVO:
    return IntentNodeVO.model_validate(node, from_attributes=True)


@router.get("/trees")
async def trees(request: Request) -> dict:
    return Results.success([_vo(node) for node in await _service(request).list_tree()]).model_dump(
        by_alias=True
    )


@router.post("")
async def create(
    body: IntentNodeWrite, request: Request, user: Annotated[LoginUser, Depends(require_admin)]
) -> dict:
    try:
        node_id = await _service(request).create(body.model_dump(), user.user_id)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc
    return Results.success(str(node_id)).model_dump(by_alias=True)


@router.post("/batch/enable")
async def batch_enable(body: IntentNodeBatch, request: Request) -> dict:
    try:
        await _service(request).batch_enable(body.ids, True)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc
    return Results.success().model_dump(by_alias=True)


@router.post("/batch/disable")
async def batch_disable(body: IntentNodeBatch, request: Request) -> dict:
    try:
        await _service(request).batch_enable(body.ids, False)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc
    return Results.success().model_dump(by_alias=True)


@router.post("/batch/delete")
async def batch_delete(body: IntentNodeBatch, request: Request) -> dict:
    try:
        await _service(request).batch_delete(body.ids)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc
    return Results.success().model_dump(by_alias=True)


@router.put("/{node_id}")
async def update(
    node_id: int,
    body: IntentNodeWrite,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    try:
        await _service(request).update(node_id, body.model_dump(), user.user_id)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc
    return Results.success().model_dump(by_alias=True)


@router.delete("/{node_id}")
async def delete(node_id: int, request: Request) -> dict:
    try:
        await _service(request).delete(node_id)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc
    return Results.success().model_dump(by_alias=True)
