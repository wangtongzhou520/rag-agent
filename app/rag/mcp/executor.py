"""FastMCP Client 工具执行适配器。"""

import json
import time
from typing import Any

from fastmcp import Client

from app.framework.logging import get_logger
from app.rag.mcp.models import ToolDefinition, ToolOutput

logger = get_logger(__name__)


class McpClientToolExecutor:
    def __init__(
        self,
        client: Client,
        definition: ToolDefinition,
        timeout_seconds: int,
    ) -> None:
        self._client = client
        self.definition = definition
        self._timeout = timeout_seconds

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        started = time.monotonic()
        try:
            result = await self._client.call_tool(
                self.definition.name,
                parameters,
                raise_on_error=False,
                timeout=self._timeout,
            )
            texts = [
                str(item.text)
                for item in result.content
                if getattr(item, "type", None) == "text" and getattr(item, "text", None)
            ]
            structured = (
                result.structured_content
                if isinstance(result.structured_content, dict)
                else None
            )
            content = "\n".join(texts).strip()
            if not content and structured:
                content = json.dumps(structured, ensure_ascii=False)
            logger.info(
                "mcp tool called",
                tool_id=self.definition.qualified_key,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                content_size=len(content),
                success=not result.is_error,
            )
            return ToolOutput(
                self.definition.qualified_key,
                content,
                bool(result.is_error),
                structured,
            )
        except Exception as exc:  # noqa: BLE001 - MCP 下游异常统一收敛为领域结果
            logger.warning(
                "mcp tool call failed",
                tool_id=self.definition.qualified_key,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                error_type=type(exc).__name__,
            )
            return ToolOutput(
                self.definition.qualified_key,
                "工具调用失败，请稍后重试。",
                True,
            )
