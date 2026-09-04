"""可编排入库 Pipeline、同步任务与节点日志表。"""

from datetime import datetime

from sqlalchemy import BigInteger, Identity, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.framework.db import AuditMixin, Base


class IngestionPipeline(AuditMixin, Base):
    __tablename__ = "t_ingestion_pipeline"
    __table_args__ = (UniqueConstraint("name", name="uk_ingestion_pipeline_name"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)


class IngestionPipelineNode(AuditMixin, Base):
    __tablename__ = "t_ingestion_pipeline_node"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "node_id", name="uk_ingestion_pipeline_node"),
        Index("idx_ingestion_pipeline_node_pipeline", "pipeline_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)
    next_node_id: Mapped[str | None] = mapped_column(String(64))
    settings_json: Mapped[dict | None] = mapped_column(JSONB)
    condition_json: Mapped[dict | str | bool | None] = mapped_column(JSONB)


class IngestionTask(AuditMixin, Base):
    __tablename__ = "t_ingestion_task"
    __table_args__ = (
        Index("idx_ingestion_task_pipeline", "pipeline_id"),
        Index("idx_ingestion_task_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_location: Mapped[str | None] = mapped_column(String(1024))
    source_file_name: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    logs_json: Mapped[list | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class IngestionTaskNode(AuditMixin, Base):
    __tablename__ = "t_ingestion_task_node"
    __table_args__ = (Index("idx_ingestion_task_node_task", "task_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pipeline_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)
    node_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    message: Mapped[str | None] = mapped_column(String(512))
    error_message: Mapped[str | None] = mapped_column(Text)
    output_json: Mapped[str | None] = mapped_column(Text)
