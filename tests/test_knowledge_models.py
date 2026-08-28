"""知识域与任务队列表结构测试（docs/03 §12/§11.2）。"""

import app.knowledge.models  # noqa: F401 导入即注册元数据
from app.framework.async_task import AsyncTask  # noqa: F401
from app.framework.db import Base

TABLES = (
    "t_knowledge_base",
    "t_knowledge_document",
    "t_knowledge_chunk",
    "t_knowledge_vector",
    "t_knowledge_document_chunk_log",
    "t_async_task",
)


def test_all_tables_registered() -> None:
    for name in TABLES:
        assert name in Base.metadata.tables


def test_knowledge_base_unique_collection_name() -> None:
    table = Base.metadata.tables["t_knowledge_base"]
    uniques = {
        tuple(c.name for c in uc.columns)
        for uc in table.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("collection_name",) in uniques
    index_cols = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("name",) in index_cols


def test_knowledge_vector_partition_and_embedding() -> None:
    table = Base.metadata.tables["t_knowledge_vector"]
    assert "collection_name" in table.c
    assert "metadata" in table.c
    embedding_type = table.c.embedding.type
    assert getattr(embedding_type, "dim", None) == 1536
    index_cols = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("collection_name",) in index_cols


def test_chunk_uuid_pk_and_embedding_text() -> None:
    table = Base.metadata.tables["t_knowledge_chunk"]
    assert table.primary_key.columns.keys() == ["id"]
    assert "embedding_text" in table.c
    index_cols = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("doc_id",) in index_cols


def test_async_task_active_partial_unique_index() -> None:
    table = Base.metadata.tables["t_async_task"]
    partial = {
        idx.name: idx
        for idx in table.indexes
        if idx.unique and idx.dialect_options["postgresql"].get("where") is not None
    }
    assert "uk_async_task_active" in partial
    where = str(partial["uk_async_task_active"].dialect_options["postgresql"]["where"])
    assert "pending" in where and "running" in where
    assert table.c.event_id.unique
