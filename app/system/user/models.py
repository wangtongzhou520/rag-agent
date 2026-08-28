"""系统用户 ORM。"""

from sqlalchemy import BigInteger, Identity, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.framework.db import AuditMixin, Base


class User(AuditMixin, Base):
    __tablename__ = "t_user"
    __table_args__ = (Index("uk_user_username", "username", unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="USER")
    avatar: Mapped[str | None] = mapped_column(String(1024))
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
