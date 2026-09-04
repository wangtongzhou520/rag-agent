"""单次审计调用的快照上下文。"""

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any


@dataclass
class AuditState:
    biz_id: str = "UNKNOWN"
    before: Any = None
    after: Any = None
    skipped: bool = False
    name: str | None = None


_state: ContextVar[AuditState | None] = ContextVar("audit_state", default=None)


class AuditContext:
    @staticmethod
    def begin() -> Token[AuditState | None]:
        return _state.set(AuditState())

    @staticmethod
    def reset(token: Token[AuditState | None]) -> None:
        _state.reset(token)

    @staticmethod
    def current() -> AuditState:
        state = _state.get()
        if state is None:
            state = AuditState()
            _state.set(state)
        return state

    @classmethod
    def put(cls, biz_id: str | int, before: Any, after: Any) -> None:
        state = cls.current()
        state.biz_id = str(biz_id)[:64] or "UNKNOWN"
        state.before = before
        state.after = after

    @classmethod
    def skip(cls) -> None:
        cls.current().skipped = True

    @classmethod
    def put_name(cls, name: str) -> None:
        cls.current().name = name
