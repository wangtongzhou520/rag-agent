"""RAG 黄金集批次报告 ORM。"""

import uuid

from sqlalchemy import BigInteger, Boolean, Identity, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.framework.db import AuditMixin, Base
from app.framework.ids import new_native_uuid7


class EvalReport(AuditMixin, Base):
    """t_eval_report：保存批量评测摘要与逐题证据，不保存认证信息。"""

    __tablename__ = "t_eval_report"
    __table_args__ = (Index("idx_eval_report_time", "create_time"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, default=new_native_uuid7, unique=True, nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(128))
    dataset: Mapped[str] = mapped_column(String(255), nullable=False)
    collections: Mapped[list] = mapped_column(JSONB, nullable=False)
    include_answers: Mapped[bool] = mapped_column(Boolean, nullable=False)
    thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cases: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
