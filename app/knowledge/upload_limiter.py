"""上传并发信号量：并发占满时按 429 降级，而不是让请求无限排队。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.framework.exceptions import ClientException
from app.framework.result import ErrorCode


class UploadLimiter:
    def __init__(self, max_concurrency: int, wait_timeout_seconds: float = 0.5) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency 必须大于 0")
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._wait_timeout = max(0.0, wait_timeout_seconds)
        self._max_concurrency = max_concurrency

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    @property
    def available(self) -> int:
        return self._semaphore._value

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """在超时窗口内取到名额则放行，否则抛 429 业务错误。"""

        if self._wait_timeout > 0:
            try:
                await asyncio.wait_for(self._semaphore.acquire(), self._wait_timeout)
            except TimeoutError as exc:
                raise ClientException(
                    "当前上传任务过多，请稍后重试", code=ErrorCode.RATE_LIMITED
                ) from exc
        else:
            if self._semaphore.locked():
                raise ClientException(
                    "当前上传任务过多，请稍后重试", code=ErrorCode.RATE_LIMITED
                )
            await self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()
