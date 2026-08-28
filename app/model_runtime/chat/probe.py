"""流式首包探测（缓冲-提交桥），docs/04 §4。

语义：以档位 timeout_ms 为首包预算；预算内第一个 content/thinking 到达 →
SUCCESS 并 commit 放行缓冲；超时 / 报错 / 空完成 → 丢弃缓冲切下一候选。
commit 前下游收不到任何字节，切换候选对前端无感。
"""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from enum import StrEnum

from app.model_runtime.chat.base import StreamCallback


class ProbeResult(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    NO_CONTENT = "no_content"


class ProbeStreamBridge:
    """StreamCallback 代理：探测期缓冲动作，commit 后按到达顺序 replay 再直传。

    单事件循环内 ``_committed`` 判定与 replay 不需要锁（回调与 await 均在同一 loop）。
    """

    def __init__(self, downstream: StreamCallback) -> None:
        self._downstream = downstream
        self._event = asyncio.Event()
        self._result: ProbeResult | None = None
        self.error: Exception | None = None
        self._buffer: deque[Callable[[], Awaitable[None]]] = deque()
        self._committed = False

    @property
    def result(self) -> ProbeResult | None:
        return self._result

    @property
    def committed(self) -> bool:
        return self._committed

    def discard(self) -> None:
        """探测失败：丢弃缓冲，下游始终零字节。"""
        self._buffer.clear()

    async def wait(self) -> None:
        await self._event.wait()

    def _complete(self, result: ProbeResult) -> None:
        if self._result is None:
            self._result = result
            self._event.set()

    async def commit(self) -> None:
        """放行缓冲；此后事件越过缓冲直传下游。"""
        self._committed = True
        while self._buffer:
            action = self._buffer.popleft()
            await action()

    def _dispatch(self, action: Callable[[], Awaitable[None]]) -> Awaitable[None] | None:
        if self._committed:
            return action()
        self._buffer.append(action)
        return None

    async def on_content(self, content: str) -> None:
        self._complete(ProbeResult.SUCCESS)
        pending = self._dispatch(lambda: self._downstream.on_content(content))
        if pending is not None:
            await pending

    async def on_thinking(self, content: str) -> None:
        self._complete(ProbeResult.SUCCESS)
        pending = self._dispatch(lambda: self._downstream.on_thinking(content))
        if pending is not None:
            await pending

    async def on_complete(self) -> None:
        if self._result is None:
            # 无任何内容就完成 → 空完成，不触达下游
            self._complete(ProbeResult.NO_CONTENT)
            return
        pending = self._dispatch(self._downstream.on_complete)
        if pending is not None:
            await pending

    async def on_error(self, error: Exception) -> None:
        if self._result is None:
            self.error = error
            self._complete(ProbeResult.ERROR)
            return
        pending = self._dispatch(lambda: self._downstream.on_error(error))
        if pending is not None:
            await pending


async def await_first_packet(bridge: ProbeStreamBridge, budget_ms: int) -> ProbeResult:
    """以预算等待首包；SUCCESS 时 commit 放行。

    TODO(M5 trace)：挂 @trace_node(name="llm-first-packet", type="LLM_TTFT")。
    """
    try:
        await asyncio.wait_for(bridge.wait(), budget_ms / 1000)
    except TimeoutError:
        return ProbeResult.TIMEOUT
    if bridge.result is ProbeResult.SUCCESS:
        await bridge.commit()
    return bridge.result or ProbeResult.ERROR
