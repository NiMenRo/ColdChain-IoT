"""One-time, expiring password reset workflow."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.auth.password import hash_password
from app.database.infrastructure.models import (
    HUMAN_USER_ROLES,
    PasswordResetTokenORM,
    UserORM,
)
from app.notifications.application.channel_config import SmtpConfig
from app.notifications.application.notification_channel import send_smtp_email

logger = logging.getLogger(__name__)

RESET_TOKEN_TTL = timedelta(minutes=30)
RESET_REQUEST_COOLDOWN = timedelta(minutes=1)
RESET_EMAIL_RESPONSE = (
    "Si el correo corresponde a una cuenta activa, recibirás instrucciones "
    "para restablecer la contraseña."
)
RESET_EMAIL_SUBJECT = "ColdChain-IoT | Restablecimiento de contraseña"


class InvalidPasswordResetToken(Exception):
    """The supplied reset token is unknown, expired, or already used."""


class PasswordResetService:
    def request_reset(self, db: Session, email: str) -> None:
        """Create and send a reset link without revealing account existence."""
        normalized_email = email.strip().lower()
        if not normalized_email:
            return

        user = (
            db.query(UserORM)
            .filter(UserORM.email == normalized_email)
            .filter(UserORM.is_active.is_(True))
            .filter(UserORM.role.in_(sorted(HUMAN_USER_ROLES)))
            .first()
        )
        if user is None:
            return

        now = datetime.now(timezone.utc)
        recent_request = (
            db.query(PasswordResetTokenORM)
            .filter(PasswordResetTokenORM.user_id == user.id)
            .filter(
                PasswordResetTokenORM.created_at
                >= now - RESET_REQUEST_COOLDOWN
            )
            .first()
        )
        if recent_request is not None:
            return

        # A new request invalidates earlier unused links for this account.
        (
            db.query(PasswordResetTokenORM)
            .filter(PasswordResetTokenORM.user_id == user.id)
            .filter(PasswordResetTokenORM.used_at.is_(None))
            .update(
                {PasswordResetTokenORM.used_at: now},
                synchronize_session=False,
            )
        )

        token = secrets.token_urlsafe(32)
        reset_token = PasswordResetTokenORM(
            user_id=user.id,
            token_hash=self._hash_token(token),
            created_at=now,
            expires_at=now + RESET_TOKEN_TTL,
        )
        db.add(reset_token)
        db.commit()

        frontend_url = os.getenv(
            "FRONTEND_BASE_URL", "http://localhost:5173"
        ).strip().rstrip("/")
        reset_link = f"{frontend_url}/reset-password#token={quote(token, safe='')}"
        body = (
            "Recibimos una solicitud para restablecer la contraseña de tu cuenta "
            "ColdChain-IoT.\n\n"
            "Para elegir una contraseña nueva, abre este enlace dentro de los "
            "próximos 30 minutos:\n"
            f"{reset_link}\n\n"
            "Si no solicitaste este cambio, puedes ignorar este mensaje."
        )
        try:
            send_smtp_email(
                SmtpConfig.from_env(),
                user.email,
                RESET_EMAIL_SUBJECT,
                body,
            )
        except Exception:
            logger.exception("Password reset email delivery failed")
            reset_token.used_at = datetime.now(timezone.utc)
            db.commit()

    def reset_password(self, db: Session, token: str, new_password: str) -> None:
        """Consume a valid reset link and update the account password."""
        if not isinstance(new_password, str) or len(new_password) < 8:
            raise ValueError("password must be at least 8 characters")
        if len(new_password.encode("utf-8")) > 72:
            raise ValueError("password must be no more than 72 UTF-8 bytes")

        now = datetime.now(timezone.utc)
        reset_token = (
            db.query(PasswordResetTokenORM)
            .filter(PasswordResetTokenORM.token_hash == self._hash_token(token))
            .filter(PasswordResetTokenORM.used_at.is_(None))
            .with_for_update()
            .first()
        )
        if reset_token is None or self._is_expired(reset_token.expires_at, now):
            raise InvalidPasswordResetToken

        user = db.query(UserORM).filter(UserORM.id == reset_token.user_id).first()
        if user is None or not user.is_active or user.role not in HUMAN_USER_ROLES:
            raise InvalidPasswordResetToken

        user.password_hash = hash_password(new_password)
        (
            db.query(PasswordResetTokenORM)
            .filter(PasswordResetTokenORM.user_id == user.id)
            .filter(PasswordResetTokenORM.used_at.is_(None))
            .update(
                {PasswordResetTokenORM.used_at: now},
                synchronize_session=False,
            )
        )
        db.commit()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_expired(expires_at: datetime, now: datetime) -> bool:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= now
