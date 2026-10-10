"""Shared admission counters, with no questions, client identities or secrets."""

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PitwallUsage(Base):
    __tablename__ = "pitwall_usage"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            "minute_count >= 0 AND day_count >= 0", name="nonnegative_usage"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    minute: Mapped[int]
    minute_count: Mapped[int]
    day: Mapped[int]
    day_count: Mapped[int]
