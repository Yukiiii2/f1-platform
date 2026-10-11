"""Independent bounded authentication admission, following the Pitwall lock pattern."""

from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.models import AuthUsage

NAMESPACE = 701120002


def limited(wait=5):
    return HTTPException(
        429,
        "Account requests are busy; try again shortly",
        headers={"Retry-After": str(wait)},
    )


@contextmanager
def permit(connection, settings, now=None):
    if connection.dialect.name != "postgresql":
        raise HTTPException(503, "Account service is temporarily unavailable")
    slot = None
    try:
        if not connection.scalar(select(func.pg_try_advisory_xact_lock(NAMESPACE, -1))):
            raise limited(1)
        if now is None:
            now = connection.scalar(select(func.extract("epoch", func.now())))
        minute = int(now) // 60
        table = AuthUsage.__table__
        row = (
            connection.execute(select(table).where(table.c.id == 1))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(503, "Account service is temporarily unavailable")
        count = row["minute_count"] if row["minute"] == minute else 0
        if count >= settings.auth_requests_per_minute:
            raise limited((minute + 1) * 60 - int(now))
        for candidate in range(settings.auth_max_concurrent):
            if connection.scalar(
                select(func.pg_try_advisory_lock(NAMESPACE, candidate))
            ):
                slot = candidate
                break
        if slot is None:
            raise limited()
        connection.execute(
            update(table)
            .where(table.c.id == 1)
            .values(minute=minute, minute_count=count + 1)
        )
        connection.commit()
        yield
    finally:
        connection.rollback()
        if slot is not None:
            try:
                connection.scalar(select(func.pg_advisory_unlock(NAMESPACE, slot)))
                connection.commit()
            except Exception:
                connection.invalidate()
                raise
