"""MCP 管理请求模型。"""

from typing import Any

from pydantic import BaseModel, Field


class McpEnabledWrite(BaseModel):
    enabled: bool


class McpDebugRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
