"""查询词映射管理 REST 接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.framework.exceptions import ClientException
from app.framework.result import Results
from app.rag.rewrite.models import QueryTermMapping
from app.rag.rewrite.schemas import MappingPage, QueryTermMappingVO, QueryTermMappingWrite
from app.rag.rewrite.term_mapping import QueryTermMappingService
from app.system.auth.deps import require_user
from app.system.auth.models import LoginUser

router = APIRouter(prefix="/mappings", tags=["rewrite"], dependencies=[Depends(require_user)])


def _service(request: Request) -> QueryTermMappingService:
    return request.app.state.query_term_mapping_service


def _vo(mapping: QueryTermMapping) -> QueryTermMappingVO:
    return QueryTermMappingVO.model_validate(mapping)


@router.get("")
async def list_mappings(
    request: Request, current: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), keyword: str | None = None
) -> dict:
    records, total = await _service(request).list_mappings(current, size, keyword)
    page = MappingPage(records=[_vo(item) for item in records], total=total, current=current, size=size)
    return Results.success(page).model_dump(by_alias=True)


@router.get("/{mapping_id}")
async def get_mapping(mapping_id: int, request: Request) -> dict:
    try:
        return Results.success(_vo(await _service(request).get_mapping(mapping_id))).model_dump(by_alias=True)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc


@router.post("")
async def create_mapping(
    body: QueryTermMappingWrite, request: Request, user: Annotated[LoginUser, Depends(require_user)]
) -> dict:
    try:
        mapping_id = await _service(request).create_mapping(QueryTermMapping(**body.model_dump()), user.user_id)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc
    return Results.success(str(mapping_id)).model_dump(by_alias=True)


@router.put("/{mapping_id}")
async def update_mapping(
    mapping_id: int, body: QueryTermMappingWrite, request: Request, user: Annotated[LoginUser, Depends(require_user)]
) -> dict:
    try:
        await _service(request).update_mapping(mapping_id, QueryTermMapping(**body.model_dump()), user.user_id)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc
    return Results.success().model_dump(by_alias=True)


@router.delete("/{mapping_id}")
async def delete_mapping(mapping_id: int, request: Request) -> dict:
    try:
        await _service(request).delete_mapping(mapping_id)
    except ValueError as exc:
        raise ClientException(str(exc)) from exc
    return Results.success().model_dump(by_alias=True)
