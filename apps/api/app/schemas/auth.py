from pydantic import ConfigDict, Field, SecretStr, field_validator

from app.schemas.domain import ReadFields, Schema


class LoginRequest(Schema):
    # Domain text is normally trimmed; credentials must be preserved exactly.
    model_config = ConfigDict(str_strip_whitespace=False)
    username: str = Field(
        min_length=3, max_length=32, pattern=r"^[a-z0-9][a-z0-9_.-]{2,31}$"
    )
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalized(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RegisterRequest(LoginRequest):
    password: SecretStr = Field(min_length=12, max_length=128)


class UserRead(ReadFields):
    username: str
