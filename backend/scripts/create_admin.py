"""Bootstrap the first admin user (TSK-054).

Reads credentials from the environment (never hardcodes them),
hashes the password with the same mechanism as the login flow
and is idempotent: if the email already exists nothing is created.

Usage (from backend/):
    set ADMIN_EMAIL=admin@example.com
    set ADMIN_PASSWORD=change-me-securely
    python scripts/create_admin.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from app.auth.service import AuthService
from app.database.infrastructure.repositories import UserRepository
from app.database.infrastructure.session import SessionLocal


def main() -> int:
    email = os.getenv("ADMIN_EMAIL", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    name = os.getenv("ADMIN_NAME", "Administrator").strip() or "Administrator"
    if not email or not password:
        print("error: ADMIN_EMAIL and ADMIN_PASSWORD must be set in the environment")
        return 2
    with SessionLocal() as db:
        existing = UserRepository().get_by_email(db, email)
        if existing is not None:
            print(f"user already exists: {existing.email} ({existing.role})")
            return 0
        try:
            user = AuthService().create_user(
                db, name=name, email=email, password=password, role="admin"
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"error: could not create admin user: {exc}")
            return 1
        print(f"created admin user: {user.email} ({user.id})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
