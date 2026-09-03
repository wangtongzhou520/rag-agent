"""问答域 REST 请求模型。"""

from pydantic import BaseModel


class ConversationTitleUpdate(BaseModel):
    title: str
