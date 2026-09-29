"""Auth endpoints (TSK-054): login and current user.

No user-management endpoints are exposed here by design:
creation/updates via HTTP API require authorization and belong
to TSK-055. Bootstrap of the first admin is done via seed/CLI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.schemas import LoginRequest, TokenResponse, UserResponse
from app.auth.service import AuthService, InvalidCredentialsError
from app.database.infrastructure.repositories import UserRepository
from app.database.infrastructure.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

__all__ = ["router"]


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email + password and issue a JWT."""
    try:
        _, token, expires_in = AuthService().login(
            db, email=body.email, password=body.password
        )
    except InvalidCredentialsError:
        # Single generic message: do not reveal whether the user
        # exists, the password was wrong or the user is inactive.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserResponse)
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
