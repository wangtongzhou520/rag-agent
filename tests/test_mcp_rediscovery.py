"""MCP Server 后台指数退避重发现。"""

import asyncio
import time

from app.framework.config import McpRediscoverySettings, McpServerSettings, McpSettings
from app.rag.mcp.client import McpClientManager
from app.rag.mcp.models import McpServerSnapshot
from app.rag.mcp.registry import McpToolRegistry


def build_manager(**overrides) -> McpClientManager:
    rediscovery = McpRediscoverySettings(**overrides)
    settings = McpSettings(
        servers=[
            McpServerSettings(name="internal", url="http://127.0.0.1:1", timeout_seconds=1)
        ],
        rediscovery=rediscovery,
    )
    return McpClientManager(settings, McpToolRegistry())


def test_backoff_sequence_grows_and_caps() -> None:
    manager = build_manager(
        initial_delay_seconds=1, multiplier=2, max_delay_seconds=8
    )

    delays = [manager._schedule_retry("internal") for _ in range(5)]

    assert delays == [1, 2, 4, 8, 8]
    assert manager._failures["internal"] == 5

    manager._clear_retry("internal")

    assert manager._failures == {}
    assert manager._next_retry == {}


async def test_failed_discovery_schedules_retry() -> None:
    manager = build_manager()

    snapshot = await manager.refresh("internal")

    assert snapshot.status == "offline"
    assert snapshot.tool_count == 0
    assert manager._failures["internal"] == 1
    assert manager._next_retry["internal"] > time.monotonic()


async def test_rediscovery_loop_retries_due_servers_and_stops() -> None:
    calls: list[str] = []
    manager = build_manager(initial_delay_seconds=0.1, max_delay_seconds=0.2)

    async def fake_connect(server) -> McpServerSnapshot:
        calls.append(server.name)
        manager._clear_retry(server.name)
        return McpServerSnapshot(name=server.name, url=server.url, status="online")

    manager._connect = fake_connect  # type: ignore[method-assign]
    manager._failures["internal"] = 1
    manager._next_retry["internal"] = time.monotonic() - 1

    await manager.start_rediscovery()
    await asyncio.sleep(0.4)
    await manager.stop_rediscovery()

    assert calls == ["internal"]
    assert manager._failures == {}
    assert manager._rediscovery_task is None


async def test_rediscovery_disabled_keeps_startup_only_behaviour() -> None:
    manager = build_manager(enabled=False)

    await manager.start_rediscovery()

    assert manager._rediscovery_task is None
