"""User management endpoints (TSK-055).

Every route requires the admin role. There is deliberately no
self-service: users cannot change their own role through any
endpoint (attempts are rejected with 403).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.authorization import AuthenticatedUser, require_admin
from app.auth.schemas import UserResponse
from app.auth.service import AuthService
from app.database.infrastructure.models import TECHNICAL_USER_ROLE
from app.database.infrastructure.repositories import UserRepository
from app.database.infrastructure.session import get_db
from app.users.schemas import PasswordReset, UserCreate, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

__all__ = ["router"]

_users = UserRepository()
_auth = AuthService()


def _to_response(user) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=bool(user.is_active),
        created_at=user.created_at,
    )


def _get_or_404(db: Session, user_id: UUID):
    user = _users.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    return user


def _forbid_system(user) -> None:
    if user.role == TECHNICAL_USER_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The technical system identity cannot be managed via API.",
        )


@router.get("", response_model=dict)
def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _current: AuthenticatedUser = Depends(require_admin),
):
    total, items = _users.list(db, page=page, per_page=per_page, role=role, search=search)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "count": len(items),
        "results": [_to_response(u) for u in items],
    }


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _current: AuthenticatedUser = Depends(require_admin),
):
    return _to_response(_get_or_404(db, user_id))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _current: AuthenticatedUser = Depends(require_admin),
):
    if _users.exists_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )
    try:
        user = _auth.create_user(
            db,
            name=body.name,
            email=body.email,
            password=body.password,
            role=body.role,
            is_active=body.is_active,
        )
        db.commit()
        db.refresh(user)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )
    return _to_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current: AuthenticatedUser = Depends(require_admin),
):
    user = _get_or_404(db, user_id)
    _forbid_system(user)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No updatable fields provided.",
        )
    if user.id == current.id and "role" in fields:
        # No self-service role changes, even for admins.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Users cannot modify their own role.",
        )
    try:
        updated = _auth.update_user(db, user, **fields)
        db.commit()
        db.refresh(updated)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )
    return _to_response(updated)


@router.post("/{user_id}/password", response_model=dict)
def reset_password(
    user_id: UUID,
    body: PasswordReset,
    db: Session = Depends(get_db),
    _current: AuthenticatedUser = Depends(require_admin),
):
    """Admin-driven credential reset (no self-service endpoint exists)."""
    user = _get_or_404(db, user_id)
    _forbid_system(user)
    try:
        _auth.change_password(db, user, body.new_password)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"message": "Password updated successfully", "id": str(user.id)}
