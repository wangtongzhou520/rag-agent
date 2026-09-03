"""会话列表、消息历史、重命名与软删除服务。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.exceptions import ClientException
from app.framework.result import ErrorCode
from app.rag.models import Conversation, ConversationSummary, Message, MessageFeedback


class ConversationService:
    """所有查询均以登录用户为边界，不接受请求传入的 user_id。"""

    def __init__(self, engine: AsyncEngine, title_max_length: int = 30) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._title_max_length = title_max_length

    async def list_conversations(self, user_id: int) -> list[dict]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(Conversation)
                    .where(
                        Conversation.user_id == user_id,
                        Conversation.deleted == 0,
                    )
                    .order_by(
                        Conversation.last_time.desc().nullslast(),
                        Conversation.create_time.desc(),
                    )
                )
            ).all()
        return [self._conversation(row) for row in rows]

    async def rename(self, conversation_id: str, user_id: int, title: str) -> None:
        normalized_title = title.strip()
        if not normalized_title:
            raise ClientException("会话标题不能为空")
        if len(normalized_title) > self._title_max_length:
            raise ClientException(f"会话标题不能超过 {self._title_max_length} 个字符")
        parsed_id = self._parse_id(conversation_id)
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(Conversation).where(
                    Conversation.conversation_id == parsed_id,
                    Conversation.user_id == user_id,
                    Conversation.deleted == 0,
                )
            )
            if row is None:
                raise ClientException("会话不存在", code=ErrorCode.NOT_FOUND)
            row.title = normalized_title

    async def delete(self, conversation_id: str, user_id: int) -> None:
        parsed_id = self._parse_id(conversation_id)
        filters = (
            Conversation.conversation_id == parsed_id,
            Conversation.user_id == user_id,
            Conversation.deleted == 0,
        )
        async with self._sessions.begin() as session:
            row = await session.scalar(select(Conversation.id).where(*filters))
            if row is None:
                raise ClientException("会话不存在", code=ErrorCode.NOT_FOUND)
            await session.execute(
                update(Conversation).where(*filters).values(deleted=1)
            )
            await session.execute(
                update(Message)
                .where(
                    Message.conversation_id == parsed_id,
                    Message.user_id == user_id,
                    Message.deleted == 0,
                )
                .values(deleted=1)
            )
            await session.execute(
                update(ConversationSummary)
                .where(
                    ConversationSummary.conversation_id == parsed_id,
                    ConversationSummary.user_id == user_id,
                    ConversationSummary.deleted == 0,
                )
                .values(deleted=1)
            )
            await session.execute(
                update(MessageFeedback)
                .where(
                    MessageFeedback.conversation_id == parsed_id,
                    MessageFeedback.user_id == user_id,
                    MessageFeedback.deleted == 0,
                )
                .values(deleted=1)
            )

    async def list_messages(self, conversation_id: str, user_id: int) -> list[dict]:
        parsed_id = self._parse_id(conversation_id)
        async with self._sessions() as session:
            exists = await session.scalar(
                select(Conversation.id).where(
                    Conversation.conversation_id == parsed_id,
                    Conversation.user_id == user_id,
                    Conversation.deleted == 0,
                )
            )
            if exists is None:
                return []
            rows = (
                await session.execute(
                    select(Message, MessageFeedback.vote)
                    .outerjoin(
                        MessageFeedback,
                        and_(
                            MessageFeedback.message_id == Message.id,
                            MessageFeedback.user_id == user_id,
                            MessageFeedback.deleted == 0,
                        ),
                    )
                    .where(
                        Message.conversation_id == parsed_id,
                        Message.user_id == user_id,
                        Message.deleted == 0,
                    )
                    .order_by(Message.create_time, Message.id)
                )
            ).all()
        return [
            self._message(message, vote if message.role == "assistant" else None)
            for message, vote in rows
        ]

    @staticmethod
    def _parse_id(value: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except ValueError as exc:
            raise ClientException("会话 ID 无效") from exc

    @staticmethod
    def _epoch_millis(value: datetime) -> int:
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return int(aware.timestamp() * 1000)

    @classmethod
    def _conversation(cls, row: Conversation) -> dict:
        last_time = row.last_time or row.update_time or row.create_time
        return {
            "conversationId": str(row.conversation_id),
            "title": (row.title or "").strip() or "新对话",
            "lastTime": cls._epoch_millis(last_time),
        }

    @classmethod
    def _message(cls, row: Message, vote: int | None) -> dict:
        return {
            "id": str(row.id),
            "conversationId": str(row.conversation_id),
            "role": row.role,
            "content": row.content,
            "thinkingContent": row.thinking_content,
            "thinkingDuration": row.thinking_duration,
            "vote": vote,
            "sources": row.sources,
            "recommendedQuestions": row.recommended_questions,
            "messageStatus": row.message_status,
            "createTime": cls._epoch_millis(row.create_time),
        }
