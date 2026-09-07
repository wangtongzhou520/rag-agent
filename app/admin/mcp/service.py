"""MCP 服务状态、工具启停、重新发现与显式参数调试。"""

import time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.exceptions import ClientException
from app.rag.intent.orm import IntentNodeRecord
from app.rag.mcp.client import McpClientManager
from app.rag.mcp.orm import McpServerState, McpToolState
from app.rag.mcp.registry import McpToolRegistry
from app.system.audit.context import AuditContext


class McpAdminService:
    def __init__(
        self,
        engine: AsyncEngine,
        manager: McpClientManager,
        registry: McpToolRegistry,
    ) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._manager = manager
        self._registry = registry

    async def apply_persisted_states(self) -> None:
        async with self._sessions() as session:
            servers = (
                await session.scalars(
                    select(McpServerState).where(McpServerState.deleted == 0)
                )
            ).all()
            tools = (
                await session.scalars(
                    select(McpToolState).where(McpToolState.deleted == 0)
                )
            ).all()
        for row in servers:
            self._registry.set_server_enabled(row.server_name, bool(row.enabled))
        for row in tools:
            self._registry.set_tool_enabled(row.tool_id, bool(row.enabled))

    async def list_servers(self) -> list[dict]:
        snapshots = self._manager.snapshots()
        return [
            {
                "name": item.name,
                "url": item.url,
                "status": item.status,
                "serverName": item.server_name,
                "serverVersion": item.server_version,
                "enabled": self._registry.server_enabled(item.name),
                "toolCount": item.tool_count,
                "errorMessage": item.error_message,
                "discoveredAt": item.discovered_at,
            }
            for item in snapshots
        ]

    async def list_tools(self) -> dict:
        executors = self._registry.list_all()
        tool_ids = [item.definition.qualified_key for item in executors]
        linked: dict[str, int] = {}
        if tool_ids:
            async with self._sessions() as session:
                rows = (
                    await session.execute(
                        select(IntentNodeRecord.mcp_tool_id, func.count())
                        .where(
                            IntentNodeRecord.mcp_tool_id.in_(tool_ids),
                            IntentNodeRecord.kind == 2,
                            IntentNodeRecord.deleted == 0,
                        )
                        .group_by(IntentNodeRecord.mcp_tool_id)
                    )
                ).all()
            linked = {str(tool_id): int(count) for tool_id, count in rows}
        tools = [
            {
                "toolId": item.definition.qualified_key,
                "serverName": item.definition.server_name,
                "name": item.definition.name,
                "description": item.definition.description,
                "inputSchema": item.definition.input_schema,
                "enabled": self._registry.is_enabled(item.definition.qualified_key),
                "serverEnabled": self._registry.server_enabled(
                    item.definition.server_name
                ),
                "linkedIntentCount": linked.get(item.definition.qualified_key, 0),
            }
            for item in executors
        ]
        return {"tools": tools, "total": len(tools)}

    async def refresh(self, server_name: str) -> dict:
        try:
            await self._manager.refresh(server_name)
        except ValueError as exc:
            raise ClientException(str(exc)) from exc
        await self.apply_persisted_states()
        AuditContext.put(server_name, None, {"refreshed": True})
        return next(
            item for item in await self.list_servers() if item["name"] == server_name
        )

    async def set_server_enabled(
        self, server_name: str, enabled: bool, user_id: int
    ) -> None:
        if server_name not in {item.name for item in self._manager.snapshots()}:
            raise ClientException("MCP Server 不存在")
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(McpServerState).where(
                    McpServerState.server_name == server_name,
                    McpServerState.deleted == 0,
                )
            )
            before = {"serverName": server_name, "enabled": self._registry.server_enabled(server_name)}
            if row is None:
                row = McpServerState(
                    server_name=server_name,
                    enabled=int(enabled),
                    create_by=user_id,
                    update_by=user_id,
                )
                session.add(row)
            else:
                row.enabled = int(enabled)
                row.update_by = user_id
            AuditContext.put(server_name, before, {"serverName": server_name, "enabled": enabled})
        self._registry.set_server_enabled(server_name, enabled)

    async def set_tool_enabled(
        self, tool_id: str, enabled: bool, user_id: int
    ) -> None:
        executor = self._registry.get_any_executor(tool_id)
        if executor is None:
            raise ClientException("MCP 工具不存在")
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(McpToolState).where(
                    McpToolState.tool_id == tool_id, McpToolState.deleted == 0
                )
            )
            before = {"toolId": tool_id, "enabled": self._registry.is_enabled(tool_id)}
            if row is None:
                row = McpToolState(
                    tool_id=tool_id,
                    enabled=int(enabled),
                    create_by=user_id,
                    update_by=user_id,
                )
                session.add(row)
            else:
                row.enabled = int(enabled)
                row.update_by = user_id
            AuditContext.put(tool_id, before, {"toolId": tool_id, "enabled": enabled})
        self._registry.set_tool_enabled(tool_id, enabled)

    async def debug(self, tool_id: str, parameters: dict) -> dict:
        executor = self._registry.get_executor(tool_id)
        if executor is None:
            raise ClientException("MCP 工具不存在或已停用")
        started = time.monotonic()
        output = await executor.execute(parameters)
        result = {
            "toolId": tool_id,
            "success": not output.is_error,
            "content": output.content,
            "structuredContent": output.structured_content,
            "durationMs": int((time.monotonic() - started) * 1000),
        }
        AuditContext.put(tool_id, None, {**result, "content": _truncate(output.content)})
        return result


def _truncate(value: str, limit: int = 1000) -> str:
    return value if len(value) <= limit else value[:limit] + "…"
