"""RoutingLLMService 与 ModelRoutingExecutor 测试：容错切换、熔断、首包探测。

全部用假 ChatClient 注入，不发真实 HTTP（docs/04 §14 测试要点）。
"""

import pytest

from app.framework.chat_types import ChatMessage, ChatRequest, ChatRole
from app.framework.exceptions import RemoteException
from app.model_runtime.chat.base import StreamCancellationHandle
from app.model_runtime.chat.service import ALL_FAILED_MESSAGE, RoutingLLMService
from app.model_runtime.routing import (
    ModelCandidate,
    ModelHealthStore,
    ModelSelector,
    Tier,
    TierPlan,
)


class Recorder:
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


class FakeChatClient:
    """按候选 id 脚本化行为：sync_fail / stream_timeout / 正常流。"""

    def __init__(self, sync_fail: set[str] | None = None, stream_timeout: set[str] | None = None):
        self.sync_fail = sync_fail or set()
        self.stream_timeout = stream_timeout or set()
        self.stream_calls: list[str] = []

    async def chat(self, request: ChatRequest, target) -> str:
        if target.id in self.sync_fail:
            raise RuntimeError(f"{target.id} boom")
        return f"answer-from-{target.id}"

    async def stream_chat(self, request: ChatRequest, callback, target) -> StreamCancellationHandle:
        self.stream_calls.append(target.id)
        if target.id in self.stream_timeout:
            # 模拟首包超时：永不回调
            return StreamCancellationHandle()
        await callback.on_content(f"chunk-from-{target.id}")
        await callback.on_complete()
        return StreamCancellationHandle()


def make_service(
    *,
    sync_fail: set[str] | None = None,
    stream_timeout: set[str] | None = None,
    health: ModelHealthStore | None = None,
) -> tuple[RoutingLLMService, FakeChatClient, ModelHealthStore]:
    candidates = {
        "a": ModelCandidate("a", "bailian", "m-a", supports_thinking=True),
        "b": ModelCandidate("b", "bailian", "m-b", supports_thinking=True),
    }
    tiers = {Tier.STANDARD: TierPlan(("a", "b"), 50)}
    health = health or ModelHealthStore()
    selector = ModelSelector(candidates, tiers, health_store=health)
    client = FakeChatClient(sync_fail=sync_fail, stream_timeout=stream_timeout)
    service = RoutingLLMService(selector, health, {"bailian": client})
    return service, client, health


def make_request() -> ChatRequest:
    return ChatRequest(messages=[ChatMessage(role=ChatRole.USER, content="你好")])


async def test_chat_falls_back_to_next_candidate() -> None:
    service, _, health = make_service(sync_fail={"a"})

    assert await service.chat(make_request()) == "answer-from-b"
    # 失败计入熔断
    _, failures, _ = await health.snapshot("a")
    assert failures == 1


async def test_chat_all_candidates_failed_raises_remote() -> None:
    service, _, _ = make_service(sync_fail={"a", "b"})

    with pytest.raises(RemoteException, match="All Chat model candidates failed"):
        await service.chat(make_request())


async def test_chat_empty_candidates_raises_remote() -> None:
    selector = ModelSelector({}, {})
    service = RoutingLLMService(selector, ModelHealthStore(), {})

    with pytest.raises(RemoteException, match="No Chat model candidates available"):
        await service.chat(make_request())


async def test_chat_skips_circuit_open_candidate() -> None:
    health = ModelHealthStore(failure_threshold=2)
    await health.mark_failure("a")
    await health.mark_failure("a")
    service, client, _ = make_service(health=health)

    assert await service.chat(make_request()) == "answer-from-b"
    assert "a" not in client.stream_calls


async def test_stream_first_candidate_probe_timeout_switches_invisibly() -> None:
    service, client, _ = make_service(stream_timeout={"a"})
    downstream = Recorder()

    handle = await service.stream_chat(make_request(), downstream)

    assert handle is not None
    assert client.stream_calls == ["a", "b"]
    # 前端只见第二候选内容：commit 前零字节
    assert downstream.contents == ["chunk-from-b"]
    assert downstream.completed == 1
    assert downstream.errors == []


async def test_stream_all_failed_notifies_and_raises() -> None:
    service, _, _ = make_service(stream_timeout={"a", "b"})
    downstream = Recorder()

    with pytest.raises(RemoteException, match="大模型调用失败"):
        await service.stream_chat(make_request(), downstream)

    assert len(downstream.errors) == 1
    assert str(downstream.errors[0]) == ALL_FAILED_MESSAGE
    assert downstream.contents == []
