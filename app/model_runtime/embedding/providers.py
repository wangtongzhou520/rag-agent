"""Embedding provider 薄子类（docs/04 §7.1）。"""

from app.model_runtime.embedding.base import AbstractOpenAIStyleEmbeddingClient
from app.model_runtime.routing import ModelProvider


class SiliconFlowEmbeddingClient(AbstractOpenAIStyleEmbeddingClient):
    provider = ModelProvider.SILICONFLOW


class OllamaEmbeddingClient(AbstractOpenAIStyleEmbeddingClient):
    provider = ModelProvider.OLLAMA

    def requires_api_key(self) -> bool:
        return False


class AIHubMixEmbeddingClient(AbstractOpenAIStyleEmbeddingClient):
    provider = ModelProvider.AIHUBMIX
