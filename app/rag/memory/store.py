"""会话记忆存储：SQLAlchemy async 直读 t_conversation / t_message（docs/01 §6）。"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.chat_types import ChatMessage, ChatRole
from app.rag.models import Conversation, Message


def normalize_history(
    messages: list[ChatMessage], keep_turns: int
) -> list[ChatMessage]:
    """历史归一化：只留 user/assistant，裁剪头部 assistant，保留最近 keep_turns 轮。

    TODO(M3)：assistant 历史内容须 CitationMarkup.strip 去掉行内引用角标（docs/01 §2.2）。
    """
    items = [m for m in messages if m.role in (ChatRole.USER, ChatRole.ASSISTANT)]
    while items and items[0].role is ChatRole.ASSISTANT:
        items.pop(0)
    if keep_turns > 0:
        items = items[-keep_turns * 2 :]
        while items and items[0].role is ChatRole.ASSISTANT:
            items.pop(0)
    return items


class ConversationMemoryStore:
    """t_conversation / t_message 的异步读写。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def get_or_create_conversation(
        self, conversation_id: uuid.UUID, user_id: int
    ) -> None:
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(Conversation.id).where(
                    Conversation.conversation_id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.deleted == 0,
                )
            )
            if existing is None:
                session.add(
                    Conversation(conversation_id=conversation_id, user_id=user_id)
                )
                await session.commit()

    async def load_history(
        self, conversation_id: uuid.UUID, user_id: int, keep_turns: int
    ) -> list[ChatMessage]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.user_id == user_id,
                        Message.deleted == 0,
                    )
                    .order_by(Message.create_time, Message.id)
                )
            ).all()
        history = [ChatMessage(role=ChatRole(row.role), content=row.content) for row in rows]
        return normalize_history(history, keep_turns)

    async def append_message(
        self,
        *,
        conversation_id: uuid.UUID,
        user_id: int,
        role: ChatRole,
        content: str,
        thinking_content: str | None = None,
        thinking_duration: int | None = None,
        sources: list | None = None,
        message_status: str = "NORMAL",
        reply_to_message_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """写入一条消息并刷新会话 last_time，返回预分配的 UUIDv7 消息 ID。"""
        async with self._session_factory() as session:
            message = Message(
                conversation_id=conversation_id,
                user_id=user_id,
                role=str(role),
                content=content,
                thinking_content=thinking_content,
                thinking_duration=thinking_duration,
                sources=sources,
                message_status=message_status,
                reply_to_message_id=reply_to_message_id,
            )
            session.add(message)
            await session.execute(
                update(Conversation)
                .where(
                    Conversation.conversation_id == conversation_id,
                    Conversation.user_id == user_id,
                )
                .values(last_time=func.now())
            )
            await session.commit()
            return message.id
