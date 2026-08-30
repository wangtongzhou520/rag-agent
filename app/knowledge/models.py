"""知识域 ORM 模型：知识库 / 文档 / chunk / 向量 / 分块日志。

表设计见 docs/03 §12；ID 策略见 docs/00 §5.5（chunkId 用 UUIDv7 跨存储对齐）。
向量维度部署级固定 1536（docs/03 §7），变更维度即变更迁移。
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
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

from app.framework.db import AuditMixin, Base
from app.framework.ids import new_native_uuid7

VECTOR_DIMENSION = 1536


class KnowledgeBase(AuditMixin, Base):
    """t_knowledge_base：知识库；collection_name 兼任向量分区键与对象存储目录名。"""

    __tablename__ = "t_knowledge_base"
    __table_args__ = (
        UniqueConstraint("collection_name", name="uk_collection_name"),
        Index("idx_kb_name", "name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    collection_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)


class KnowledgeDocument(AuditMixin, Base):
    """t_knowledge_document：文档；status 状态机 pending→running→success|failed。"""

    __tablename__ = "t_knowledge_document"
    __table_args__ = (Index("idx_kb_id", "kb_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    doc_name: Mapped[str] = mapped_column(String(256), nullable=False)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    file_url: Mapped[str | None] = mapped_column(String(1024))
    file_type: Mapped[str | None] = mapped_column(String(16))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    process_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="chunk"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_location: Mapped[str | None] = mapped_column(String(1024))
    schedule_enabled: Mapped[int | None] = mapped_column(SmallInteger)
    schedule_cron: Mapped[str | None] = mapped_column(String(64))
    ingestion_spec: Mapped[dict | None] = mapped_column(JSONB)
    pipeline_id: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)


class KnowledgeChunk(AuditMixin, Base):
    """t_knowledge_chunk：关系 chunk 表；向量在 t_knowledge_vector，不在此表。"""

    __tablename__ = "t_knowledge_chunk"
    __table_args__ = (Index("idx_doc_id", "doc_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=new_native_uuid7
    )
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    char_count: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    # 向量文本（章节路径+正文），重嵌入唯一正确来源
    embedding_text: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")


class KnowledgeVector(Base):
    """t_knowledge_vector：pgvector 向量表（HNSW + vector_cosine_ops）。"""

    __tablename__ = "t_knowledge_vector"
    __table_args__ = (
        Index("idx_kv_collection_name", "collection_name"),
        Index(
            "idx_kv_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    collection_name: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(VECTOR_DIMENSION))


class KnowledgeDocumentChunkLog(Base):
    """t_knowledge_document_chunk_log：分块执行日志，耗时毫秒分段。"""

    __tablename__ = "t_knowledge_document_chunk_log"
    __table_args__ = (Index("idx_chunk_log_doc_id", "doc_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    process_mode: Mapped[str | None] = mapped_column(String(16))
    parse_profile: Mapped[str | None] = mapped_column(String(16))
    pipeline_id: Mapped[int | None] = mapped_column(BigInteger)
    extract_duration: Mapped[int | None] = mapped_column(BigInteger)
    chunk_duration: Mapped[int | None] = mapped_column(BigInteger)
    embed_duration: Mapped[int | None] = mapped_column(BigInteger)
    persist_duration: Mapped[int | None] = mapped_column(BigInteger)
    total_duration: Mapped[int | None] = mapped_column(BigInteger)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[datetime | None] = mapped_column()
    end_time: Mapped[datetime | None] = mapped_column()
