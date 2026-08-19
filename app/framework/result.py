"""Result<T> 统一包装与稳定字符串错误码。"""

from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.framework.trace_ctx import get_request_id

T = TypeVar("T")


class ErrorCode(StrEnum):
    """错误码骨架，领域错误码后续按模块细分。"""

    SUCCESS = "0"
    PARAM_ERROR = "40000"
    UNAUTHORIZED = "40100"
    FORBIDDEN = "40300"
    NOT_FOUND = "40400"
    RATE_LIMITED = "42900"
    SERVICE_ERROR = "50000"
    REMOTE_ERROR = "50001"


class Result[T](BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    data: T | None = None
    request_id: str | None = Field(default=None, alias="requestId")


class Results:
    @staticmethod
    def success(data: T | None = None, message: str = "ok") -> Result[T]:
        return Result(
            code=ErrorCode.SUCCESS,
            message=message,
            data=data,
            request_id=get_request_id(),
        )

    @staticmethod
    def error(code: str | ErrorCode, message: str = "") -> Result[None]:
        return Result(
            code=str(code),
            message=message,
            data=None,
            request_id=get_request_id(),
        )
