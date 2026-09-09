"""M5 Redis 幂等原语与 Worker 消费编排单元测试。"""

import asyncio
import uuid
from typing import Any, cast

import pytest

from app.framework.idempotency import (
    ConsumeInProgressError,
    ConsumeMarkExecutor,
    ConsumeState,
    SubmitLockExecutor,
)
from app.framework.task_queue import ClaimedTask
from app.worker import WorkerTaskHandler


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        px: int | None = None,
        ex: int | None = None,
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script: str, _keys: int, key: str, *args: Any):
        if "idempotency:unlock" in script:
            if self.values.get(key) != args[0]:
                return 0
            del self.values[key]
            return 1
        if "idempotency:try-begin" in script:
            if key in self.values:
                return self.values[key]
            self.values[key] = f"0:{args[1]}"
            return "-1"
        if "idempotency:mark-consumed" in script:
            if self.values.get(key) != f"0:{args[0]}":
                return 0
            self.values[key] = "1"
            return 1
        if "idempotency:rollback-consume" in script:
            if self.values.get(key) != f"0:{args[0]}":
                return 0
            del self.values[key]
            return 1
        raise AssertionError("unexpected script")

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)


async def test_submit_lock_token_prevents_stale_unlock() -> None:
    redis = MemoryRedis()
    first = SubmitLockExecutor(redis, "test:", ttl_seconds=10)
    second = SubmitLockExecutor(redis, "test:", ttl_seconds=10)

    token = await first.try_lock("7")
    assert token is not None
    assert await second.try_lock("7") is None
    assert await second.unlock("7", "stale-token") is False
    assert await second.try_lock("7") is None
    assert await first.unlock("7", token) is True
    assert await second.try_lock("7") is not None


async def test_consume_mark_has_first_consuming_consumed_and_rollback_states() -> None:
    redis = MemoryRedis()
    first = ConsumeMarkExecutor(redis, "test:")
    second = ConsumeMarkExecutor(redis, "test:")

    states = await asyncio.gather(*(first.try_begin("event-1") for _ in range(20)))
    assert states.count(ConsumeState.FIRST_RUN) == 1
    assert states.count(ConsumeState.CONSUMING) == 19

    assert await first.mark_consumed("event-1") is True
    assert await second.try_begin("event-1") is ConsumeState.CONSUMED
    assert await first.rollback("event-1") is False
    assert await first.try_begin("event-2") is ConsumeState.FIRST_RUN
    assert await first.rollback("event-2") is True
    assert await second.try_begin("event-2") is ConsumeState.FIRST_RUN


def _task() -> ClaimedTask:
    return ClaimedTask(
        id=1,
        event_id=uuid.uuid4(),
        task_type="chunk-document",
        biz_key="doc:1",
        payload={"docId": 1, "logId": 1},
        retry_count=0,
        max_retries=5,
    )


async def test_worker_skips_consumed_event_and_rolls_back_failed_first_run() -> None:
    class Marks:
        def __init__(self) -> None:
            self.state = ConsumeState.CONSUMED
            self.completed = 0
            self.rolled_back = 0

        async def try_begin(self, key: str) -> ConsumeState:
            return self.state

        async def mark_consumed(self, key: str) -> bool:
            self.completed += 1
            return True

        async def rollback(self, key: str) -> bool:
            self.rolled_back += 1
            return True

    class Knowledge:
        def __init__(self) -> None:
            self.calls = 0
            self.fail = False

        async def handle(self, task: ClaimedTask) -> None:
            self.calls += 1
            if self.fail:
                raise RuntimeError("handler failed")

    marks = Marks()
    knowledge = Knowledge()
    handler = WorkerTaskHandler(
        cast(Any, knowledge), cast(Any, object()), cast(Any, marks)
    )

    await handler.handle(_task())
    assert knowledge.calls == 0

    marks.state = ConsumeState.FIRST_RUN
    await handler.handle(_task())
    assert knowledge.calls == 1
    assert marks.completed == 1

    knowledge.fail = True
    with pytest.raises(RuntimeError, match="handler failed"):
        await handler.handle(_task())
    assert marks.rolled_back == 1

    marks.state = ConsumeState.CONSUMING
    with pytest.raises(ConsumeInProgressError):
        await handler.handle(_task())
