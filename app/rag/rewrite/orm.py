"""查询词映射 ORM 表。"""

from sqlalchemy import BigInteger, Identity, Index, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.framework.db import AuditMixin, Base


class QueryTermMappingRecord(AuditMixin, Base):
    __tablename__ = "t_query_term_mapping"
    __table_args__ = (Index("idx_query_mapping_source", "source_term"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    domain: Mapped[str | None] = mapped_column(String(64))
    source_term: Mapped[str] = mapped_column(String(128), nullable=False)
    target_term: Mapped[str] = mapped_column(String(128), nullable=False)
    match_type: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="1"
    )
    priority: Mapped[int | None] = mapped_column(Integer, server_default="100")
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    remark: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
