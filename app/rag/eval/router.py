"""按配置启用的纯检索评测入口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.framework.result import Results
from app.rag.eval.reports import EvalReportService
from app.rag.eval.schemas import EvalReportCreate
from app.rag.eval.service import EvalService
from app.system.auth.deps import require_admin
from app.system.auth.models import LoginUser

router = APIRouter(
    prefix="/rag", tags=["eval"], dependencies=[Depends(require_admin)]
)


def _service(request: Request) -> EvalService:
    return request.app.state.eval_service


def _reports(request: Request) -> EvalReportService:
    return request.app.state.eval_report_service


@router.get("/eval")
async def evaluate(
    request: Request,
    question: str = Query(min_length=1, max_length=1000),
    collection: Annotated[list[str] | None, Query()] = None,
    include_answer: Annotated[bool, Query(alias="includeAnswer")] = False,
) -> dict:
    collections = tuple(
        dict.fromkeys(value.strip() for value in collection or () if value.strip())
    )
    result = await _service(request).evaluate(
        question,
        collections=collections,
        include_answer=include_answer,
    )
    return Results.success(result).model_dump(by_alias=True)


@router.post("/eval/reports")
async def create_report(
    command: EvalReportCreate,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    result = await _reports(request).create(command, user.user_id)
    return Results.success(result).model_dump(by_alias=True)


@router.get("/eval/reports")
async def page_reports(
    request: Request,
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> dict:
    result = await _reports(request).page(current, size)
    return Results.success(result).model_dump(by_alias=True)


@router.get("/eval/reports/{report_id}")
async def report_detail(report_id: str, request: Request) -> dict:
    result = await _reports(request).detail(report_id)
    return Results.success(result).model_dump(by_alias=True)
