"""Cross-process admission limits; held connections own concurrency slots.

PostgreSQL releases advisory locks on disconnect, including process crashes.
No expiring lease can admit extra requests while a slow model call still runs.
"""

from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.models import PitwallUsage

LOCK_NAMESPACE = 701120001


def busy(retry_after):
    return HTTPException(
        status_code=429,
        detail="Pitwall is busy; please try again later",
        headers={"Retry-After": str(retry_after)},
    )


@contextmanager
def permit(connection, settings, *, now=None):
    """Debit admitted queries (including failures); rejection spends no budget."""
    if connection.dialect.name != "postgresql":
        raise HTTPException(503, "Pitwall is temporarily unavailable")
    slot = None
    try:
        # Nonblocking serialization avoids piling up public requests on a row lock.
        if not connection.scalar(
            select(func.pg_try_advisory_xact_lock(LOCK_NAMESPACE, -1))
        ):
            raise busy(1)
        if now is None:
            now = connection.scalar(select(func.extract("epoch", func.now())))
        now = int(now)
        minute, day = now // 60, now // 86400
        table = PitwallUsage.__table__
        row = (
            connection.execute(select(table).where(table.c.id == 1))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(503, "Pitwall is temporarily unavailable")
        minute_count = row["minute_count"] if row["minute"] == minute else 0
        day_count = row["day_count"] if row["day"] == day else 0
        if day_count >= settings.pitwall_requests_per_day:
            raise busy((day + 1) * 86400 - now)
        if minute_count >= settings.pitwall_requests_per_minute:
            raise busy((minute + 1) * 60 - now)
        for candidate in range(settings.pitwall_max_concurrent):
            if connection.scalar(
                select(func.pg_try_advisory_lock(LOCK_NAMESPACE, candidate))
            ):
                slot = candidate
                break
        if slot is None:
            raise busy(5)
        connection.execute(
            update(table)
            .where(table.c.id == 1)
            .values(
                minute=minute,
                minute_count=minute_count + 1,
                day=day,
                day_count=day_count + 1,
            )
        )
        connection.commit()
        yield
    finally:
        connection.rollback()
        if slot is not None:
            try:
                connection.scalar(select(func.pg_advisory_unlock(LOCK_NAMESPACE, slot)))
                connection.commit()
            except Exception:
                # Never return a potentially locked physical connection to the pool.
                connection.invalidate()
                raise
