import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: PostgresDsn | None = Field(default=None, repr=False)
    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    gemini_api_key: SecretStr | None = Field(default=None, repr=False)
    pitwall_provider: Literal["openai", "gemini"] = "openai"
    pitwall_model: str | None = Field(default=None, min_length=1, max_length=100)
    pitwall_fallback_models: str = Field(default="", max_length=305)
    pitwall_max_retries: int = Field(default=1, ge=0, le=2)

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
