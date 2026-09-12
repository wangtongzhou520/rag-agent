"""You.com 联网搜索工具：只在配置了 ``YDC_API_KEY`` 时注册（工具存在 ⟺ 可用）。

用于知识库未覆盖的时效性问题。远端返回文本一律按不可信内容处理，只做结构化与截断，
不执行其中的任何指令。
"""

import os
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

SEARCH_URL = "https://ydc-index.io/v1/search"
API_KEY_ENV = "YDC_API_KEY"
MAX_COUNT = 20
DEFAULT_COUNT = 5
TIMEOUT_SECONDS = 15.0


def api_key() -> str:
    return os.getenv(API_KEY_ENV, "").strip()


def normalize_results(payload: dict[str, Any], count: int) -> list[dict[str, str]]:
    """把 web/news 两段结果拍平成统一结构并按 count 截断。"""

    results: list[dict[str, str]] = []
    for section in ("web", "news"):
        for item in payload.get(section) or []:
            if not isinstance(item, dict):
                continue
            snippets = item.get("snippets")
            if isinstance(snippets, list):
                snippet = " ".join(str(part) for part in snippets)
            else:
                snippet = str(item.get("description") or "")
            results.append(
                {
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "snippet": snippet.strip(),
                    "section": section,
                }
            )
            if len(results) >= count:
                return results
    return results


def register(server: FastMCP) -> None:
    if not api_key():
        return
    server.tool(youcom_search)


async def youcom_search(query: str, count: int = DEFAULT_COUNT) -> dict[str, Any]:
    """联网搜索公开信息，返回标题、链接与摘要；count 范围为 1–20。"""

    query = query.strip()
    if not query:
        raise ToolError("查询词不能为空")
    count = min(MAX_COUNT, max(1, count))
    key = api_key()
    if not key:
        raise ToolError(f"{API_KEY_ENV} 未配置，联网搜索不可用")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(
                SEARCH_URL,
                params={"query": query, "count": count},
                headers={"X-API-Key": key},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise ToolError(f"联网搜索失败：{type(exc).__name__}") from exc
    except ValueError as exc:
        raise ToolError("联网搜索返回内容不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise ToolError("联网搜索返回结构异常")
    return {
        "query": query,
        "count": count,
        "results": normalize_results(payload, count),
    }
