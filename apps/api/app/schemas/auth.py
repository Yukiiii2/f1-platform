from typing import Literal

from pydantic import AwareDatetime, ConfigDict, Field, SecretStr, field_validator

from app.schemas.domain import ReadFields, Schema


class UsernameRequest(Schema):
    # Domain text is normally trimmed; credentials must be preserved exactly.
    model_config = ConfigDict(str_strip_whitespace=False)
    username: str = Field(
        min_length=3, max_length=32, pattern=r"^[a-z0-9][a-z0-9_.-]{2,31}$"
    )

    @field_validator("username", mode="before")
    @classmethod
    def normalized(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class LoginRequest(UsernameRequest):
    password: SecretStr = Field(min_length=1, max_length=128)


class RegisterRequest(LoginRequest):
    password: SecretStr = Field(min_length=12, max_length=128)


class UserRead(ReadFields):
    username: str


class CurrentPasswordRequest(Schema):
    model_config = ConfigDict(str_strip_whitespace=False)
    current_password: SecretStr = Field(min_length=1, max_length=128)


class PasswordChange(CurrentPasswordRequest):
    new_password: SecretStr = Field(min_length=12, max_length=128)


class AccountDelete(CurrentPasswordRequest):
    confirmation: Literal["DELETE"]


class AccountSessionRead(Schema):
    created_at: AwareDatetime
    expires_at: AwareDatetime
    is_current: bool


class AccountRead(UserRead):
    saved_comparison_count: int
    sessions: list[AccountSessionRead]
