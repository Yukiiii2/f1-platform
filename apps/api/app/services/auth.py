"""Argon2id credentials and short, revocable sessions; never return a token in JSON."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select

from app import models

COOKIE_NAME = "f1_session"
hasher = PasswordHasher()


@lru_cache(maxsize=1)
def dummy_hash():
    return hasher.hash(secrets.token_urlsafe(32))


def verify_password(user, password):
    try:
        matched = hasher.verify(user.password_hash if user else dummy_hash(), password)
        return bool(user and matched)
    except (VerificationError, InvalidHashError):
        return False


def token_hash(token):
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def issue_session(db, user, old_token, settings):
    # Serialize a user's session cap, including simultaneous logins.
    db.scalar(select(models.User.id).where(models.User.id == user.id).with_for_update())
    old_hash = token_hash(old_token)
    if old_hash:
        db.execute(
            delete(models.AuthSession).where(models.AuthSession.token_hash == old_hash)
        )
    now = datetime.now(timezone.utc)
    db.execute(
        delete(models.AuthSession).where(
            models.AuthSession.user_id == user.id, models.AuthSession.expires_at <= now
        )
    )
    existing = db.scalars(
        select(models.AuthSession.id)
        .where(models.AuthSession.user_id == user.id)
        .order_by(models.AuthSession.created_at.desc(), models.AuthSession.id)
    ).all()
    if len(existing) >= 5:
        db.execute(
            delete(models.AuthSession).where(models.AuthSession.id.in_(existing[4:]))
        )
    token = secrets.token_urlsafe(32)
    db.add(
        models.AuthSession(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=now + timedelta(hours=settings.auth_session_hours),
        )
    )
    db.commit()
    return token


def session_user(db, token):
    hashed = token_hash(token)
    if hashed is None:
        return None
    return db.scalar(
        select(models.User)
        .join(models.AuthSession, models.AuthSession.user_id == models.User.id)
        .where(
            models.AuthSession.token_hash == hashed,
            models.AuthSession.expires_at > datetime.now(timezone.utc),
        )
    )
