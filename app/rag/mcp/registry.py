"""MCP 工具进程级注册表与启停快照。"""

from app.rag.mcp.executor import McpClientToolExecutor


class McpToolRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, McpClientToolExecutor] = {}
        self._tool_enabled: dict[str, bool] = {}
        self._server_enabled: dict[str, bool] = {}

    def replace_server(
        self, server_name: str, executors: list[McpClientToolExecutor]
    ) -> None:
        self._executors = {
            key: value
            for key, value in self._executors.items()
            if value.definition.server_name != server_name
        }
        self._executors.update(
            {executor.definition.qualified_key: executor for executor in executors}
        )

    def unregister_server(self, server_name: str) -> None:
        self.replace_server(server_name, [])

    def get_executor(self, tool_id: str) -> McpClientToolExecutor | None:
        executor = self._executors.get(tool_id)
        if executor is None or not self.is_enabled(tool_id):
            return None
        return executor

    def get_any_executor(self, tool_id: str) -> McpClientToolExecutor | None:
        return self._executors.get(tool_id)

    def list_all(self) -> list[McpClientToolExecutor]:
        return sorted(
            self._executors.values(), key=lambda item: item.definition.qualified_key
        )

    def set_tool_enabled(self, tool_id: str, enabled: bool) -> None:
        self._tool_enabled[tool_id] = enabled

    def set_server_enabled(self, server_name: str, enabled: bool) -> None:
        self._server_enabled[server_name] = enabled

    def is_enabled(self, tool_id: str) -> bool:
        executor = self._executors.get(tool_id)
        if executor is None:
            return False
        server_enabled = self._server_enabled.get(
            executor.definition.server_name, True
        )
        return server_enabled and self._tool_enabled.get(tool_id, True)

    def server_enabled(self, server_name: str) -> bool:
        return self._server_enabled.get(server_name, True)
