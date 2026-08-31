"""意图树 PostgreSQL 持久化模型。"""

from sqlalchemy import JSON, BigInteger, Identity, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.framework.db import AuditMixin, Base


class IntentNodeRecord(AuditMixin, Base):
    __tablename__ = "t_intent_node"
    __table_args__ = (Index("idx_intent_node_code", "intent_code"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kb_id: Mapped[int | None] = mapped_column(BigInteger)
    intent_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    parent_code: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    examples: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    collection_name: Mapped[str | None] = mapped_column(String(128))
    collection_names: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    kind: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    mcp_tool_id: Mapped[str | None] = mapped_column(String(256))
    top_k: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
