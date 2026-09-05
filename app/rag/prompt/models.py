"""Agent Profile 与 Prompt Slot 持久化模型。"""

from sqlalchemy import (
    BigInteger,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.framework.db import AuditMixin, Base


class AgentProfile(AuditMixin, Base):
    __tablename__ = "t_agent_profile"
    __table_args__ = (
        UniqueConstraint("name", name="uk_agent_name"),
        Index(
            "uk_agent_active",
            "active",
            unique=True,
            postgresql_where=text("active = 1 AND deleted = 0"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    avatar: Mapped[str | None] = mapped_column(String(32))
    builtin: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    active: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    create_by: Mapped[int | None] = mapped_column(BigInteger)
    update_by: Mapped[int | None] = mapped_column(BigInteger)


class AgentPrompt(AuditMixin, Base):
    __tablename__ = "t_agent_prompt"
    __table_args__ = (
        UniqueConstraint("agent_id", "slot_key", name="uk_agent_slot"),
        Index("idx_agent_prompt_agent", "agent_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    slot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    create_by: Mapped[int | None] = mapped_column(BigInteger)
    update_by: Mapped[int | None] = mapped_column(BigInteger)
