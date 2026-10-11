"""First-party identities and revocable opaque sessions, separate from F1 data."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity


class User(Entity, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("username = lower(username)", name="normalized_name"),
    )
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class AuthSession(Entity, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_created", "user_id", "created_at"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthUsage(Base):
    __tablename__ = "auth_usage"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("minute_count >= 0", name="nonnegative_usage"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    minute: Mapped[int]
    minute_count: Mapped[int]
