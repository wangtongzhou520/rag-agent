"""M5 Worker 租约所有权边界测试。"""

import asyncio
import uuid
from typing import cast

from app.framework.task_queue import ClaimedTask, TaskQueue
from app.worker import WorkerTaskHandler, _process


async def test_process_cancels_handler_immediately_after_lease_loss() -> None:
    handler_started = asyncio.Event()
    handler_cancelled = asyncio.Event()

    class LostLeaseQueue:
        def __init__(self) -> None:
            self.succeed_calls = 0
            self.fail_calls = 0

        async def renew(self, task_id: int, owner: str) -> bool:
            return False

        async def succeed(self, *args) -> bool:
            self.succeed_calls += 1
            return True

        async def fail(self, *args) -> bool:
            self.fail_calls += 1
            return False

    class BlockingHandler:
        async def handle(self, task: ClaimedTask) -> None:
            handler_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                handler_cancelled.set()
                raise

    queue = LostLeaseQueue()
    task = ClaimedTask(
        id=1,
        event_id=uuid.uuid4(),
        task_type="chunk-document",
        biz_key="doc:1",
        payload={"docId": 1, "logId": 1},
        retry_count=0,
        max_retries=5,
    )

    await _process(
        cast(TaskQueue, queue),
        cast(WorkerTaskHandler, BlockingHandler()),
        task,
        "worker-a",
        renew_seconds=0.01,
        lease_seconds=0.05,
    )

    assert handler_started.is_set()
    assert handler_cancelled.is_set()
    assert queue.succeed_calls == 0
    assert queue.fail_calls == 0
