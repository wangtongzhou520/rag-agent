"""模型调用 HTTP 层：错误分类、URL 解析、按档位超时派生客户端缓存（docs/04 §6）。"""

from enum import StrEnum

import httpx

# 基础超时：读 60s / 连接 10s；派生客户端只改读超时，连接与写沿用基础值
_BASE_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
# 流式读超时不设上限，首包预算由探测层（probe.py）控制
_STREAM_TIMEOUT = httpx.Timeout(None, connect=10.0)


class ModelClientErrorType(StrEnum):
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    CLIENT_ERROR = "client_error"
    NETWORK_ERROR = "network_error"
    INVALID_RESPONSE = "invalid_response"
    PROVIDER_ERROR = "provider_error"

    @classmethod
    def from_http_status(cls, status: int) -> "ModelClientErrorType":
        if status in (401, 403):
            return cls.UNAUTHORIZED
        if status == 429:
            return cls.RATE_LIMITED
        if status >= 500:
            return cls.SERVER_ERROR
        return cls.CLIENT_ERROR


class ModelClientException(Exception):
    """模型调用异常；error_type 进日志与 Trace，路由层一律 fallback。"""

    def __init__(
        self,
        message: str,
        error_type: ModelClientErrorType,
        http_status: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.http_status = http_status
        self.__cause__ = cause


def resolve_url(
    candidate_url: str | None,
    provider_url: str | None,
    endpoint: str | None,
) -> str:
    """候选 url 优先，否则 provider.url + endpoint 斜杠智能拼接。"""
    if candidate_url:
        return candidate_url
    if not provider_url or not endpoint:
        raise ModelClientException(
            "provider url 或 endpoint 未配置",
            ModelClientErrorType.PROVIDER_ERROR,
        )
    return f"{provider_url.rstrip('/')}/{endpoint.lstrip('/')}"


class HttpClientFactory:
    """按档位 timeout_ms 派生 httpx 客户端（缓存复用连接池）。

    timeout_ms 为 None → 基础客户端；派生客户端只改读超时（read=timeout_ms/1000），
    连接/写沿用基础值。流式调用统一用独立长超时客户端。
    """

    def __init__(self) -> None:
        self._derived: dict[int, httpx.AsyncClient] = {}
        self._base: httpx.AsyncClient | None = None
        self._streaming: httpx.AsyncClient | None = None

    @property
    def base(self) -> httpx.AsyncClient:
        if self._base is None:
            self._base = httpx.AsyncClient(timeout=_BASE_TIMEOUT)
        return self._base

    @property
    def streaming(self) -> httpx.AsyncClient:
        if self._streaming is None:
            self._streaming = httpx.AsyncClient(timeout=_STREAM_TIMEOUT)
        return self._streaming

    def derive(self, timeout_ms: int | None) -> httpx.AsyncClient:
        if timeout_ms is None:
            return self.base
        client = self._derived.get(timeout_ms)
        if client is None:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    timeout_ms / 1000,
                    connect=_BASE_TIMEOUT.connect,
                    write=_BASE_TIMEOUT.write,
                    pool=_BASE_TIMEOUT.pool,
                )
            )
            self._derived[timeout_ms] = client
        return client

    async def aclose(self) -> None:
        for client in [self._base, self._streaming, *self._derived.values()]:
            if client is not None:
                await client.aclose()
        self._base = None
        self._streaming = None
        self._derived.clear()
