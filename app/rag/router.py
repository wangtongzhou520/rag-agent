"""RAG 对外路由；/rag/v3/chat 为 SSE 协议薄壳，编排委托 RAGChatService。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.framework.exceptions import ClientException
from app.framework.ids import new_uuid7
from app.framework.result import Results
from app.framework.sse import SseSender
from app.rag.conversation import ConversationService
from app.rag.schemas import ConversationTitleUpdate
from app.rag.service import RAGChatService
from app.system.auth.deps import require_user
from app.system.auth.models import LoginUser

router = APIRouter(prefix="/rag/v3", tags=["rag"])
conversation_router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_user)],
)


def _conversation_service(request: Request) -> ConversationService:
    return request.app.state.conversation_service


@conversation_router.get("")
async def list_conversations(
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
) -> dict:
    data = await _conversation_service(request).list_conversations(user.user_id)
    return Results.success(data).model_dump(by_alias=True)


@conversation_router.put("/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: ConversationTitleUpdate,
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
) -> dict:
    await _conversation_service(request).rename(conversation_id, user.user_id, body.title)
    return Results.success().model_dump(by_alias=True)


@conversation_router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
) -> dict:
    await _conversation_service(request).delete(conversation_id, user.user_id)
    return Results.success().model_dump(by_alias=True)


@conversation_router.get("/{conversation_id}/messages")
async def list_conversation_messages(
    conversation_id: str,
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
) -> dict:
    data = await _conversation_service(request).list_messages(conversation_id, user.user_id)
    return Results.success(data).model_dump(by_alias=True)

@router.get("/chat", response_class=StreamingResponse)
async def stream_chat(
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
    question: Annotated[str, Query(min_length=1, max_length=4000)],
    conversation_id: Annotated[str | None, Query(alias="conversationId")] = None,
    deep_thinking: Annotated[bool, Query(alias="deepThinking")] = False,
) -> StreamingResponse:
    """流式问答入口：构造 SseSender 并委托 RAGChatService，协议契约不变。"""
    normalized_question = question.strip()
    if not normalized_question:
        raise ClientException("问题不能为空")

    sender = SseSender()
    service: RAGChatService = request.app.state.rag_chat_service
    task_id = new_uuid7()
    producer = asyncio.create_task(
        service.stream_chat(
            question=normalized_question,
            conversation_id=conversation_id,
            deep_thinking=deep_thinking,
            user_id=user.user_id,
            sender=sender,
        ),
        name=f"stream-chat:{task_id}",
    )

    async def body() -> AsyncIterator[str]:
        try:
            async for frame in sender.stream():
                yield frame
        finally:
            if not producer.done():
                producer.cancel()
            with suppress(asyncio.CancelledError):
                await producer

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
