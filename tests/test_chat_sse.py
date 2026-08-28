"""OpenAI 风格 SSE 逐行解析测试（docs/04 §6.4）。"""

from app.model_runtime.chat.sse import ParsedEvent, parse_line


def test_empty_and_data_only_lines_are_skipped() -> None:
    assert parse_line("") is None
    assert parse_line("   ") is None
    assert parse_line("data:") is None
    assert parse_line("data:   ") is None


def test_done_marker_is_case_insensitive() -> None:
    assert parse_line("data: [DONE]").completed
    assert parse_line("data: [done]").completed
    assert parse_line("[Done]").completed


def test_bad_lines_are_skipped_without_interrupting() -> None:
    assert parse_line("data: {not-json") is None
    assert parse_line("garbage") is None
    assert parse_line("data: [1, 2]") is None  # 非 dict 结构
    # 坏行之后后续行仍可正常解析
    event = parse_line('data: {"choices":[{"delta":{"content":"hi"},"finish_reason":null}]}')
    assert event == ParsedEvent(content="hi")


def test_content_prefers_delta_then_falls_back_to_message() -> None:
    delta = parse_line('data: {"choices":[{"delta":{"content":"答案"},"finish_reason":null}]}')
    assert delta.content == "答案"

    message = parse_line('data: {"choices":[{"message":{"content":"回落"},"finish_reason":null}]}')
    assert message.content == "回落"

    # delta 非 null 时不读 message
    both = parse_line(
        'data: {"choices":[{"delta":{"content":"d"},"message":{"content":"m"},'
        '"finish_reason":null}]}'
    )
    assert both.content == "d"

    # delta 为 null 才回落 message
    null_delta = parse_line(
        'data: {"choices":[{"delta":{"content":null},"message":{"content":"m"},'
        '"finish_reason":null}]}'
    )
    assert null_delta.content == "m"


def test_blank_content_is_not_an_event() -> None:
    event = parse_line('data: {"choices":[{"delta":{"content":"  "},"finish_reason":null}]}')
    assert event is not None
    assert event.content is None


def test_reasoning_requires_reasoning_enabled() -> None:
    line = 'data: {"choices":[{"delta":{"reasoning_content":"让我想"},"finish_reason":null}]}'
    enabled = parse_line(line, reasoning_enabled=True)
    assert enabled.reasoning == "让我想"
    disabled = parse_line(line, reasoning_enabled=False)
    assert disabled is not None
    assert disabled.reasoning is None
    assert disabled.content is None


def test_finish_reason_completes_the_event() -> None:
    event = parse_line('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}')
    assert event.completed

    null_reason = parse_line('data: {"choices":[{"delta":{"content":"x"},"finish_reason":null}]}')
    assert not null_reason.completed


def test_missing_or_empty_choices_yield_empty_event() -> None:
    assert parse_line('data: {"id":"x"}') == ParsedEvent()
    assert parse_line('data: {"choices":[]}') == ParsedEvent()
    assert parse_line('data: {"choices":["oops"]}') == ParsedEvent()
