"""问答域表结构测试：锁定 docs/01 第 2 节的表设计，防止模型与迁移漂移。"""

import uuid

from sqlalchemy import BigInteger, Uuid
from sqlalchemy.dialects.postgresql import JSONB

import app.rag.models
from app.framework.db import Base

TABLES = ("t_conversation", "t_message", "t_conversation_summary", "t_message_feedback")
AUDIT_COLUMNS = {"create_time", "update_time", "deleted"}


def _columns(name: str) -> dict:
    return Base.metadata.tables[name].c


def test_all_tables_registered_with_audit_columns():
    for name in TABLES:
        assert name in Base.metadata.tables
        assert AUDIT_COLUMNS <= set(_columns(name).keys())


def test_conversation_structure():
    table = Base.metadata.tables["t_conversation"]
    assert isinstance(table.c.id.type, BigInteger)
    assert isinstance(table.c.conversation_id.type, Uuid)
    assert isinstance(table.c.user_id.type, BigInteger)
    assert table.c.title.type.length == 128

    uniques = {
        tuple(c.name for c in uc.columns)
        for uc in table.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("conversation_id", "user_id") in uniques

    index_cols = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("user_id", "last_time") in index_cols


def test_message_structure():
    table = Base.metadata.tables["t_message"]
    assert isinstance(table.c.id.type, Uuid)
    assert table.primary_key.columns.keys() == ["id"]
    for col in ("sources", "recommended_questions", "retrieved_chunks"):
        assert isinstance(table.c[col].type, JSONB)
    assert table.c.message_status.server_default.arg == "NORMAL"

    index_cols = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("conversation_id", "user_id", "create_time") in index_cols


def test_message_id_default_is_uuid7():
    message = app.rag.models.Message.__dict__["id"]
    default = message.default.arg
    value = default(None)
    assert uuid.UUID(str(value)).version == 7


def test_summary_structure():
    table = Base.metadata.tables["t_conversation_summary"]
    assert isinstance(table.c.last_message_id.type, Uuid)

    index_cols = {tuple(c.name for c in idx.columns) for idx in table.indexes}
    assert ("conversation_id", "user_id") in index_cols


def test_feedback_structure():
    table = Base.metadata.tables["t_message_feedback"]
    uniques = {
        tuple(c.name for c in uc.columns)
        for uc in table.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("message_id", "user_id") in uniques
    assert table.c.reason.type.length == 255
    assert table.c.comment.type.length == 1024
