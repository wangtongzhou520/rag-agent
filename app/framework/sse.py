"""SSE 七事件协议、payload 模型与单写入者发送器。"""

import asyncio
import json
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class SsePayload(BaseModel):
    """SSE payload 基类：camelCase 输出并省略空字段。"""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class SseEventType(StrEnum):
    META = "meta"
    MESSAGE = "message"
    FINISH = "finish"
    CANCEL = "cancel"
    REJECT = "reject"
    GUIDANCE = "guidance"
    DONE = "done"


class MessageDeltaType(StrEnum):
    THINK = "think"
    RESPONSE = "response"


class MessageStatus(StrEnum):
    NORMAL = "NORMAL"
    INTERRUPTED = "INTERRUPTED"
    REJECTED = "REJECTED"


class RecommendedQuestionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    FAILED = "FAILED"


class MetaPayload(SsePayload):
    conversation_id: str
    task_id: str


class MessageDelta(SsePayload):
    type: MessageDeltaType
    delta: str


class SourceRef(SsePayload):
    index: int
    doc_id: str
    doc_name: str
    source_type: str
    file_type: str | None = None
    url: str | None = None
    excerpt: str | None = None


class CompletionPayload(SsePayload):
    message_id: str | None = None
    title: str | None = None
    sources: list[SourceRef] | None = None
    message_status: MessageStatus


class RecommendedQuestionsPayload(SsePayload):
    status: RecommendedQuestionStatus
    questions: list[str] = Field(default_factory=list)


class GuidanceOption(SsePayload):
    id: int
    intent_code: str
    label: str
    query: str


class GuidancePayload(SsePayload):
    prompt: str
    original_question: str
    options: list[GuidanceOption]
    all_query: str | None = None


def encode_sse(event: SseEventType, payload: SsePayload | dict[str, Any] | str) -> str:
    """编码单个 SSE 帧；done 的 data 固定为非 JSON 字面量 ``[DONE]``。"""
    if event is SseEventType.DONE:
        data = "[DONE]"
    elif isinstance(payload, BaseModel):
        data = payload.model_dump_json(by_alias=True, exclude_none=True)
    elif isinstance(payload, str):
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.value}\ndata: {data}\n\n"


def split_message_chunk(text: str, chunk_size: int) -> list[str]:
    """按 Unicode code point 切分单个上游 chunk，不跨调用缓存残余。"""
    if not text or not text.strip():
        return []
    size = max(1, chunk_size)
    return [text[start : start + size] for start in range(0, len(text), size)]


class SseSender:
    """并发安全的 SSE 队列发送器。

    所有状态迁移都在一把 asyncio 锁内完成。终态后发送静默返回 ``False``；
    ``done`` 会原子写入终止帧并关闭流，``complete``/``fail`` 均幂等。
    """

    _END: ClassVar[object] = object()

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | object] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._closed = False
        self._error: BaseException | None = None

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def error(self) -> BaseException | None:
        return self._error

    async def send(
        self,
        event: SseEventType,
        payload: SsePayload | dict[str, Any] | str,
    ) -> bool:
        if event is SseEventType.DONE:
            return await self.done()
        async with self._lock:
            if self._closed:
                return False
            self._queue.put_nowait(encode_sse(event, payload))
            return True

    async def send_message(
        self,
        delta_type: MessageDeltaType,
        text: str,
        chunk_size: int,
        *,
        event: SseEventType = SseEventType.MESSAGE,
    ) -> int:
        """切分并发送一个上游 chunk，返回成功写入的帧数。"""
        sent = 0
        for chunk in split_message_chunk(text, chunk_size):
            if not await self.send(event, MessageDelta(type=delta_type, delta=chunk)):
                break
            sent += 1
        return sent

    async def done(self) -> bool:
        async with self._lock:
            if self._closed:
                return False
            self._queue.put_nowait(encode_sse(SseEventType.DONE, "[DONE]"))
            self._queue.put_nowait(self._END)
            self._closed = True
            return True

    async def complete(self) -> bool:
        """不追加事件地关闭流，供客户端断开或无协议终态的异常路径使用。"""
        async with self._lock:
            if self._closed:
                return False
            self._queue.put_nowait(self._END)
            self._closed = True
            return True

    async def fail(self, error: BaseException) -> bool:
        async with self._lock:
            if self._closed:
                return False
            self._error = error
            self._queue.put_nowait(self._END)
            self._closed = True
            return True

    async def stream(self) -> AsyncIterator[str]:
        while True:
            item = await self._queue.get()
            if item is self._END:
                break
            yield str(item)
