"""First-party cookie sessions. Public F1 APIs require no authentication."""

from datetime import timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import models
from app.api.core import Database
from app.core.config import get_settings
from app.db.session import get_engine
from app.schemas.auth import LoginRequest, RegisterRequest, UserRead
from app.services.auth import (
    COOKIE_NAME,
    hasher,
    issue_session,
    session_user,
    token_hash,
    verify_password,
)
from app.services.auth_protection import permit

router = APIRouter(prefix="/auth", tags=["accounts"])


def unsafe_request(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    settings = get_settings()
    origin = request.headers.get("origin")
    # A custom header forces browser preflight; the API enables no cross-origin CORS.
    if request.headers.get("x-f1-auth") != "1" or (
        origin is not None and origin not in settings.auth_allowed_origins.split(",")
    ):
        raise HTTPException(403, "Account request could not be verified")


def admission(request: Request):
    unsafe_request(request)
    try:
        with get_engine().connect() as connection:
            with permit(connection, get_settings()):
                yield
    except (RuntimeError, SQLAlchemyError) as error:
        raise HTTPException(
            503, "Account service is temporarily unavailable"
        ) from error


def authenticated_owner(db: Database, request: Request, response: Response) -> UUID:
    response.headers["Cache-Control"] = "no-store"
    unsafe_request(request)
    user = session_user(db, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(
            401,
            "Sign in to access saved comparisons",
            headers={"Cache-Control": "no-store"},
        )
    return user.id


def public_user(user):
    def aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    return UserRead(
        id=user.id,
        username=user.username,
        created_at=aware(user.created_at),
        updated_at=aware(user.updated_at),
    )


def cookie(response, token):
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.auth_session_hours * 3600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


@router.post(
    "/register",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(admission)],
)
def register(
    db: Database, request: RegisterRequest, response: Response, incoming: Request
):
    # Hash on conflicts too; never reveal existing account details or log credentials.
    user = models.User(
        username=request.username,
        password_hash=hasher.hash(request.password.get_secret_value()),
    )
    try:
        db.add(user)
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            409, "Unable to create an account with these details"
        ) from error
    cookie(
        response,
        issue_session(db, user, incoming.cookies.get(COOKIE_NAME), get_settings()),
    )
    return public_user(user)


@router.post("/login", response_model=UserRead, dependencies=[Depends(admission)])
def login(db: Database, request: LoginRequest, response: Response, incoming: Request):
    user = db.scalar(
        select(models.User).where(models.User.username == request.username)
    )
    password = request.password.get_secret_value()
    if not verify_password(user, password):
        raise HTTPException(401, "Sign-in name or password is incorrect")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(password)
    cookie(
        response,
        issue_session(db, user, incoming.cookies.get(COOKIE_NAME), get_settings()),
    )
    return public_user(user)


@router.post("/logout", status_code=204, dependencies=[Depends(unsafe_request)])
def logout(db: Database, request: Request):
    hashed = token_hash(request.cookies.get(COOKIE_NAME))
    if hashed:
        db.execute(
            delete(models.AuthSession).where(models.AuthSession.token_hash == hashed)
        )
        db.commit()
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        secure=get_settings().auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me", response_model=UserRead)
def me(db: Database, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    user = session_user(db, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(401, "Sign in to view your account")
    return public_user(user)
