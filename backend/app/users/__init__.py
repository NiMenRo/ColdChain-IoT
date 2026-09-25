"""User management package (TSK-055).

HTTP exposure lives in app.users.api and is admin-only.
Business rules live in AuthService/UserRepository.
"""

from app.users.api import router

__all__ = ["router"]
