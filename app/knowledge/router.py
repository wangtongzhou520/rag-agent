"""知识库、文档和 chunk 的 M2 REST 接口。"""

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.framework.exceptions import ClientException
from app.framework.result import Results
from app.knowledge.schemas import (
    BatchEnable,
    ChunkUpdate,
    DocumentUpdate,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
)
from app.knowledge.service import KnowledgeService
from app.system.auth.deps import require_admin, require_user
from app.system.auth.models import LoginUser

router = APIRouter(
    prefix="/knowledge-base",
    tags=["knowledge"],
    dependencies=[Depends(require_user)],
)

ADMIN_ONLY = [Depends(require_admin)]


def _service(request: Request) -> KnowledgeService:
    return request.app.state.knowledge_service


@router.post("", dependencies=ADMIN_ONLY)
async def create_base(
    body: KnowledgeBaseCreate,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    return Results.success(await _service(request).create_base(body, user.user_id)).model_dump(
        by_alias=True
    )


@router.get("", dependencies=ADMIN_ONLY)
async def list_bases(
    request: Request,
    current: int = 1,
    size: int = 20,
    name: str | None = None,
) -> dict:
    data = await _service(request).list_bases(current, size, name)
    return Results.success(data).model_dump(by_alias=True)


@router.get("/docs/ingestion-spec-schema", dependencies=ADMIN_ONLY)
async def ingestion_spec_schema() -> dict:
    data = {
        "version": 2,
        "parseProfiles": ["fast", "fidelity"],
        "budget": {
            "maxChars": {"default": 1024, "min": 128, "max": 50000, "whole": -1},
            "overlapChars": {"default": 128, "min": 0},
            "rowsPerChunk": {"default": 50, "min": 1, "max": 1000},
            "toleranceFactor": {"default": 3},
        },
    }
    return Results.success(data).model_dump(by_alias=True)


@router.get("/docs/search", dependencies=ADMIN_ONLY)
async def search_documents(request: Request, keyword: str | None = None, limit: int = 8) -> dict:
    data = await _service(request).search_documents(keyword, limit)
    return Results.success(data).model_dump(by_alias=True)


@router.get("/docs/{doc_id}", dependencies=ADMIN_ONLY)
async def get_document(doc_id: int, request: Request) -> dict:
    return Results.success(await _service(request).get_document(doc_id)).model_dump(by_alias=True)


@router.put("/docs/{doc_id}", dependencies=ADMIN_ONLY)
async def update_document(doc_id: int, body: DocumentUpdate, request: Request) -> dict:
    await _service(request).update_document(
        doc_id,
        doc_name=body.doc_name,
        ingestion_spec=body.ingestion_spec,
        source_location=body.source_location,
    )
    return Results.success().model_dump(by_alias=True)


@router.get("/docs/{doc_id}/preview")
async def preview_document(doc_id: int, request: Request) -> dict:
    return Results.success(await _service(request).preview_document(doc_id)).model_dump(
        by_alias=True
    )


@router.get("/docs/{doc_id}/file")
async def document_file(doc_id: int, request: Request) -> FileResponse:
    path, filename = await _service(request).document_file(doc_id)
    if not path.is_file():
        raise ClientException("文档文件不存在")
    return FileResponse(path, filename=filename, content_disposition_type="inline")


@router.post("/{kb_id}/docs/upload", dependencies=ADMIN_ONLY)
async def upload_document(
    kb_id: int,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
    file: Annotated[UploadFile | None, File()] = None,
    source_type: Annotated[str, Form(alias="sourceType")] = "file",
    source_location: Annotated[str | None, Form(alias="sourceLocation")] = None,
    ingestion_spec: Annotated[str | None, Form(alias="ingestionSpec")] = None,
) -> dict:
    try:
        parsed_spec = json.loads(ingestion_spec) if ingestion_spec else None
    except json.JSONDecodeError as exc:
        raise ClientException("ingestionSpec 不是合法 JSON") from exc
    data = await file.read() if file is not None else None
    document = await _service(request).create_document(
        kb_id,
        user.user_id,
        filename=file.filename if file else None,
        data=data,
        source_type=source_type,
        source_location=source_location,
        ingestion_spec=parsed_spec,
    )
    return Results.success(document).model_dump(by_alias=True)


@router.post("/docs/{doc_id}/chunk", dependencies=ADMIN_ONLY)
async def trigger_chunk(
    doc_id: int,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    await _service(request).trigger_chunk(doc_id, user.user_id)
    return Results.success().model_dump(by_alias=True)


@router.get("/{kb_id}/docs", dependencies=ADMIN_ONLY)
async def list_documents(
    kb_id: int,
    request: Request,
    current: int = 1,
    size: int = 20,
    status: str | None = None,
    keyword: str | None = None,
) -> dict:
    data = await _service(request).list_documents(kb_id, current, size, status, keyword)
    return Results.success(data).model_dump(by_alias=True)


@router.patch("/docs/{doc_id}/enable", dependencies=ADMIN_ONLY)
async def enable_document(doc_id: int, request: Request, value: Annotated[bool, Query()]) -> dict:
    await _service(request).set_document_enabled(doc_id, value)
    return Results.success().model_dump(by_alias=True)


@router.delete("/docs/{doc_id}", dependencies=ADMIN_ONLY)
async def delete_document(doc_id: int, request: Request) -> dict:
    await _service(request).delete_document(doc_id)
    return Results.success().model_dump(by_alias=True)


@router.get("/docs/{doc_id}/chunks", dependencies=ADMIN_ONLY)
async def list_chunks(
    doc_id: int,
    request: Request,
    current: int = 1,
    size: int = 20,
    enabled: bool | None = None,
) -> dict:
    data = await _service(request).list_chunks(doc_id, current, size, enabled)
    return Results.success(data).model_dump(by_alias=True)


@router.patch("/docs/{doc_id}/chunks/{chunk_id}/enable", dependencies=ADMIN_ONLY)
async def enable_chunk(
    doc_id: int,
    chunk_id: uuid.UUID,
    request: Request,
    value: Annotated[bool, Query()],
) -> dict:
    await _service(request).set_chunk_enabled(chunk_id, value)
    return Results.success().model_dump(by_alias=True)


@router.patch("/docs/{doc_id}/chunks/batch-enable", dependencies=ADMIN_ONLY)
async def batch_enable_chunks(
    doc_id: int,
    body: BatchEnable,
    request: Request,
    value: Annotated[bool, Query()],
) -> dict:
    await _service(request).batch_set_chunks_enabled(body.chunk_ids, value)
    return Results.success().model_dump(by_alias=True)


@router.put("/docs/{doc_id}/chunks/{chunk_id}", dependencies=ADMIN_ONLY)
async def update_chunk(
    doc_id: int,
    chunk_id: uuid.UUID,
    body: ChunkUpdate,
    request: Request,
) -> dict:
    await _service(request).update_chunk(chunk_id, body.content)
    return Results.success().model_dump(by_alias=True)


@router.delete("/docs/{doc_id}/chunks/{chunk_id}", dependencies=ADMIN_ONLY)
async def delete_chunk(doc_id: int, chunk_id: uuid.UUID, request: Request) -> dict:
    await _service(request).delete_chunk(chunk_id)
    return Results.success().model_dump(by_alias=True)


@router.get("/{kb_id}", dependencies=ADMIN_ONLY)
async def get_base(kb_id: int, request: Request) -> dict:
    return Results.success(await _service(request).get_base(kb_id)).model_dump(by_alias=True)


@router.put("/{kb_id}", dependencies=ADMIN_ONLY)
async def update_base(
    kb_id: int,
    body: KnowledgeBaseUpdate,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    await _service(request).update_base(kb_id, body, user.user_id)
    return Results.success().model_dump(by_alias=True)


@router.delete("/{kb_id}", dependencies=ADMIN_ONLY)
async def delete_base(
    kb_id: int,
    request: Request,
    user: Annotated[LoginUser, Depends(require_admin)],
) -> dict:
    await _service(request).delete_base(kb_id, user.user_id)
    return Results.success().model_dump(by_alias=True)
