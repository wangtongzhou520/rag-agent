"""会话记忆服务：加载降级为空、追加失败不阻断（docs/01 §13 异常与降级）。

TODO(M1 后续增量)：摘要并行加载与 attachSummary（docs/01 §6/§7）。
"""

import uuid

from app.framework.chat_types import ChatMessage, ChatRole
from app.framework.logging import get_logger
from app.rag.memory.store import ConversationMemoryStore

logger = get_logger(__name__)


class ConversationMemoryService:
    """对外记忆入口；所有 DB 异常只记日志，不影响问答主流程。"""

    def __init__(self, store: ConversationMemoryStore, history_keep_turns: int = 8) -> None:
        self._store = store
        self._history_keep_turns = history_keep_turns

    async def load(self, conversation_id: str, user_id: int) -> list[ChatMessage]:
        """加载历史（不含本次问题）；任何异常降级为空历史。"""
        try:
            conv_id = uuid.UUID(conversation_id)
            await self._store.get_or_create_conversation(conv_id, user_id)
            return await self._store.load_history(
                conv_id, user_id, self._history_keep_turns
            )
        except Exception:
            logger.exception(
                "记忆加载失败，降级为空历史", conversation_id=conversation_id
            )
            return []

    async def append_user_message(
        self, conversation_id: str, user_id: int, content: str
    ) -> str | None:
        """追加 user 消息，返回消息 ID；失败只记日志返回 None。"""
        try:
            message_id = await self._store.append_message(
                conversation_id=uuid.UUID(conversation_id),
                user_id=user_id,
                role=ChatRole.USER,
                content=content,
            )
            return str(message_id)
        except Exception:
            logger.exception("user 消息落库失败", conversation_id=conversation_id)
            return None

    async def append_assistant_message(
        self,
        conversation_id: str,
        user_id: int,
        content: str,
        *,
        thinking_content: str | None = None,
        thinking_duration: int | None = None,
        sources: list | None = None,
        message_status: str = "NORMAL",
        reply_to_message_id: str | None = None,
    ) -> str | None:
        """追加 assistant 消息；失败只记日志返回 None（不阻断流，docs/01 §13）。"""
        try:
            message_id = await self._store.append_message(
                conversation_id=uuid.UUID(conversation_id),
                user_id=user_id,
                role=ChatRole.ASSISTANT,
                content=content,
                thinking_content=thinking_content,
                thinking_duration=thinking_duration,
                sources=sources,
                message_status=message_status,
                reply_to_message_id=(
                    uuid.UUID(reply_to_message_id) if reply_to_message_id else None
                ),
            )
            return str(message_id)
        except Exception:
            logger.exception("assistant 消息落库失败", conversation_id=conversation_id)
            return None
