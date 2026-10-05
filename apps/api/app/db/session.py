from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def get_database_url() -> URL:
    configured = get_settings().database_url
    if configured is None:
        raise RuntimeError("DATABASE_URL must be configured for database operations")
    return make_url(str(configured)).set(drivername="postgresql+psycopg")


@lru_cache
def get_engine() -> Engine:
    # No connection is opened at import time or during the liveness check.
    return create_engine(get_database_url(), pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    # Callers commit explicitly; closing rolls back unfinished transactions.
    with get_session_factory()() as session:
        yield session
