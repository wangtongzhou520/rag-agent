"""FastMCP Client 生命周期、服务发现与注册表刷新。"""

import asyncio
import os
import time
from urllib.parse import urlparse

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.types import Implementation

from app.framework.config import McpServerSettings, McpSettings
from app.framework.logging import get_logger
from app.rag.mcp.executor import McpClientToolExecutor
from app.rag.mcp.models import McpServerSnapshot, ToolDefinition
from app.rag.mcp.registry import McpToolRegistry

logger = get_logger(__name__)


class McpClientManager:
    def __init__(self, settings: McpSettings, registry: McpToolRegistry) -> None:
        self._settings = {server.name: server for server in settings.servers}
        self._registry = registry
        self._clients: dict[str, Client] = {}
        self._locks = {name: asyncio.Lock() for name in self._settings}
        self._snapshots = {
            name: McpServerSnapshot(name=name, url=server.url)
            for name, server in self._settings.items()
        }

    async def discover_all(self) -> None:
        await asyncio.gather(
            *(self.refresh(name) for name in self._settings), return_exceptions=True
        )

    async def refresh(self, server_name: str) -> McpServerSnapshot:
        server = self._settings.get(server_name)
        if server is None:
            raise ValueError("MCP Server 不存在")
        async with self._locks[server_name]:
            await self._close_client(server_name)
            return await self._connect(server)

    async def _connect(self, server: McpServerSettings) -> McpServerSnapshot:
        snapshot = self._snapshots[server.name]
        snapshot.status = "connecting"
        snapshot.error_message = None
        try:
            client = Client(
                self._transport(server),
                timeout=server.timeout_seconds,
                init_timeout=server.timeout_seconds,
                client_info=Implementation(name="ragent-bootstrap", version="1.0.0"),
            )
            await client.__aenter__()
            tools = await client.list_tools()
            executors = [
                McpClientToolExecutor(
                    client,
                    ToolDefinition(
                        qualified_key=f"{server.name}:{tool.name}",
                        server_name=server.name,
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=dict(tool.inputSchema or {}),
                    ),
                    server.timeout_seconds,
                )
                for tool in tools
            ]
            self._clients[server.name] = client
            self._registry.replace_server(server.name, executors)
            server_info = getattr(client.initialize_result, "serverInfo", None)
            snapshot.status = "online"
            snapshot.server_name = getattr(server_info, "name", None)
            snapshot.server_version = getattr(server_info, "version", None)
            snapshot.tool_count = len(executors)
            snapshot.discovered_at = int(time.time() * 1000)
            return snapshot
        except Exception as exc:  # noqa: BLE001 - 发现失败必须降级，不阻断 API 启动
            self._registry.unregister_server(server.name)
            snapshot.status = "offline"
            snapshot.tool_count = 0
            snapshot.error_message = _safe_error(exc)
            snapshot.discovered_at = int(time.time() * 1000)
            logger.warning(
                "mcp server discovery failed",
                server_name=server.name,
                error_type=type(exc).__name__,
            )
            return snapshot

    @staticmethod
    def _transport(server: McpServerSettings) -> StreamableHttpTransport:
        url = server.url.rstrip("/")
        if not url.endswith("/mcp"):
            url += "/mcp"
        headers: dict[str, str] = {}
        if server.auth_token_env:
            token = os.getenv(server.auth_token_env, "").strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        hostname = urlparse(url).hostname

        def http_client_factory(**kwargs) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                trust_env=hostname not in {"127.0.0.1", "localhost", "::1"},
                **kwargs,
            )

        return StreamableHttpTransport(
            url,
            headers=headers or None,
            httpx_client_factory=http_client_factory,
        )

    async def close(self) -> None:
        for server_name in list(self._clients):
            await self._close_client(server_name)

    async def _close_client(self, server_name: str) -> None:
        client = self._clients.pop(server_name, None)
        if client is None:
            return
        try:
            await client.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001 - 关闭失败不阻断其他资源释放
            logger.warning("mcp client close failed", server_name=server_name)

    def snapshots(self) -> list[McpServerSnapshot]:
        return [self._snapshots[name] for name in sorted(self._snapshots)]


def _safe_error(exc: Exception) -> str:
    value = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return value[:256]
