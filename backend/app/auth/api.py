"""Auth endpoints (TSK-054): login and current user.

No user-management endpoints are exposed here by design:
creation/updates via HTTP API require authorization and belong
to TSK-055. Bootstrap of the first admin is done via seed/CLI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.password_reset_service import (
    InvalidPasswordResetToken,
    PasswordResetService,
    RESET_EMAIL_RESPONSE,
)
from app.auth.schemas import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    TokenResponse,
    UserResponse,
)
from app.auth.sessions import active_sessions
from app.auth.service import AuthService, InvalidCredentialsError
from app.database.infrastructure.repositories import UserRepository
from app.database.infrastructure.session import get_db
from app.notifications.application.channel_config import SmtpConfig
from app.security.dependencies import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

__all__ = ["router"]


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate a human user",
    responses={401: {"description": "Invalid credentials or inactive user"}},
)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email + password and issue a JWT."""
    try:
        user, token, expires_in = AuthService().login(
            db, email=body.email, password=body.password
        )
    except InvalidCredentialsError:
        # Single generic message: do not reveal whether the user
        # exists, the password was wrong or the user is inactive.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    active_sessions.login(user.id, expires_in)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post(
    "/password-reset/request",
    response_model=PasswordResetResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password-reset email",
)
def request_password_reset(
    body: PasswordResetRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    if not SmtpConfig.from_env().is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de correo no está configurado.",
        )
    PasswordResetService().request_reset(db, body.email)
    return PasswordResetResponse(message=RESET_EMAIL_RESPONSE)


@router.post(
    "/password-reset/confirm",
    response_model=PasswordResetResponse,
    summary="Set a new password using a reset link",
)
def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        PasswordResetService().reset_password(db, body.token, body.new_password)
    except InvalidPasswordResetToken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El enlace no es válido o ya venció. Solicita uno nuevo.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return PasswordResetResponse(message="La contraseña se restableció correctamente.")


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End the local notification session",
)
def logout(current: AuthenticatedUser = Depends(get_current_user)):
    """Remove the caller from local notification recipients.

    JWTs remain stateless; this endpoint affects only the in-memory local
    recipient registry used for alert delivery.
    """
    active_sessions.logout(current.id)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the authenticated user's identity",
    responses={401: {"description": "Missing, invalid, expired, or inactive token"}},
)
def get_me(
    db: Session = Depends(get_db),
    current: AuthenticatedUser = Depends(get_current_user),
):
    """Return the user identified by the Bearer token.

    The identity always comes from the validated token, never
    from a client-provided user_id (no such field exists).
    """
    user = UserRepository().get_by_id(db, current.id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=bool(user.is_active),
        created_at=user.created_at,
    )
