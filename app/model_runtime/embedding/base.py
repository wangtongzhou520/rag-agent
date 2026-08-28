"""EmbeddingClient 协议与 OpenAI 兼容基类（docs/04 §7.1）。

请求体 OpenAI 兼容：{model, input, dimensions, encoding_format: "float"}；
子类钩子 max_batch_size()（默认 0 不限）超限分片并保持返回顺序与输入一致。
"""

from typing import Protocol

import httpx

from app.framework.logging import get_logger
from app.model_runtime.http import (
    HttpClientFactory,
    ModelClientErrorType,
    ModelClientException,
    resolve_url,
)
from app.model_runtime.routing import ModelCapability, ModelTarget

logger = get_logger(__name__)


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str], target: ModelTarget) -> list[list[float]]:
        ...


class AbstractOpenAIStyleEmbeddingClient:
    """OpenAI 兼容 embedding 公共实现；provider 薄子类见 providers.py。"""

    provider: str = ""

    def __init__(
        self,
        http: HttpClientFactory,
        provider_url: str,
        api_key: str = "",
        endpoints: dict | None = None,
    ) -> None:
        self._http = http
        self._provider_url = provider_url
        self._api_key = api_key
        self._endpoints = dict(endpoints or {})

    def requires_api_key(self) -> bool:
        return True

    def max_batch_size(self) -> int:
        """单批最大条数；0 = 不限制。"""
        return 0

    def _headers(self) -> dict[str, str]:
        if not self.requires_api_key():
            return {}
        if not self._api_key:
            raise ModelClientException(
                f"provider {self.provider} 缺少 api key",
                ModelClientErrorType.PROVIDER_ERROR,
            )
        return {"Authorization": f"Bearer {self._api_key}"}

    def _batches(self, texts: list[str]) -> list[list[str]]:
        size = self.max_batch_size()
        if size <= 0 or len(texts) <= size:
            return [texts]
        return [texts[i : i + size] for i in range(0, len(texts), size)]

    async def embed(self, texts: list[str], target: ModelTarget) -> list[list[float]]:
        """整批（或分片）调用；返回顺序与输入一致。"""
        url = resolve_url(
            target.candidate.url,
            self._provider_url,
            self._endpoints.get(ModelCapability.EMBEDDING.value),
        )
        results: list[list[float]] = []
        for batch in self._batches(texts):
            results.extend(await self._embed_batch(url, batch, target))
        return results

    async def _embed_batch(
        self, url: str, texts: list[str], target: ModelTarget
    ) -> list[list[float]]:
        body: dict = {
            "model": target.candidate.model,
            "input": texts,
            "encoding_format": "float",
        }
        if target.candidate.dimension is not None:
            body["dimensions"] = target.candidate.dimension
        client = self._http.derive(target.timeout_ms)
        try:
            response = await client.post(url, json=body, headers=self._headers())
        except httpx.TransportError as exc:
            raise ModelClientException(
                f"网络错误: {exc}", ModelClientErrorType.NETWORK_ERROR, cause=exc
            ) from exc
        if response.status_code != 200:
            raise ModelClientException(
                f"provider 返回 HTTP {response.status_code}",
                ModelClientErrorType.from_http_status(response.status_code),
                http_status=response.status_code,
            )
        return self._extract_vectors(response, expected=len(texts))

    @staticmethod
    def _extract_vectors(
        response: httpx.Response, expected: int
    ) -> list[list[float]]:
        try:
            data = response.json()["data"]
            ordered = sorted(data, key=lambda item: item["index"])
            vectors = [item["embedding"] for item in ordered]
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelClientException(
                "embedding 响应结构不符（缺 data/index/embedding）",
                ModelClientErrorType.INVALID_RESPONSE,
                cause=exc,
            ) from exc
        if len(vectors) != expected:
            raise ModelClientException(
                f"embedding 返回条数 {len(vectors)} 与输入 {expected} 不符",
                ModelClientErrorType.INVALID_RESPONSE,
            )
        return vectors
