"""Embedding provider 薄子类（docs/04 §7.1）。"""

from app.model_runtime.embedding.base import AbstractOpenAIStyleEmbeddingClient
from app.model_runtime.routing import ModelProvider


class BaiLianEmbeddingClient(AbstractOpenAIStyleEmbeddingClient):
    provider = ModelProvider.BAILIAN

    def max_batch_size(self) -> int:
        """百炼 qwen3.7-text-embedding 同步接口单次最多接收 20 条文本。"""
        return 20


class SiliconFlowEmbeddingClient(AbstractOpenAIStyleEmbeddingClient):
    provider = ModelProvider.SILICONFLOW


class OllamaEmbeddingClient(AbstractOpenAIStyleEmbeddingClient):
    provider = ModelProvider.OLLAMA

    def requires_api_key(self) -> bool:
        return False


class AIHubMixEmbeddingClient(AbstractOpenAIStyleEmbeddingClient):
    provider = ModelProvider.AIHUBMIX
