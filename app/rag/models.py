"""问答域 ORM 模型：会话 / 消息 / 摘要 / 反馈。

表设计见 docs/01 第 2 节；ID 策略见 docs/00 §5.5：
DB 内部主键用 BIGINT IDENTITY，对外/预分配业务标识用 UUIDv7（原生 UUID 类型）。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from uuid_utils import uuid7

from app.framework.db import AuditMixin, Base


class Conversation(AuditMixin, Base):
    """t_conversation：会话。"""

    __tablename__ = "t_conversation"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_conv_user"),
        Index("idx_user_time", "user_id", "last_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(128))
    last_time: Mapped[datetime | None] = mapped_column()


class Message(AuditMixin, Base):
    """t_message：会话消息；UUIDv7 主键，落库前预分配，兼作摘要游标。"""

    __tablename__ = "t_message"
    __table_args__ = (
        Index("idx_conversation_user_time", "conversation_id", "user_id", "create_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    thinking_content: Mapped[str | None] = mapped_column(Text)
    thinking_duration: Mapped[int | None] = mapped_column(Integer)
    sources: Mapped[list | None] = mapped_column(JSONB)
    recommended_questions: Mapped[list | None] = mapped_column(JSONB)
    retrieved_chunks: Mapped[list | None] = mapped_column(JSONB)
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    message_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="NORMAL"
    )


class ConversationSummary(AuditMixin, Base):
    """t_conversation_summary：会话摘要，last_message_id 为 UUIDv7 游标。"""

    __tablename__ = "t_conversation_summary"
    __table_args__ = (Index("idx_conv_user", "conversation_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_message_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class MessageFeedback(AuditMixin, Base):
    """t_message_feedback：消息反馈，(message_id, user_id) 为 upsert 冲突键。"""

    __tablename__ = "t_message_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_feedback_msg_user"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    vote: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(String(1024))
