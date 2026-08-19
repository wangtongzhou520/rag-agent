"""请求与 Trace 上下文；完整 RAG 节点树在后续里程碑接入。"""

from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(request_id: str) -> Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


# TODO(M4): 扩展 trace_id / task_id / 不可变 node_stack 与节点装饰器
