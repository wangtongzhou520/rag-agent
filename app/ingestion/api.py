"""入库 Pipeline、同步调试任务与后台队列管理接口。"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from app.framework.exceptions import ClientException
from app.framework.result import Results
from app.ingestion.schemas import DocumentSource, PipelineCreate, PipelineUpdate, TaskCreate
from app.ingestion.service import IngestionService
from app.system.audit.decorator import audit_log
from app.system.auth.deps import require_admin
from app.system.auth.models import LoginUser

router = APIRouter(
    prefix="/ingestion", tags=["ingestion"], dependencies=[Depends(require_admin)]
)


def _service(request: Request) -> IngestionService:
    return request.app.state.ingestion_service


@router.post("/pipelines")
@audit_log(
    biz_type="INGESTION_PIPELINE",
    op="CREATE",
    success_desc=lambda values, _: f"创建 Pipeline：{values['body'].name.strip()}",
    fail_desc="创建 Pipeline 失败",
)
async def create_pipeline(
    body: PipelineCreate,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    return Results.success(
        await _service(request).create_pipeline(body, user.user_id)
    ).model_dump(by_alias=True)


@router.put("/pipelines/{pipeline_id}")
@audit_log(
    biz_type="INGESTION_PIPELINE",
    op="UPDATE",
    success_desc="更新 Pipeline",
    fail_desc="更新 Pipeline 失败",
)
async def update_pipeline(
    pipeline_id: int,
    body: PipelineUpdate,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    await _service(request).update_pipeline(pipeline_id, body, user.user_id)
    return Results.success().model_dump(by_alias=True)


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: int, request: Request) -> dict:
    return Results.success(
        await _service(request).get_pipeline(pipeline_id)
    ).model_dump(by_alias=True)


@router.get("/pipelines")
async def page_pipelines(
    request: Request,
    page_no: int = Query(1, alias="pageNo", ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    keyword: str | None = None,
) -> dict:
    return Results.success(
        await _service(request).page_pipelines(page_no, page_size, keyword)
    ).model_dump(by_alias=True)


@router.delete("/pipelines/{pipeline_id}")
@audit_log(
    biz_type="INGESTION_PIPELINE",
    op="DELETE",
    success_desc="删除 Pipeline",
    fail_desc="删除 Pipeline 失败",
)
async def delete_pipeline(pipeline_id: int, request: Request) -> dict:
    await _service(request).delete_pipeline(pipeline_id)
    return Results.success().model_dump(by_alias=True)


@router.post("/tasks")
@audit_log(
    biz_type="INGESTION_TASK",
    op="RUN",
    success_desc="执行 Pipeline 调试任务",
    fail_desc="执行 Pipeline 调试任务失败",
)
async def run_task(
    body: TaskCreate,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    return Results.success(
        await _service(request).run_task(body, user.user_id)
    ).model_dump(by_alias=True)


@router.post("/tasks/upload")
@audit_log(
    biz_type="INGESTION_TASK",
    op="RUN",
    success_desc="执行上传文件 Pipeline 调试任务",
    fail_desc="执行上传文件 Pipeline 调试任务失败",
)
async def run_upload_task(
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
    pipeline_id: Annotated[int, Form(alias="pipelineId")],
    file: Annotated[UploadFile, File()],
    vector_space_id: Annotated[str | None, Form(alias="vectorSpaceId")] = None,
    metadata: Annotated[str | None, Form()] = None,
) -> dict:
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError as exc:
        raise ClientException("metadata 不是合法 JSON") from exc
    if not isinstance(parsed_metadata, dict):
        raise ClientException("metadata 必须是 JSON 对象")
    data = await file.read()
    body = TaskCreate(
        pipelineId=pipeline_id,
        source=DocumentSource(type="file", fileName=file.filename),
        metadata=parsed_metadata,
        vectorSpaceId=vector_space_id,
    )
    return Results.success(
        await _service(request).run_task(body, user.user_id, raw_bytes=data)
    ).model_dump(by_alias=True)


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, request: Request) -> dict:
    return Results.success(await _service(request).get_task(task_id)).model_dump(
        by_alias=True
    )


@router.get("/tasks/{task_id}/nodes")
async def task_nodes(task_id: int, request: Request) -> dict:
    return Results.success(await _service(request).task_nodes(task_id)).model_dump(
        by_alias=True
    )


@router.get("/tasks")
async def page_tasks(
    request: Request,
    page_no: int = Query(1, alias="pageNo", ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    status: str | None = None,
) -> dict:
    return Results.success(
        await _service(request).page_tasks(page_no, page_size, status)
    ).model_dump(by_alias=True)


@router.get("/async-tasks")
async def page_async_tasks(
    request: Request,
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    task_type: str | None = Query(None, alias="taskType"),
) -> dict:
    return Results.success(
        await _service(request).page_async_tasks(current, size, status, task_type)
    ).model_dump(by_alias=True)
