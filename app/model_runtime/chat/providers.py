"""Chat provider 薄子类：公共逻辑在 AbstractOpenAIStyleChatClient。"""

from app.model_runtime.chat.base import AbstractOpenAIStyleChatClient
from app.model_runtime.routing import ModelProvider


class BaiLianChatClient(AbstractOpenAIStyleChatClient):
    provider = ModelProvider.BAILIAN


class SiliconFlowChatClient(AbstractOpenAIStyleChatClient):
    provider = ModelProvider.SILICONFLOW


class AIHubMixChatClient(AbstractOpenAIStyleChatClient):
    provider = ModelProvider.AIHUBMIX


class OllamaChatClient(AbstractOpenAIStyleChatClient):
    provider = ModelProvider.OLLAMA

    def requires_api_key(self) -> bool:
        return False
