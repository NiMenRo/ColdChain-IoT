"""Secure password hashing with bcrypt (TSK-054).

The plaintext password is never persisted and never returned.
Only the hash is stored via UserRepository.
"""

from __future__ import annotations

import bcrypt


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password. Raises ValueError on empty input."""
    if not isinstance(plain_password, str) or not plain_password:
        raise ValueError("password must be a non-empty string")
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Compare a plaintext password against a stored hash.

    Returns False for any invalid input or non-bcrypt hash
    (e.g. the legacy "!" placeholder), never raises.
    """
    try:
        if not isinstance(plain_password, str) or not plain_password:
            return False
        if not isinstance(password_hash, str) or not password_hash:
            return False
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False
