"""F3 会话管理 REST 契约与序列化测试。"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.framework.exceptions import ClientException
from app.framework.result import ErrorCode
from app.main import app
from app.rag.conversation import ConversationService
from app.rag.router import conversation_router
from app.system.auth.deps import require_user
from app.system.auth.models import LoginUser


class FakeConversationService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def list_conversations(self, user_id: int) -> list[dict]:
        self.calls.append(("list", user_id))
        return [
            {
                "conversationId": "01999111-1111-7111-8111-111111111111",
                "title": "产品接入说明",
                "lastTime": 1_788_320_400_000,
            }
        ]

    async def list_messages(self, conversation_id: str, user_id: int) -> list[dict]:
        self.calls.append(("messages", conversation_id, user_id))
        return [
            {
                "id": "01999222-2222-7222-8222-222222222222",
                "conversationId": conversation_id,
                "role": "user",
                "content": "如何接入？",
                "thinkingContent": None,
                "thinkingDuration": None,
                "vote": None,
                "sources": None,
                "recommendedQuestions": None,
                "messageStatus": "NORMAL",
                "createTime": 1_788_320_400_000,
            }
        ]

    async def rename(self, conversation_id: str, user_id: int, title: str) -> None:
        self.calls.append(("rename", conversation_id, user_id, title))

    async def delete(self, conversation_id: str, user_id: int) -> None:
        self.calls.append(("delete", conversation_id, user_id))


class FakeFeedbackService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def submit(self, message_id, user_id, vote, reason=None, comment=None):
        self.calls.append(("submit", message_id, user_id, vote, reason, comment))

    async def remove(self, message_id, user_id):
        self.calls.append(("remove", message_id, user_id))


class FakeRecommendService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def generate(self, message_id, user_id):
        from app.framework.sse import (
            RecommendedQuestionsPayload,
            RecommendedQuestionStatus,
        )

        self.calls.append((message_id, user_id))
        return RecommendedQuestionsPayload(
            status=RecommendedQuestionStatus.SUCCESS,
            questions=["下一步如何配置？"],
        )


async def test_conversation_routes_preserve_contract_and_current_user(client: AsyncClient) -> None:
    service = FakeConversationService()
    conversation_id = "01999111-1111-7111-8111-111111111111"

    async def current_user() -> LoginUser:
        return LoginUser(userId=42, username="reader", role="USER")

    original_service = app.state.conversation_service
    app.state.conversation_service = service
    app.dependency_overrides[require_user] = current_user
    try:
        listed = await client.get("/conversations")
        messages = await client.get(f"/conversations/{conversation_id}/messages")
        renamed = await client.put(
            f"/conversations/{conversation_id}", json={"title": "新的会话标题"}
        )
        deleted = await client.delete(f"/conversations/{conversation_id}")
    finally:
        app.state.conversation_service = original_service
        app.dependency_overrides.pop(require_user, None)

    assert listed.json()["data"] == [
        {
            "conversationId": conversation_id,
            "title": "产品接入说明",
            "lastTime": 1_788_320_400_000,
        }
    ]
    assert messages.json()["data"][0]["content"] == "如何接入？"
    assert renamed.json()["code"] == str(ErrorCode.SUCCESS)
    assert deleted.json()["code"] == str(ErrorCode.SUCCESS)
    assert service.calls == [
        ("list", 42),
        ("messages", conversation_id, 42),
        ("rename", conversation_id, 42, "新的会话标题"),
        ("delete", conversation_id, 42),
    ]


async def test_feedback_and_recommendation_routes_use_current_user(client: AsyncClient) -> None:
    feedback = FakeFeedbackService()
    recommend = FakeRecommendService()

    async def current_user() -> LoginUser:
        return LoginUser(userId=42, username="reader", role="USER")

    original_feedback = app.state.message_feedback_service
    original_recommend = app.state.recommended_question_service
    app.state.message_feedback_service = feedback
    app.state.recommended_question_service = recommend
    app.dependency_overrides[require_user] = current_user
    try:
        submitted = await client.post(
            "/conversations/messages/message-1/feedback",
            json={"vote": -1, "reason": "不准确", "comment": "缺少来源"},
        )
        removed = await client.delete("/conversations/messages/message-1/feedback")
        generated = await client.post(
            "/conversations/messages/message-1/recommended-questions"
        )
    finally:
        app.state.message_feedback_service = original_feedback
        app.state.recommended_question_service = original_recommend
        app.dependency_overrides.pop(require_user, None)

    assert submitted.json()["code"] == "0"
    assert removed.json()["code"] == "0"
    assert generated.json()["data"] == {
        "status": "SUCCESS",
        "questions": ["下一步如何配置？"],
    }
    assert feedback.calls == [
        ("submit", "message-1", 42, -1, "不准确", "缺少来源"),
        ("remove", "message-1", 42),
    ]
    assert recommend.calls == [("message-1", 42)]


def test_all_conversation_routes_require_authentication() -> None:
    for route in conversation_router.routes:
        assert isinstance(route, APIRoute)
        calls = {dependency.call for dependency in route.dependant.dependencies}
        assert require_user in calls


async def test_conversation_validation_happens_before_database_access() -> None:
    service = ConversationService(cast(AsyncEngine, None), title_max_length=5)
    valid_id = "01999111-1111-7111-8111-111111111111"

    with pytest.raises(ClientException, match="会话标题不能为空"):
        await service.rename(valid_id, 1, "   ")
    with pytest.raises(ClientException, match="会话标题不能超过 5 个字符"):
        await service.rename(valid_id, 1, "超过五个字符")
    with pytest.raises(ClientException, match="会话 ID 无效"):
        await service.rename("invalid", 1, "标题")


def test_conversation_and_message_serialization_use_epoch_milliseconds() -> None:
    conversation_id = uuid.UUID("01999111-1111-7111-8111-111111111111")
    message_id = uuid.UUID("01999222-2222-7222-8222-222222222222")
    created = datetime(2026, 9, 3, 7, 30, tzinfo=UTC)
    conversation = SimpleNamespace(
        conversation_id=conversation_id,
        title=None,
        last_time=created,
        update_time=created,
        create_time=created,
    )
    message = SimpleNamespace(
        id=message_id,
        conversation_id=conversation_id,
        role="assistant",
        content="请查看来源 [1](#cite-1)。",
        thinking_content="检索产品文档",
        thinking_duration=2,
        sources=[{"index": 1, "docId": "7", "docName": "产品指南.md"}],
        recommended_questions=["如何配置？"],
        message_status="NORMAL",
        create_time=created,
    )

    listed = ConversationService._conversation(conversation)
    serialized = ConversationService._message(message, 1)

    assert listed == {
        "conversationId": str(conversation_id),
        "title": "新对话",
        "lastTime": 1_788_420_600_000,
    }
    assert serialized["content"] == "请查看来源 [1](#cite-1)。"
    assert serialized["vote"] == 1
    assert serialized["createTime"] == 1_788_420_600_000
