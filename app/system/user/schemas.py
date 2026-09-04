"""用户管理请求模型。"""

from pydantic import BaseModel, ConfigDict, Field


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str | None = None
    avatar: str | None = Field(default=None, max_length=1024)


class UserUpdateRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    role: str | None = None
    avatar: str | None = Field(default=None, max_length=1024)


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    current_password: str = Field(alias="currentPassword")
    new_password: str = Field(alias="newPassword")
