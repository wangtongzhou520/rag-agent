"""LLMService 协议与路由实现：同步走容错执行器，流式走首包探测（docs/04 §3.5/§4）。"""

import asyncio
from collections.abc import Mapping
from typing import Protocol

from app.framework.chat_types import ChatRequest
from app.framework.exceptions import RemoteException
from app.framework.logging import get_logger
from app.model_runtime.chat.base import (
    ChatClient,
    StreamCallback,
    StreamCancellationHandle,
)
from app.model_runtime.chat.probe import ProbeResult, ProbeStreamBridge, await_first_packet
from app.model_runtime.routing import (
    ModelHealthStore,
    ModelRoutingExecutor,
    ModelSelector,
    ModelTarget,
    Tier,
)

logger = get_logger(__name__)

ALL_FAILED_MESSAGE = "大模型调用失败，请稍后再试..."


class LLMService(Protocol):
    async def chat(
        self,
        request: ChatRequest,
        tier: Tier | str | None = None,
        preferred_model_id: str | None = None,
    ) -> str: ...

    async def stream_chat(
        self,
        request: ChatRequest,
        callback: StreamCallback,
        tier: Tier | str | None = None,
        preferred_model_id: str | None = None,
    ) -> StreamCancellationHandle: ...


class RoutingLLMService:
    """组合 ModelSelector（选候选）+ ModelRoutingExecutor（容错）+ ModelHealthStore（熔断）。"""

    def __init__(
        self,
        selector: ModelSelector,
        health_store: ModelHealthStore,
        clients: Mapping[str, ChatClient],
    ) -> None:
        self._selector = selector
        self._health_store = health_store
        self._clients = dict(clients)
        self._executor = ModelRoutingExecutor(health_store, self._clients)

    async def chat(
        self,
        request: ChatRequest,
        tier: Tier | str | None = None,
        preferred_model_id: str | None = None,
    ) -> str:
        targets = await self._selector.build_tier_targets(
            thinking=request.thinking,
            override=tier,
            preferred_model_id=preferred_model_id,
        )
        if not targets:
            raise RemoteException("No Chat model candidates available")
        return await self._executor.execute_with_fallback(
            targets,
            lambda client, target: client.chat(request, target),
            "Chat",
        )

    async def stream_chat(
        self,
        request: ChatRequest,
        callback: StreamCallback,
        tier: Tier | str | None = None,
        preferred_model_id: str | None = None,
    ) -> StreamCancellationHandle:
        targets = await self._selector.build_tier_targets(
            thinking=request.thinking,
            override=tier,
            preferred_model_id=preferred_model_id,
        )
        for target in targets:
            handle = await self._try_stream_candidate(request, callback, target)
            if handle is not None:
                return handle
        # 所有候选失败（含候选列表为空）：通知下游并抛出（docs/04 §13）
        await callback.on_error(RemoteException(ALL_FAILED_MESSAGE))
        raise RemoteException(ALL_FAILED_MESSAGE)

    async def _try_stream_candidate(
        self,
        request: ChatRequest,
        callback: StreamCallback,
        target: ModelTarget,
    ) -> StreamCancellationHandle | None:
        """单个候选的启动 + 首包探测；失败返回 None 由外层切下一候选。"""
        client = self._clients.get(str(target.candidate.provider))
        if client is None:
            logger.warning(
                "model client 缺失，跳过候选",
                model_id=target.id,
                provider=str(target.candidate.provider),
            )
            return None
        permit = await self._health_store.allow_call(target.id)
        if permit is None:
            return None

        bridge = ProbeStreamBridge(callback)
        handle: StreamCancellationHandle | None = None
        try:
            handle = await client.stream_chat(request, bridge, target)
            if handle is None:
                raise RemoteException("流式请求启动失败")
            result = await await_first_packet(bridge, target.timeout_ms)
        except asyncio.CancelledError:
            # 探测期间被中断/取消：取消该流并释放 HALF_OPEN 探测名额（docs/04 §4.2）
            if handle is not None:
                await _cancel_quietly(handle)
            await self._health_store.release_half_open_permit(permit)
            raise
        except Exception as exc:  # noqa: BLE001 启动失败一律 mark_failure 切下一候选
            logger.warning("流式请求启动失败，切换下一候选", model_id=target.id, error=str(exc))
            await self._health_store.mark_failure(target.id)
            return None

        if result is ProbeResult.SUCCESS:
            await self._health_store.mark_success(target.id)
            return handle

        reason = _probe_failure_reason(bridge, result)
        logger.warning(
            "流式首包探测失败，切换下一候选",
            model_id=target.id,
            probe_result=str(result),
            reason=reason,
        )
        await _cancel_quietly(handle)
        await self._health_store.mark_failure(target.id)
        return None


def _probe_failure_reason(bridge: ProbeStreamBridge, result: ProbeResult) -> str:
    """docs/04 §4.3 错误文案。"""
    if result is ProbeResult.TIMEOUT:
        return "流式首包超时"
    if result is ProbeResult.NO_CONTENT:
        return "流式请求未返回内容"
    if bridge.error is not None:
        return str(bridge.error)
    return "流式请求被中断"


async def _cancel_quietly(handle: StreamCancellationHandle) -> None:
    try:
        await handle.cancel()
    except Exception:
        logger.warning("取消流式请求失败", exc_info=True)
