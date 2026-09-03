"""PG 任务队列的入队、领取、确认、重试和卡死恢复。"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.framework.async_task import AsyncTask
from app.framework.ids import new_native_uuid7


@dataclass(frozen=True, slots=True)
class ClaimedTask:
    id: int
    event_id: uuid.UUID
    task_type: str
    biz_key: str | None
    payload: dict
    retry_count: int
    max_retries: int


class TaskQueue:
    def __init__(self, engine: AsyncEngine, lease_seconds: int = 300) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._lease_seconds = max(30, lease_seconds)

    @staticmethod
    async def enqueue(
        session: AsyncSession,
        task_type: str,
        biz_key: str,
        payload: dict,
        *,
        max_retries: int = 5,
    ) -> AsyncTask:
        task = AsyncTask(
            event_id=new_native_uuid7(),
            task_type=task_type,
            biz_key=biz_key,
            payload=payload,
            status="pending",
            max_retries=max_retries,
        )
        session.add(task)
        await session.flush()
        await session.execute(
            text("SELECT pg_notify('ragent_task', :payload)"),
            {"payload": str(task.event_id)},
        )
        return task

    @staticmethod
    async def enqueue_latest(
        session: AsyncSession,
        task_type: str,
        biz_key: str,
        payload: dict,
        *,
        max_retries: int = 5,
    ) -> uuid.UUID:
        """合并同业务键的活跃事件；running 快照结束时会检测版本并重新排队。"""
        event_id = new_native_uuid7()
        statement = insert(AsyncTask).values(
            event_id=event_id,
            task_type=task_type,
            biz_key=biz_key,
            payload=payload,
            status="pending",
            retry_count=0,
            max_retries=max_retries,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[AsyncTask.task_type, AsyncTask.biz_key],
            index_where=AsyncTask.status.in_(("pending", "running")),
            set_={
                "event_id": statement.excluded.event_id,
                "payload": statement.excluded.payload,
                "retry_count": 0,
                "max_retries": statement.excluded.max_retries,
                "next_retry_at": None,
                "error_message": None,
            },
        )
        await session.execute(statement)
        await session.execute(
            text("SELECT pg_notify('ragent_task', :payload)"),
            {"payload": str(event_id)},
        )
        return event_id

    async def claim(self, owner: str) -> ClaimedTask | None:
        now = datetime.now(UTC).replace(tzinfo=None)
        async with self._sessions.begin() as session:
            task = await session.scalar(
                select(AsyncTask)
                .where(
                    AsyncTask.status == "pending",
                    or_(
                        AsyncTask.next_retry_at.is_(None),
                        AsyncTask.next_retry_at <= now,
                    ),
                )
                .order_by(AsyncTask.create_time, AsyncTask.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if task is None:
                return None
            task.status = "running"
            task.owner = owner
            task.lease_until = now + timedelta(seconds=self._lease_seconds)
            return ClaimedTask(
                task.id,
                task.event_id,
                task.task_type,
                task.biz_key,
                task.payload or {},
                task.retry_count,
                task.max_retries,
            )

    async def succeed(
        self, task_id: int, owner: str, event_id: uuid.UUID | None = None
    ) -> bool:
        async with self._sessions.begin() as session:
            task = await session.scalar(
                select(AsyncTask)
                .where(
                    AsyncTask.id == task_id,
                    AsyncTask.owner == owner,
                    AsyncTask.status == "running",
                )
                .with_for_update()
            )
            if task is None:
                return False
            if event_id is not None and task.event_id != event_id:
                task.status = "pending"
                task.owner = None
                task.lease_until = None
                return False
            task.status = "success"
            task.owner = None
            task.lease_until = None
            task.error_message = None
            return True

    async def fail(
        self,
        task_id: int,
        owner: str,
        error: str,
        event_id: uuid.UUID | None = None,
    ) -> bool:
        async with self._sessions.begin() as session:
            task = await session.scalar(
                select(AsyncTask)
                .where(
                    AsyncTask.id == task_id,
                    AsyncTask.owner == owner,
                    AsyncTask.status == "running",
                )
                .with_for_update()
            )
            if task is None:
                return False
            if event_id is not None and task.event_id != event_id:
                task.status = "pending"
                task.owner = None
                task.lease_until = None
                return False
            task.retry_count += 1
            task.owner = None
            task.lease_until = None
            task.error_message = error[:4000]
            if task.retry_count > task.max_retries:
                task.status = "failed"
                task.next_retry_at = None
                return True
            else:
                task.status = "pending"
                delay = min(300, 2 ** min(task.retry_count, 8))
                task.next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                    seconds=delay
                )
                return False

    async def renew(self, task_id: int, owner: str) -> bool:
        lease_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            seconds=self._lease_seconds
        )
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(AsyncTask)
                .where(
                    AsyncTask.id == task_id,
                    AsyncTask.owner == owner,
                    AsyncTask.status == "running",
                )
                .values(lease_until=lease_until)
            )
            return bool(result.rowcount)

    async def recover_stuck(self) -> list[tuple[ClaimedTask, bool]]:
        now = datetime.now(UTC).replace(tzinfo=None)
        async with self._sessions.begin() as session:
            tasks = (
                await session.scalars(
                    select(AsyncTask)
                    .where(
                        AsyncTask.status == "running",
                        AsyncTask.lease_until < now,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
            recovered = []
            for task in tasks:
                snapshot = ClaimedTask(
                    task.id,
                    task.event_id,
                    task.task_type,
                    task.biz_key,
                    task.payload or {},
                    task.retry_count,
                    task.max_retries,
                )
                task.retry_count += 1
                terminal = task.retry_count > task.max_retries
                task.status = "failed" if terminal else "pending"
                task.owner = None
                task.lease_until = None
                task.next_retry_at = None if terminal else now
                task.error_message = "任务租约超时"
                recovered.append((snapshot, terminal))
            return recovered
