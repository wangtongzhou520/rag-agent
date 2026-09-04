"""用户角色。"""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"

    @classmethod
    def normalize(cls, value: str | None) -> "UserRole":
        normalized = (value or cls.USER.value).strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError("角色类型不合法") from exc
