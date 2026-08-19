"""SSE 事件协议定义（占位）。

六种事件保持现有前端契约；SseSender 发送器在 M1 主链路实现。
"""

from enum import StrEnum


class SseEventType(StrEnum):
    META = "meta"
    MESSAGE = "message"
    FINISH = "finish"
    CANCEL = "cancel"
    REJECT = "reject"
    DONE = "done"


# TODO(M1): SseSender（send(event, payload)，序列化 Result 包装后的 SSE 帧）
