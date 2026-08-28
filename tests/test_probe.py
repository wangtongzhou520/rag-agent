"""流式首包探测（缓冲-提交桥）测试（docs/04 §4）。"""

from app.model_runtime.chat.probe import ProbeResult, ProbeStreamBridge, await_first_packet


class Recorder:
    """记录下游收到的全部回调。"""

    def __init__(self) -> None:
        self.contents: list[str] = []
        self.thinkings: list[str] = []
        self.completed = 0
        self.errors: list[Exception] = []

    async def on_content(self, content: str) -> None:
        self.contents.append(content)

    async def on_thinking(self, content: str) -> None:
        self.thinkings.append(content)

    async def on_complete(self) -> None:
        self.completed += 1

    async def on_error(self, error: Exception) -> None:
        self.errors.append(error)


async def test_success_buffers_then_replays_in_order_and_streams_directly() -> None:
    downstream = Recorder()
    bridge = ProbeStreamBridge(downstream)

    await bridge.on_content("a")
    await bridge.on_thinking("想")
    await bridge.on_content("b")

    # commit 前下游零字节
    assert downstream.contents == []
    assert downstream.thinkings == []
    assert bridge.result is ProbeResult.SUCCESS

    result = await await_first_packet(bridge, 1000)

    assert result is ProbeResult.SUCCESS
    assert bridge.committed
    # commit 后按到达顺序 replay
    assert downstream.contents == ["a", "b"]
    assert downstream.thinkings == ["想"]

    # commit 后事件越过缓冲直传
    await bridge.on_content("c")
    await bridge.on_complete()
    assert downstream.contents == ["a", "b", "c"]
    assert downstream.completed == 1


async def test_first_outcome_wins() -> None:
    bridge = ProbeStreamBridge(Recorder())
    await bridge.on_content("x")
    await bridge.on_complete()
    assert bridge.result is ProbeResult.SUCCESS


async def test_timeout_when_no_packet_within_budget() -> None:
    downstream = Recorder()
    bridge = ProbeStreamBridge(downstream)

    result = await await_first_packet(bridge, 20)

    assert result is ProbeResult.TIMEOUT
    assert bridge.result is None
    assert not bridge.committed
    assert downstream.contents == []


async def test_error_outcome_keeps_downstream_silent() -> None:
    downstream = Recorder()
    bridge = ProbeStreamBridge(downstream)
    await bridge.on_error(RuntimeError("流炸了"))

    result = await await_first_packet(bridge, 1000)

    assert result is ProbeResult.ERROR
    assert isinstance(bridge.error, RuntimeError)
    # 失败路径缓冲被丢弃，下游始终零字节
    bridge.discard()
    assert downstream.errors == []
    assert downstream.contents == []


async def test_no_content_outcome() -> None:
    downstream = Recorder()
    bridge = ProbeStreamBridge(downstream)
    await bridge.on_complete()

    result = await await_first_packet(bridge, 1000)

    assert result is ProbeResult.NO_CONTENT
    assert not bridge.committed
    assert downstream.completed == 0
