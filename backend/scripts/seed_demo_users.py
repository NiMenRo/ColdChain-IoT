"""Seed demo login users (local development only).

Reads the shared password from the environment (never hardcodes it),
hashes passwords with the same mechanism as the login flow and is
idempotent: existing emails are skipped, nothing is overwritten.

Usage (from backend/):
    set DEMO_USER_PASSWORD=demo1234
    python scripts/seed_demo_users.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from app.auth.service import AuthService
from app.database.infrastructure.repositories import UserRepository
from app.database.infrastructure.session import SessionLocal

# Display names and roles only (no secrets). Must match the demo accounts
# offered by the frontend login screen: {role}@example.com.
DEMO_USERS = [
    ("Administrator", "admin@example.com", "admin"),
    ("Supervisor", "supervisor@example.com", "supervisor"),
    ("Operador", "operador@example.com", "operador"),
    ("Auditor", "auditor@example.com", "auditor"),
]


def main() -> int:
    password = os.getenv("DEMO_USER_PASSWORD", "")
    if not password:
        print("error: DEMO_USER_PASSWORD must be set in the environment")
        return 2
    created = 0
    with SessionLocal() as db:
        users = UserRepository()
        service = AuthService()
        for name, email, role in DEMO_USERS:
            if users.get_by_email(db, email) is not None:
                print(f"user already exists: {email} ({role})")
                continue
            try:
                service.create_user(
                    db, name=name, email=email, password=password, role=role
                )
                db.commit()
            except Exception as exc:
                db.rollback()
                print(f"error: could not create demo user {email}: {exc}")
                return 1
            print(f"created demo user: {email} ({role})")
            created += 1
    print(f"done: {created} demo user(s) created, {len(DEMO_USERS) - created} already existed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
