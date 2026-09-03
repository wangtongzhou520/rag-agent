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
from app.framework.stream_tasks import StreamTaskManager
from app.rag.conversation import ConversationService
from app.rag.feedback import MessageFeedbackService
from app.rag.recommend import RecommendedQuestionService
from app.rag.schemas import ConversationTitleUpdate, MessageFeedbackWrite
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


def _feedback_service(request: Request) -> MessageFeedbackService:
    return request.app.state.message_feedback_service


def _recommend_service(request: Request) -> RecommendedQuestionService:
    return request.app.state.recommended_question_service


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


@conversation_router.post("/messages/{message_id}/feedback")
async def submit_message_feedback(
    message_id: str,
    body: MessageFeedbackWrite,
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
) -> dict:
    await _feedback_service(request).submit(
        message_id,
        user.user_id,
        body.vote,
        body.reason,
        body.comment,
    )
    return Results.success().model_dump(by_alias=True)


@conversation_router.delete("/messages/{message_id}/feedback")
async def delete_message_feedback(
    message_id: str,
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
) -> dict:
    await _feedback_service(request).remove(message_id, user.user_id)
    return Results.success().model_dump(by_alias=True)


@conversation_router.post("/messages/{message_id}/recommended-questions")
async def generate_recommended_questions(
    message_id: str,
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
) -> dict:
    data = await _recommend_service(request).generate(message_id, user.user_id)
    return Results.success(data).model_dump(by_alias=True)


@router.post("/stop")
async def stop_stream_chat(
    request: Request,
    user: Annotated[LoginUser, Depends(require_user)],
    task_id: Annotated[str, Query(alias="taskId", min_length=1, max_length=128)],
) -> dict:
    """幂等停止当前用户的流任务；已结束或非本人任务不暴露额外信息。"""
    task_manager: StreamTaskManager = request.app.state.stream_task_manager
    await task_manager.cancel(task_id, user.user_id)
    return Results.success().model_dump(by_alias=True)


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
            task_id=task_id,
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
