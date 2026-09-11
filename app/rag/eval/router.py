"""按配置启用的纯检索评测入口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.framework.result import Results
from app.rag.eval.service import EvalService
from app.system.auth.deps import require_admin

router = APIRouter(
    prefix="/rag", tags=["eval"], dependencies=[Depends(require_admin)]
)


def _service(request: Request) -> EvalService:
    return request.app.state.eval_service


@router.get("/eval")
async def evaluate(
    request: Request,
    question: str = Query(min_length=1, max_length=1000),
    collection: Annotated[list[str] | None, Query()] = None,
) -> dict:
    collections = tuple(
        dict.fromkeys(value.strip() for value in collection or () if value.strip())
    )
    result = await _service(request).evaluate(question, collections=collections)
    return Results.success(result).model_dump(by_alias=True)
