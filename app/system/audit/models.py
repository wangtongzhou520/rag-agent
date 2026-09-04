"""业务变更审计 ORM。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Identity, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.framework.db import Base


class BizChangeLog(Base):
    __tablename__ = "t_biz_change_log"
    __table_args__ = (
        Index("idx_biz_change_type_id", "biz_type", "biz_id"),
        Index("idx_biz_change_time", "create_time"),
        Index("idx_biz_change_operator", "operator_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    biz_type: Mapped[str] = mapped_column(String(64), nullable=False)
    biz_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UNKNOWN")
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action_desc: Mapped[str] = mapped_column(String(512), nullable=False)
    before_snapshot: Mapped[dict | list | None] = mapped_column(JSONB)
    after_snapshot: Mapped[dict | list | None] = mapped_column(JSONB)
    change_diff: Mapped[list | None] = mapped_column(JSONB)
    operator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_name: Mapped[str | None] = mapped_column(String(128))
    operator_role: Mapped[str | None] = mapped_column(String(64))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    class_name: Mapped[str] = mapped_column(String(255), nullable=False)
    method_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
