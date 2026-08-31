"""百炼文本重排序协议客户端与 noop 客户端。"""

from typing import Protocol

import httpx

from app.model_runtime.http import (
    HttpClientFactory,
    ModelClientErrorType,
    ModelClientException,
    resolve_url,
)
from app.model_runtime.routing import ModelCapability, ModelTarget
from app.rag.retrieval.models import RetrievedChunk


class RerankClient(Protocol):
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_n: int,
        target: ModelTarget,
    ) -> list[RetrievedChunk]: ...


class BaiLianRerankClient:
    provider = "bailian"

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

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_n: int,
        target: ModelTarget,
    ) -> list[RetrievedChunk]:
        if not self._api_key:
            raise ModelClientException(
                "provider bailian 缺少 api key",
                ModelClientErrorType.PROVIDER_ERROR,
            )
        url = resolve_url(
            target.candidate.url,
            self._provider_url,
            self._endpoints.get(ModelCapability.RERANK.value),
        )
        body = {
            "model": target.candidate.model,
            "query": query,
            "documents": [candidate.text for candidate in candidates],
            "top_n": min(max(1, top_n), len(candidates)),
        }
        try:
            response = await self._http.derive(target.timeout_ms).post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
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
        try:
            values = response.json()["results"]
            indexes = [int(item["index"]) for item in values]
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelClientException(
                "rerank 响应结构不符（缺 results/index）",
                ModelClientErrorType.INVALID_RESPONSE,
                cause=exc,
            ) from exc
        if any(index < 0 or index >= len(candidates) for index in indexes):
            raise ModelClientException(
                "rerank 返回非法文档索引",
                ModelClientErrorType.INVALID_RESPONSE,
            )
        return [candidates[index] for index in indexes]


class NoopRerankClient:
    provider = "noop"

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_n: int,
        target: ModelTarget,
    ) -> list[RetrievedChunk]:
        del query, target
        return candidates[:top_n]
