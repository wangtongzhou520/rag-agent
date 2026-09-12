"""上传并发信号量：占满即 429 降级，释放后恢复。"""

import asyncio

import pytest

from app.framework.exceptions import ClientException
from app.framework.result import ErrorCode
from app.knowledge.upload_limiter import UploadLimiter


async def test_limiter_rejects_when_saturated_without_waiting() -> None:
    limiter = UploadLimiter(max_concurrency=1, wait_timeout_seconds=0.0)

    async with limiter.slot():
        assert limiter.available == 0
        with pytest.raises(ClientException) as error:
            async with limiter.slot():
                raise AssertionError("不应拿到第二个名额")

    assert error.value.code == ErrorCode.RATE_LIMITED
    assert "上传任务过多" in error.value.message
    assert limiter.available == 1


async def test_limiter_times_out_into_rate_limit_and_releases() -> None:
    limiter = UploadLimiter(max_concurrency=1, wait_timeout_seconds=0.05)

    async with limiter.slot():
        with pytest.raises(ClientException) as error:
            async with limiter.slot():
                raise AssertionError("等待超时后不应进入临界区")

    assert error.value.code == ErrorCode.RATE_LIMITED
    assert limiter.available == 1

    async with limiter.slot():
        assert limiter.available == 0


async def test_limiter_allows_parallel_slots_up_to_limit() -> None:
    limiter = UploadLimiter(max_concurrency=2, wait_timeout_seconds=0.0)
    started: list[int] = []

    async def worker(index: int) -> None:
        async with limiter.slot():
            started.append(index)
            await asyncio.sleep(0.02)

    await asyncio.gather(worker(1), worker(2))

    assert sorted(started) == [1, 2]
    assert limiter.available == 2


def test_limiter_rejects_invalid_concurrency() -> None:
    with pytest.raises(ValueError, match="max_concurrency"):
        UploadLimiter(max_concurrency=0)
