"""跨模块共享的对话类型。

docs/04 §11 约定：ChatRequest / ChatMessage 等跨模块约定类型放 framework，
model_runtime 只引用不定义。
"""

from enum import StrEnum

from pydantic import BaseModel


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str


class ChatRequest(BaseModel):
    """一次 LLM 调用请求；采样参数 None 即不下发。"""

    messages: list[ChatMessage]
    thinking: bool = False
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int | None = None
