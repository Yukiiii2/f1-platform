import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: PostgresDsn | None = Field(default=None, repr=False)
    openf1_username: SecretStr | None = Field(default=None, repr=False)
    openf1_password: SecretStr | None = Field(default=None, repr=False)
    session_live_poll_seconds: int = Field(default=60, ge=60, le=300)
    saved_comparisons_owner_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    auth_cookie_secure: bool = False
    auth_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    auth_session_hours: int = Field(default=12, ge=1, le=168)
    auth_requests_per_minute: int = Field(default=20, ge=1, le=100)
    auth_max_concurrent: int = Field(default=2, ge=1, le=4)

    @field_validator("auth_allowed_origins")
    @classmethod
    def browser_origins(cls, value):
        from urllib.parse import urlsplit

        values = [item.strip() for item in value.split(",") if item.strip()]
        for origin in values:
            parts = urlsplit(origin)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.path
                or parts.query
                or parts.fragment
            ):
                raise ValueError(
                    "Use comma-separated HTTP(S) browser origins without paths"
                )
        if not values:
            raise ValueError("At least one browser origin is required")
        return ",".join(dict.fromkeys(values))

    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    gemini_api_key: SecretStr | None = Field(default=None, repr=False)
    pitwall_provider: Literal["openai", "gemini"] = "openai"
    pitwall_model: str | None = Field(default=None, min_length=1, max_length=100)
    pitwall_fallback_models: str = Field(default="", max_length=305)
    pitwall_max_retries: int = Field(default=1, ge=0, le=2)
    pitwall_requests_per_minute: int = Field(default=10, ge=1, le=100)
    pitwall_requests_per_day: int = Field(default=100, ge=1, le=10000)
    pitwall_max_concurrent: int = Field(default=2, ge=1, le=8)

    @field_validator("pitwall_max_retries", mode="before")
    @classmethod
    def optional_retries(cls, value):
        return 1 if isinstance(value, str) and not value.strip() else value

    @field_validator("pitwall_fallback_models")
    @classmethod
    def ordered_models(cls, value):
        models = list(
            dict.fromkeys(model.strip() for model in value.split(",") if model.strip())
        )
        if len(models) > 3 or any(
            not re.fullmatch(r"gemini-[a-z0-9.-]{1,90}", model) for model in models
        ):
            raise ValueError("Use up to three comma-separated Gemini model IDs")
        return ",".join(models)

    @field_validator("pitwall_provider", mode="before")
    @classmethod
    def optional_provider(cls, value):
        return value.strip().lower() or "openai" if isinstance(value, str) else value

    @field_validator("pitwall_model", mode="before")
    @classmethod
    def optional_model(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("database_url")
    @classmethod
    def supported_driver(cls, value: PostgresDsn | None) -> PostgresDsn | None:
        if value is not None and value.scheme not in {
            "postgres",
            "postgresql",
            "postgresql+psycopg",
        }:
            raise ValueError("DATABASE_URL must use PostgreSQL with psycopg")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
