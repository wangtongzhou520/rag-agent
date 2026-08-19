"""三层业务异常：客户端错误 / 服务内部错误 / 下游远程错误。"""

from app.framework.result import ErrorCode


class BizException(Exception):
    """业务异常基类，携带错误码与消息。"""

    def __init__(self, code: str | ErrorCode, message: str = "") -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = message or self.__class__.__name__


class ClientException(BizException):
    """客户端错误（参数非法、未认证、越权、超限等）。"""

    def __init__(self, message: str = "", code: str | ErrorCode = ErrorCode.PARAM_ERROR) -> None:
        super().__init__(code, message)


class ServiceException(BizException):
    """服务内部错误。"""

    def __init__(self, message: str = "", code: str | ErrorCode = ErrorCode.SERVICE_ERROR) -> None:
        super().__init__(code, message)


class RemoteException(BizException):
    """下游远程调用错误（LLM 供应商、MCP、ES、LightRAG 等）。"""

    def __init__(self, message: str = "", code: str | ErrorCode = ErrorCode.REMOTE_ERROR) -> None:
        super().__init__(code, message)
