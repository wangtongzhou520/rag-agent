"""MCP SDK 无关的工具定义、调用结果与服务发现状态。"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    qualified_key: str
    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolOutput:
    tool_id: str
    content: str
    is_error: bool = False
    structured_content: dict[str, Any] | None = None


@dataclass(slots=True)
class McpServerSnapshot:
    name: str
    url: str
    status: str = "offline"
    server_name: str | None = None
    server_version: str | None = None
    tool_count: int = 0
    error_message: str | None = None
    discovered_at: int | None = None
