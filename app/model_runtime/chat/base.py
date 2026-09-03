"""ChatClient 协议、流式回调协议、取消句柄与 OpenAI 兼容基类（docs/04 §2/§6）。

OpenAI 兼容协议的公共逻辑（URL 解析、鉴权、请求体构造、错误分类、SSE 读取）
沉在 AbstractOpenAIStyleChatClient，每个 provider 一个薄子类（providers.py）。
"""

import asyncio
from collections.abc import Mapping
from typing import Protocol

import httpx

from app.framework.chat_types import ChatRequest
from app.framework.logging import get_logger
from app.model_runtime.chat.sse import parse_line
from app.model_runtime.http import (
    HttpClientFactory,
    ModelClientErrorType,
    ModelClientException,
    resolve_url,
)
from app.model_runtime.routing import ModelCapability, ModelTarget

logger = get_logger(__name__)


class StreamCallback(Protocol):
    """流式下游回调；首包探测期由 ProbeStreamBridge 代理，commit 前零字节。"""

    async def on_content(self, content: str) -> None: ...
    async def on_thinking(self, content: str) -> None: ...
    async def on_complete(self) -> None: ...
    async def on_error(self, error: Exception) -> None: ...


class StreamCancellationHandle:
    """取消句柄：关闭 httpx 响应流 + 取消读取 task。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._response: httpx.Response | None = None
        self._cancelled = False

    def bind(self, task: asyncio.Task, response: httpx.Response) -> None:
        self._task = task
        self._response = response

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    async def cancel(self) -> None:
        self._cancelled = True
        if self._response is not None:
            await self._response.aclose()
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def wait(self) -> None:
        """等待后台流读取完成，使调用方生命周期覆盖完整 SSE 流。"""
        if self._task is not None:
            await self._task


class ChatClient(Protocol):
    async def chat(self, request: ChatRequest, target: ModelTarget) -> str: ...
    async def stream_chat(
        self,
        request: ChatRequest,
        callback: StreamCallback,
        target: ModelTarget,
    ) -> StreamCancellationHandle: ...


class AbstractOpenAIStyleChatClient:
    """OpenAI 兼容协议公共实现；子类只需声明 provider 与钩子覆写。"""

    provider: str = ""

    def __init__(
        self,
        http: HttpClientFactory,
        provider_url: str,
        api_key: str = "",
        endpoints: Mapping[str, str] | None = None,
    ) -> None:
        self._http = http
        self._provider_url = provider_url
        self._api_key = api_key
        self._endpoints = dict(endpoints or {})

    # ---- 子类钩子 ----

    def requires_api_key(self) -> bool:
        return True

    def customize_request_body(self, body: dict, request: ChatRequest) -> dict:
        return body

    # ---- 请求构造 ----

    def build_request_body(self, request: ChatRequest, target: ModelTarget) -> dict:
        body: dict = {
            "model": target.candidate.model,
            "messages": [
                {"role": str(message.role), "content": message.content}
                for message in request.messages
            ],
            # 恒带：thinking=True→true，否则 false
            "enable_thinking": bool(request.thinking),
        }
        for key in ("temperature", "top_p", "top_k", "max_tokens"):
            value = getattr(request, key)
            if value is not None:
                body[key] = value
        return self.customize_request_body(body, request)

    def _headers(self) -> dict[str, str]:
        if not self.requires_api_key():
            return {}
        if not self._api_key:
            raise ModelClientException(
                f"provider {self.provider} 缺少 api key",
                ModelClientErrorType.PROVIDER_ERROR,
            )
        return {"Authorization": f"Bearer {self._api_key}"}

    def _chat_url(self, target: ModelTarget) -> str:
        return resolve_url(
            target.candidate.url,
            self._provider_url,
            self._endpoints.get(ModelCapability.CHAT.value),
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code != 200:
            raise ModelClientException(
                f"provider 返回 HTTP {response.status_code}",
                ModelClientErrorType.from_http_status(response.status_code),
                http_status=response.status_code,
            )

    # ---- 同步调用 ----

    async def chat(self, request: ChatRequest, target: ModelTarget) -> str:
        body = {**self.build_request_body(request, target), "stream": False}
        client = self._http.derive(target.timeout_ms)
        try:
            response = await client.post(
                self._chat_url(target), json=body, headers=self._headers()
            )
        except httpx.TransportError as exc:
            raise ModelClientException(
                f"网络错误: {exc}", ModelClientErrorType.NETWORK_ERROR, cause=exc
            ) from exc
        self._raise_for_status(response)
        return self._extract_content(response)

    @staticmethod
    def _extract_content(response: httpx.Response) -> str:
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelClientException(
                "响应结构不符（缺 choices/message/content）",
                ModelClientErrorType.INVALID_RESPONSE,
                cause=exc,
            ) from exc
        if not content or not str(content).strip():
            raise ModelClientException(
                "响应 content 为空", ModelClientErrorType.INVALID_RESPONSE
            )
        return str(content)

    # ---- 流式调用 ----

    async def stream_chat(
        self,
        request: ChatRequest,
        callback: StreamCallback,
        target: ModelTarget,
    ) -> StreamCancellationHandle:
        """发起流式请求并启动后台读取任务；启动失败直接抛异常。"""
        body = {**self.build_request_body(request, target), "stream": True}
        client = self._http.streaming
        try:
            raw_request = client.build_request(
                "POST", self._chat_url(target), json=body, headers=self._headers()
            )
            response = await client.send(raw_request, stream=True)
        except httpx.TransportError as exc:
            raise ModelClientException(
                f"网络错误: {exc}", ModelClientErrorType.NETWORK_ERROR, cause=exc
            ) from exc
        if response.status_code != 200:
            status = response.status_code
            await response.aclose()
            raise ModelClientException(
                f"provider 返回 HTTP {status}",
                ModelClientErrorType.from_http_status(status),
                http_status=status,
            )

        handle = StreamCancellationHandle()
        task = asyncio.create_task(
            self._read_stream(response, callback, handle, request.thinking),
            name=f"llm-stream:{target.id}",
        )
        handle.bind(task, response)
        return handle

    async def _read_stream(
        self,
        response: httpx.Response,
        callback: StreamCallback,
        handle: StreamCancellationHandle,
        reasoning_enabled: bool,
    ) -> None:
        """逐行解析并回调；取消期间静默，取消后异常只记 info。"""
        completed = False
        try:
            async for line in response.aiter_lines():
                event = parse_line(line, reasoning_enabled)
                if event is None:
                    continue
                if event.reasoning:
                    await callback.on_thinking(event.reasoning)
                if event.content:
                    await callback.on_content(event.content)
                if event.completed:
                    completed = True
                    await callback.on_complete()
                    return
            if not completed:
                raise ModelClientException(
                    "流式响应异常结束", ModelClientErrorType.INVALID_RESPONSE
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if handle.cancelled:
                logger.info("stream interrupted after cancel", provider=self.provider)
                return
            await callback.on_error(exc)
            raise
        finally:
            await response.aclose()
