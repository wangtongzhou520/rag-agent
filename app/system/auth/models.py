"""认证请求和当前用户类型。"""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginUser(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: int = Field(alias="userId")
    username: str
    role: str
    avatar: str | None = None


class LoginVO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: int = Field(alias="userId")
    role: str
    token: str
    avatar: str | None = None
