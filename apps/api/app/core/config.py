from functools import lru_cache
from pathlib import Path

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
    pitwall_model: str | None = Field(default=None, min_length=1, max_length=100)

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
