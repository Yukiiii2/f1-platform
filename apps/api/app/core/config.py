from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: PostgresDsn | None = Field(default=None, repr=False)

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
