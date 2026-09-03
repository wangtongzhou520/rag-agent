"""SSE payload、编码和发送器状态机测试。"""

import json

from app.framework.sse import (
    CompletionPayload,
    GuidanceOption,
    GuidancePayload,
    MessageDeltaType,
    MessageStatus,
    MetaPayload,
    SourceRef,
    SseEventType,
    SseSender,
    encode_sse,
    split_message_chunk,
)


def test_encode_sse_uses_camel_case_and_omits_none() -> None:
    payload = CompletionPayload(
        message_id=None,
        title="新对话",
        sources=[
            SourceRef(
                index=1,
                doc_id="doc-1",
                doc_name="手册.pdf",
                source_type="KB",
            )
        ],
        message_status=MessageStatus.NORMAL,
    )

    frame = encode_sse(SseEventType.FINISH, payload)

    assert frame.startswith("event: finish\ndata: ")
    data = json.loads(frame.split("data: ", maxsplit=1)[1])
    assert data == {
        "title": "新对话",
        "sources": [
            {
                "index": 1,
                "docId": "doc-1",
                "docName": "手册.pdf",
                "sourceType": "KB",
            }
        ],
        "messageStatus": "NORMAL",
    }


def test_guidance_event_has_structured_options_and_scoped_queries() -> None:
    payload = GuidancePayload(
        prompt="请选择知识范围",
        original_question="怎么配置",
        options=[
            GuidanceOption(
                id=1,
                intent_code="product.standard",
                label="产品 > 标准版",
                query="怎么配置（知识范围：产品 > 标准版）",
            )
        ],
        all_query=None,
    )

    frame = encode_sse(SseEventType.GUIDANCE, payload)
    data = json.loads(frame.split("data: ", maxsplit=1)[1])

    assert frame.startswith("event: guidance")
    assert data == {
        "prompt": "请选择知识范围",
        "originalQuestion": "怎么配置",
        "options": [
            {
                "id": 1,
                "intentCode": "product.standard",
                "label": "产品 > 标准版",
                "query": "怎么配置（知识范围：产品 > 标准版）",
            }
        ],
    }


def test_split_message_chunk_is_code_point_based_and_drops_blank() -> None:
    assert split_message_chunk("A😀中文Z", 2) == ["A😀", "中文", "Z"]
    assert split_message_chunk("abc", 0) == ["a", "b", "c"]
    assert split_message_chunk(" \n ", 5) == []


async def test_sender_done_is_terminal_and_idempotent() -> None:
    sender = SseSender()

    assert await sender.send(
        SseEventType.META,
        MetaPayload(conversation_id="conversation", task_id="task"),
    )
    assert await sender.send_message(MessageDeltaType.RESPONSE, "abcdef", 2) == 3
    assert await sender.done()
    assert not await sender.done()
    assert not await sender.send(
        SseEventType.META,
        MetaPayload(conversation_id="late", task_id="late"),
    )

    frames = [frame async for frame in sender.stream()]
    assert [frame.splitlines()[0] for frame in frames] == [
        "event: meta",
        "event: message",
        "event: message",
        "event: message",
        "event: done",
    ]
    assert frames[-1] == "event: done\ndata: [DONE]\n\n"


async def test_sender_fail_closes_without_protocol_terminal_frame() -> None:
    sender = SseSender()
    error = RuntimeError("upstream failed")

    assert await sender.fail(error)
    assert sender.closed
    assert sender.error is error
    assert [frame async for frame in sender.stream()] == []
