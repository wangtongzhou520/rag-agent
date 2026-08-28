"""SQLAlchemy 2.0 声明式基类、公共审计列与启动期自动建表。

新项目起步不做版本化迁移：``init_schema`` 在启动时幂等执行
``CREATE EXTENSION IF NOT EXISTS vector`` + ``Base.metadata.create_all``。
"""

from datetime import datetime

from sqlalchemy import DateTime, SmallInteger, func, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditMixin:
    """常规审计与软删列；deleted 取值 0/1。"""

    create_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)


async def init_schema(engine: AsyncEngine) -> None:
    """幂等建表：先启用 pgvector 扩展，再按元数据 create_all（checkfirst）。

    调用前须确保各域模型已导入（t_* 表注册到 Base.metadata）。
    """
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)
