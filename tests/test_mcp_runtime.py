"""MCP 注册表、运行时提参与管理路由测试。"""

from typing import cast

from app.admin.mcp.router import router
from app.rag.mcp.executor import McpClientToolExecutor
from app.rag.mcp.models import ToolDefinition, ToolOutput
from app.rag.mcp.registry import McpToolRegistry
from app.rag.mcp.runtime import McpQuestionExecutor
from app.system.auth.deps import require_admin


class FakeToolExecutor:
    def __init__(self, definition: ToolDefinition) -> None:
        self.definition = definition
        self.parameters = None

    async def execute(self, parameters):
        self.parameters = parameters
        return ToolOutput(self.definition.qualified_key, "北京未来三天晴")


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = []

    async def chat(self, request, tier=None, preferred_model_id=None):
        self.calls.append((request, tier))
        return self.response


def definition() -> ToolDefinition:
    return ToolDefinition(
        qualified_key="internal:weather_query",
        server_name="internal",
        name="weather_query",
        description="天气查询",
        input_schema={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "days": {"type": "integer", "default": 3},
            },
            "required": ["city"],
        },
    )


async def test_runtime_extracts_parameters_and_executes_registered_tool() -> None:
    registry = McpToolRegistry()
    executor = FakeToolExecutor(definition())
    registry.replace_server(
        "internal", [cast(McpClientToolExecutor, executor)]
    )
    runtime = McpQuestionExecutor(registry, FakeLLM('{"city":"北京"}'))

    result = await runtime.call("internal:weather_query", "北京未来天气")

    assert result == "北京未来三天晴"
    assert executor.parameters == {"city": "北京", "days": 3}


async def test_runtime_returns_clarification_without_calling_tool() -> None:
    registry = McpToolRegistry()
    executor = FakeToolExecutor(definition())
    registry.replace_server(
        "internal", [cast(McpClientToolExecutor, executor)]
    )
    runtime = McpQuestionExecutor(registry, FakeLLM("{}"))

    result = await runtime.call("internal:weather_query", "帮我查天气")

    assert "需要参数：city" in result
    assert executor.parameters is None


def test_registry_applies_server_and_tool_switches() -> None:
    registry = McpToolRegistry()
    executor = cast(McpClientToolExecutor, FakeToolExecutor(definition()))
    registry.replace_server("internal", [executor])
    assert registry.get_executor("internal:weather_query") is executor

    registry.set_tool_enabled("internal:weather_query", False)
    assert registry.get_executor("internal:weather_query") is None
    registry.set_tool_enabled("internal:weather_query", True)
    registry.set_server_enabled("internal", False)
    assert registry.get_executor("internal:weather_query") is None


def test_all_mcp_management_routes_require_admin() -> None:
    assert len(router.routes) == 6
    for route in router.routes:
        assert require_admin in {
            dependency.call for dependency in route.dependant.dependencies
        }
