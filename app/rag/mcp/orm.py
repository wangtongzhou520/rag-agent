"""MCP Server 与 Tool 启停覆盖持久化。"""

from sqlalchemy import BigInteger, Identity, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.framework.db import AuditMixin, Base


class McpServerState(AuditMixin, Base):
    __tablename__ = "t_mcp_server_state"
    __table_args__ = (UniqueConstraint("server_name", name="uk_mcp_server_name"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    server_name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    create_by: Mapped[int | None] = mapped_column(BigInteger)
    update_by: Mapped[int | None] = mapped_column(BigInteger)


class McpToolState(AuditMixin, Base):
    __tablename__ = "t_mcp_tool_state"
    __table_args__ = (UniqueConstraint("tool_id", name="uk_mcp_tool_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tool_id: Mapped[str] = mapped_column(String(256), nullable=False)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    create_by: Mapped[int | None] = mapped_column(BigInteger)
    update_by: Mapped[int | None] = mapped_column(BigInteger)
