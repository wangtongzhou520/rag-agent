"""RAG Trace 管理查询接口。"""

from fastapi import APIRouter, Depends, Query, Request

from app.framework.result import Results
from app.rag.trace.query import RagTraceQueryService
from app.system.auth.deps import require_admin

router = APIRouter(
    prefix="/rag/traces",
    tags=["trace"],
    dependencies=[Depends(require_admin)],
)


def _service(request: Request) -> RagTraceQueryService:
    return request.app.state.rag_trace_query_service


@router.get("/runs")
async def page_runs(
    request: Request,
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    trace_id: str | None = Query(None, alias="traceId"),
    conversation_id: str | None = Query(None, alias="conversationId"),
    task_id: str | None = Query(None, alias="taskId"),
    status: str | None = None,
) -> dict:
    data = await _service(request).page_runs(
        current,
        size,
        trace_id=trace_id,
        conversation_id=conversation_id,
        task_id=task_id,
        status=status,
    )
    return Results.success(data).model_dump(by_alias=True)


@router.get("/runs/{trace_id}")
async def detail(trace_id: str, request: Request) -> dict:
    return Results.success(await _service(request).detail(trace_id)).model_dump(by_alias=True)


@router.get("/runs/{trace_id}/nodes")
async def nodes(trace_id: str, request: Request) -> dict:
    return Results.success(await _service(request).nodes(trace_id)).model_dump(by_alias=True)
