"""消息反馈提交与 PG 队列消费：接口快速返回，worker 按事件时间最后写入获胜。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.exceptions import ClientException
from app.framework.result import ErrorCode
from app.framework.task_queue import ClaimedTask, TaskQueue
from app.rag.models import Message, MessageFeedback

FEEDBACK_TASK_TYPE = "message-feedback-persist"


class MessageFeedbackService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def submit(
        self,
        message_id: str,
        user_id: int,
        vote: int,
        reason: str | None = None,
        comment: str | None = None,
    ) -> None:
        if vote not in (-1, 1):
            raise ClientException("反馈值必须为 1 或 -1")
        normalized_reason = self._normalize(reason, 255, "反馈原因")
        normalized_comment = self._normalize(comment, 1024, "反馈说明")
        await self._enqueue(
            message_id,
            user_id,
            vote=vote,
            reason=normalized_reason,
            comment=normalized_comment,
            deleted=0,
        )

    async def remove(self, message_id: str, user_id: int) -> None:
        await self._enqueue(
            message_id,
            user_id,
            vote=0,
            reason=None,
            comment=None,
            deleted=1,
        )

    async def _enqueue(
        self,
        message_id: str,
        user_id: int,
        *,
        vote: int,
        reason: str | None,
        comment: str | None,
        deleted: int,
    ) -> None:
        parsed_id = self._parse_id(message_id)
        submitted_at = datetime.now(UTC).isoformat()
        async with self._sessions.begin() as session:
            message = await session.scalar(
                select(Message).where(
                    Message.id == parsed_id,
                    Message.user_id == user_id,
                    Message.role == "assistant",
                    Message.deleted == 0,
                )
            )
            if message is None:
                raise ClientException("消息不存在", code=ErrorCode.NOT_FOUND)
            await TaskQueue.enqueue_latest(
                session,
                FEEDBACK_TASK_TYPE,
                f"{user_id}:{message_id}",
                {
                    "messageId": message_id,
                    "userId": user_id,
                    "conversationId": str(message.conversation_id),
                    "vote": vote,
                    "reason": reason,
                    "comment": comment,
                    "deleted": deleted,
                    "submittedAt": submitted_at,
                },
            )

    @staticmethod
    def _parse_id(value: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except ValueError as exc:
            raise ClientException("消息 ID 无效") from exc

    @staticmethod
    def _normalize(value: str | None, limit: int, label: str) -> str | None:
        normalized = value.strip() if value else ""
        if len(normalized) > limit:
            raise ClientException(f"{label}不能超过 {limit} 个字符")
        return normalized or None


class MessageFeedbackTaskHandler:
    """消费反馈事件，数据库 update_time 作为乱序保护版本。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def handle(self, task: ClaimedTask) -> None:
        if task.task_type != FEEDBACK_TASK_TYPE:
            raise ValueError(f"未知反馈任务类型: {task.task_type}")
        payload = task.payload
        submitted_at = datetime.fromisoformat(str(payload["submittedAt"])).astimezone(UTC)
        submitted_at = submitted_at.replace(tzinfo=None)
        statement = insert(MessageFeedback).values(
            message_id=uuid.UUID(str(payload["messageId"])),
            user_id=int(payload["userId"]),
            conversation_id=uuid.UUID(str(payload["conversationId"])),
            vote=int(payload["vote"]),
            reason=payload.get("reason"),
            comment=payload.get("comment"),
            deleted=int(payload["deleted"]),
            create_time=submitted_at,
            update_time=submitted_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[MessageFeedback.message_id, MessageFeedback.user_id],
            set_={
                "conversation_id": statement.excluded.conversation_id,
                "vote": statement.excluded.vote,
                "reason": statement.excluded.reason,
                "comment": statement.excluded.comment,
                "deleted": statement.excluded.deleted,
                "update_time": statement.excluded.update_time,
            },
            where=MessageFeedback.update_time < statement.excluded.update_time,
        )
        async with self._sessions.begin() as session:
            message_exists = await session.scalar(
                select(Message.id).where(
                    Message.id == uuid.UUID(str(payload["messageId"])),
                    Message.user_id == int(payload["userId"]),
                    Message.role == "assistant",
                    Message.deleted == 0,
                )
            )
            if message_exists is None:
                return
            await session.execute(statement)
