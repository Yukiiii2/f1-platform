"""First-party cookie sessions. Public F1 APIs require no authentication."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import models
from app.api.core import Database
from app.core.config import get_settings
from app.db.session import get_engine
from app.schemas.auth import (
    AccountDelete,
    AccountRead,
    AccountSessionRead,
    LoginRequest,
    PasswordChange,
    RegisterRequest,
    UsernameRequest,
    UserRead,
)
from app.services.auth import (
    COOKIE_NAME,
    hasher,
    issue_session,
    locked_session_user,
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
        select(models.User)
        .where(models.User.username == request.username)
        .with_for_update()
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
    if hashed and locked_session_user(db, request.cookies.get(COOKIE_NAME)) is not None:
        db.execute(
            delete(models.AuthSession).where(models.AuthSession.token_hash == hashed)
        )
        db.commit()
    return cleared_session_response()


def cleared_session_response():
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


def account_user(db, incoming, response, *, lock=False):
    response.headers["Cache-Control"] = "no-store"
    token = incoming.cookies.get(COOKIE_NAME)
    user = locked_session_user(db, token) if lock else session_user(db, token)
    if user is None:
        raise HTTPException(
            401, "Sign in to manage your account", headers={"Cache-Control": "no-store"}
        )
    return user


@router.get("/account", response_model=AccountRead)
def account(db: Database, incoming: Request, response: Response):
    user = account_user(db, incoming, response)
    current_hash = token_hash(incoming.cookies.get(COOKIE_NAME))
    sessions = db.scalars(
        select(models.AuthSession)
        .where(
            models.AuthSession.user_id == user.id,
            models.AuthSession.expires_at > datetime.now(timezone.utc),
        )
        .order_by(models.AuthSession.created_at.desc(), models.AuthSession.id)
        .limit(5)
    ).all()
    count = db.scalar(
        select(func.count())
        .select_from(models.SavedComparison)
        .where(models.SavedComparison.user_id == user.id)
    )
    return AccountRead(
        **public_user(user).model_dump(),
        saved_comparison_count=count,
        sessions=[
            AccountSessionRead(
                created_at=row.created_at,
                expires_at=row.expires_at,
                is_current=row.token_hash == current_hash,
            )
            for row in sessions
        ],
    )


@router.patch("/username", response_model=UserRead, dependencies=[Depends(admission)])
def change_username(
    db: Database, incoming: Request, response: Response, request: UsernameRequest
):
    user = account_user(db, incoming, response, lock=True)
    user.username = request.username
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            409,
            "This sign-in name is unavailable",
            headers={"Cache-Control": "no-store"},
        ) from error
    return public_user(user)


def require_current_password(user, request):
    if not verify_password(user, request.current_password.get_secret_value()):
        raise HTTPException(
            400, "Current password is incorrect", headers={"Cache-Control": "no-store"}
        )


@router.post("/password", status_code=204, dependencies=[Depends(admission)])
def change_password(
    db: Database, incoming: Request, response: Response, request: PasswordChange
):
    user = account_user(db, incoming, response, lock=True)
    require_current_password(user, request)
    user.password_hash = hasher.hash(request.new_password.get_secret_value())
    db.execute(delete(models.AuthSession).where(models.AuthSession.user_id == user.id))
    cookie(response, issue_session(db, user, None, get_settings()))


@router.post(
    "/sessions/revoke-others", status_code=204, dependencies=[Depends(admission)]
)
def revoke_other_sessions(db: Database, incoming: Request, response: Response):
    user = account_user(db, incoming, response, lock=True)
    current_hash = token_hash(incoming.cookies.get(COOKIE_NAME))
    db.execute(
        delete(models.AuthSession).where(
            models.AuthSession.user_id == user.id,
            models.AuthSession.token_hash != current_hash,
        )
    )
    db.commit()


@router.delete("/account", status_code=204, dependencies=[Depends(admission)])
def delete_account(
    db: Database, incoming: Request, response: Response, request: AccountDelete
):
    user = account_user(db, incoming, response, lock=True)
    require_current_password(user, request)
    # Explicitly remove only this user's presets before the restrictive user FK.
    db.execute(
        delete(models.SavedComparison).where(models.SavedComparison.user_id == user.id)
    )
    db.execute(delete(models.AuthSession).where(models.AuthSession.user_id == user.id))
    db.delete(user)
    db.commit()
    return cleared_session_response()
