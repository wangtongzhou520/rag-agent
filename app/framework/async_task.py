"""自研 PG 任务队列的 ORM 模型（docs/03 §11.2）。

``t_async_task`` 表即队列：入队 = 业务事务内 INSERT，领取 = FOR UPDATE SKIP LOCKED
原子 claim，活跃任务由部分唯一索引 uk_async_task_active 防重。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Identity,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.framework.db import AuditMixin, Base


class AsyncTask(AuditMixin, Base):
    __tablename__ = "t_async_task"
    __table_args__ = (
        Index(
            "uk_async_task_active",
            "task_type",
            "biz_key",
            unique=True,
            # 活跃任务唯一：终态历史行不阻止重投
            postgresql_where=text("status IN ('pending','running')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    biz_key: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    owner: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column()
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    next_retry_at: Mapped[datetime | None] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text)
