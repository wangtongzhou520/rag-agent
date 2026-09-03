"""流式问答协议入口测试：SSE 基础事件契约（检索恒空走短路文案）。

本地无 PG：记忆层读写失败按 docs/01 §13 降级，不影响事件序列。
"""

import json
from typing import Any
from uuid import UUID

from httpx import AsyncClient

from app.main import app
from app.rag.pipeline.stream_chat import EMPTY_RETRIEVAL_TEXT
from app.system.auth.deps import require_user
from app.system.auth.models import LoginUser


def parse_events(body: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        event = lines[0].removeprefix("event: ")
        raw_data = lines[1].removeprefix("data: ")
        data = raw_data if raw_data == "[DONE]" else json.loads(raw_data)
        events.append((event, data))
    return events


async def test_chat_stream_emits_meta_messages_finish_and_done(client: AsyncClient) -> None:
    response = await client.get(
        "/rag/v3/chat",
        params={"question": "测试abc"},
        headers={"X-Request-ID": "stream-request"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-request-id"] == "stream-request"

    events = parse_events(response.text)
    names = [event for event, _ in events]
    assert names[0] == "meta"
    assert names[-2:] == ["finish", "done"]
    assert set(names[1:-2]) == {"message"}

    meta = events[0][1]
    assert UUID(meta["conversationId"]).version == 7
    assert UUID(meta["taskId"]).version == 7

    answer = "".join(data["delta"] for event, data in events if event == "message")
    assert answer == EMPTY_RETRIEVAL_TEXT
    assert all(data["type"] == "response" for event, data in events if event == "message")
    # 无 PG 时 assistant 落库失败，messageId 为空不序列化
    assert events[-2][1] == {"title": "新对话", "messageStatus": "NORMAL"}
    assert events[-1][1] == "[DONE]"


async def test_existing_conversation_omits_title(client: AsyncClient) -> None:
    response = await client.get(
        "/rag/v3/chat",
        params={"question": "你好", "conversationId": "existing-conversation"},
    )

    events = parse_events(response.text)
    meta = events[0][1]
    assert meta["conversationId"] == "existing-conversation"
    assert events[-2][1] == {"messageStatus": "NORMAL"}


async def test_blank_question_returns_result_error(client: AsyncClient) -> None:
    response = await client.get("/rag/v3/chat", params={"question": "   "})

    assert response.status_code == 200
    assert response.json() == {
        "code": "40000",
        "message": "问题不能为空",
        "data": None,
        "requestId": response.headers["X-Request-ID"],
    }


async def test_stop_route_uses_current_user_and_is_idempotent(client: AsyncClient) -> None:
    class RecordingTaskManager:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        async def cancel(self, task_id: str, user_id: int) -> bool:
            self.calls.append((task_id, user_id))
            return False

    async def current_user() -> LoginUser:
        return LoginUser(userId=42, username="reader", role="USER")

    manager = RecordingTaskManager()
    original_manager = app.state.stream_task_manager
    app.state.stream_task_manager = manager
    app.dependency_overrides[require_user] = current_user
    try:
        response = await client.post("/rag/v3/stop", params={"taskId": "task-1"})
    finally:
        app.state.stream_task_manager = original_manager
        app.dependency_overrides.pop(require_user, None)

    assert response.json()["code"] == "0"
    assert manager.calls == [("task-1", 42)]
