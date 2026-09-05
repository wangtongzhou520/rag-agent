"""Agent Profile 管理请求模型。"""

from pydantic import BaseModel


class AgentProfileWrite(BaseModel):
    name: str
    description: str | None = None
    avatar: str | None = None


class AgentPromptWrite(BaseModel):
    content: str | None = None
