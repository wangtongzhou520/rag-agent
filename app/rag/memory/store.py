"""会话记忆存储：SQLAlchemy async 直读 t_conversation / t_message（docs/01 §6）。"""

import uuid

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.chat_types import ChatMessage, ChatRole
from app.rag.models import Conversation, ConversationSummary, Message
from app.rag.source.citation import strip_citations


def normalize_history(
    messages: list[ChatMessage], keep_turns: int
) -> list[ChatMessage]:
    """只留 user/assistant，去引用角标并保留最近 keep_turns 轮。"""
    items = [
        ChatMessage(
            role=m.role,
            content=strip_citations(m.content)
            if m.role is ChatRole.ASSISTANT
            else m.content,
        )
        for m in messages
        if m.role in (ChatRole.USER, ChatRole.ASSISTANT)
    ]
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
                select(Conversation).where(
                    Conversation.conversation_id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            if existing is None:
                session.add(
                    Conversation(conversation_id=conversation_id, user_id=user_id)
                )
                await session.commit()
            elif existing.deleted:
                raise ValueError("conversation has been deleted")

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

    async def load_summary(
        self, conversation_id: uuid.UUID, user_id: int
    ) -> str | None:
        async with self._session_factory() as session:
            return await session.scalar(
                select(ConversationSummary.content)
                .where(
                    ConversationSummary.conversation_id == conversation_id,
                    ConversationSummary.user_id == user_id,
                    ConversationSummary.deleted == 0,
                )
                .order_by(ConversationSummary.update_time.desc())
                .limit(1)
            )

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
            conversation_exists = await session.scalar(
                select(Conversation.id).where(
                    Conversation.conversation_id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.deleted == 0,
                )
            )
            if conversation_exists is None:
                raise ValueError("conversation does not exist or has been deleted")
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
            values: dict = {"last_time": func.now()}
            if role == ChatRole.USER:
                values["title"] = case(
                    (
                        Conversation.title.is_(None),
                        content.strip()[:30] or "新对话",
                    ),
                    else_=Conversation.title,
                )
            await session.execute(
                update(Conversation)
                .where(
                    Conversation.conversation_id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.deleted == 0,
                )
                .values(**values)
            )
            await session.commit()
            return message.id
