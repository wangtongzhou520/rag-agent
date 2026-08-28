"""HTTP 层测试：错误分类、URL 解析、派生客户端缓存（docs/04 §6.2/§6.3）。"""

import pytest

from app.model_runtime.http import (
    HttpClientFactory,
    ModelClientErrorType,
    ModelClientException,
    resolve_url,
)


def test_http_status_error_mapping() -> None:
    assert ModelClientErrorType.from_http_status(401) is ModelClientErrorType.UNAUTHORIZED
    assert ModelClientErrorType.from_http_status(403) is ModelClientErrorType.UNAUTHORIZED
    assert ModelClientErrorType.from_http_status(429) is ModelClientErrorType.RATE_LIMITED
    assert ModelClientErrorType.from_http_status(500) is ModelClientErrorType.SERVER_ERROR
    assert ModelClientErrorType.from_http_status(503) is ModelClientErrorType.SERVER_ERROR
    assert ModelClientErrorType.from_http_status(404) is ModelClientErrorType.CLIENT_ERROR


def test_resolve_url_prefers_candidate_override() -> None:
    assert (
        resolve_url("https://custom.example.com/v1/chat", "https://p.example.com", "/chat")
        == "https://custom.example.com/v1/chat"
    )


def test_resolve_url_joins_provider_and_endpoint_smartly() -> None:
    assert resolve_url(None, "https://p.example.com/", "/v1/chat") == (
        "https://p.example.com/v1/chat"
    )
    assert resolve_url(None, "https://p.example.com", "v1/chat") == (
        "https://p.example.com/v1/chat"
    )


def test_resolve_url_missing_config_raises_provider_error() -> None:
    with pytest.raises(ModelClientException) as exc_info:
        resolve_url(None, "", "/v1/chat")
    assert exc_info.value.error_type is ModelClientErrorType.PROVIDER_ERROR


async def test_derive_client_cache_hits_by_timeout_ms() -> None:
    factory = HttpClientFactory()
    try:
        first = factory.derive(5000)
        assert factory.derive(5000) is first
        assert factory.derive(30000) is not first
        assert factory.derive(None) is factory.base
        assert factory.streaming is factory.streaming
        assert first.timeout.read == 5.0
    finally:
        await factory.aclose()
