"""You.com 联网搜索工具：按 key 注册、结果归一化与错误降级。"""

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.tools import youcom


async def tool_names(server: FastMCP) -> set[str]:
    async with Client(server) as client:
        return {tool.name for tool in await client.list_tools()}


async def test_tool_registers_only_when_api_key_present(monkeypatch) -> None:
    monkeypatch.delenv(youcom.API_KEY_ENV, raising=False)
    without_key = FastMCP("without-key")
    youcom.register(without_key)

    assert "youcom_search" not in await tool_names(without_key)

    monkeypatch.setenv(youcom.API_KEY_ENV, "test-key")
    with_key = FastMCP("with-key")
    youcom.register(with_key)

    assert "youcom_search" in await tool_names(with_key)


def test_normalize_results_flattens_web_and_news_and_truncates() -> None:
    payload = {
        "web": [
            {"title": "A", "url": "https://a", "snippets": ["片段一", "片段二"]},
            {"title": "B", "url": "https://b", "description": "描述"},
        ],
        "news": [{"title": "C", "url": "https://c", "description": "新闻"}],
    }

    results = youcom.normalize_results(payload, 2)

    assert [item["title"] for item in results] == ["A", "B"]
    assert results[0]["snippet"] == "片段一 片段二"
    assert results[1]["section"] == "web"

    assert [item["title"] for item in youcom.normalize_results(payload, 10)] == [
        "A",
        "B",
        "C",
    ]
    assert youcom.normalize_results({}, 5) == []


async def test_empty_query_is_rejected_without_network() -> None:
    with pytest.raises(ToolError, match="查询词不能为空"):
        await youcom.youcom_search("   ")


async def test_search_normalizes_payload_and_clamps_count(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("X-API-Key")
        return httpx.Response(
            200,
            json={"web": [{"title": "R", "url": "https://r", "description": "摘要"}]},
        )

    monkeypatch.setenv(youcom.API_KEY_ENV, "test-key")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        youcom.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(handler), timeout=1
        ),
    )

    payload = await youcom.youcom_search("育儿 睡眠", count=99)

    assert payload["count"] == youcom.MAX_COUNT
    assert payload["results"][0]["url"] == "https://r"
    assert captured["api_key"] == "test-key"
    assert "query=%E8%82%B2%E5%84%BF" in str(captured["url"])
    assert "count=20" in str(captured["url"])


async def test_search_failure_is_reported_as_tool_error(monkeypatch) -> None:
    monkeypatch.setenv(youcom.API_KEY_ENV, "test-key")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        youcom.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500)), timeout=1
        ),
    )

    with pytest.raises(ToolError, match="联网搜索失败"):
        await youcom.youcom_search("育儿")
