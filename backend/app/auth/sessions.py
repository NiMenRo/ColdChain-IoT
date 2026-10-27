"""In-memory active-session registry for local notification delivery.

JWT authentication remains the source of truth.  This registry only answers
which users explicitly logged into *this* local backend instance and have not
logged out or reached the JWT lifetime.  It intentionally is not persistent:
local development restarts clear active recipients.
"""

from __future__ import annotations

import threading
import time
from uuid import UUID


class ActiveSessionRegistry:
    def __init__(self) -> None:
        self._expires_at: dict[UUID, float] = {}
        self._lock = threading.Lock()

    def login(self, user_id: UUID, expires_in: int) -> None:
        """Mark a user active no longer than the JWT lifetime."""
        with self._lock:
            self._expires_at[user_id] = time.monotonic() + max(0, expires_in)

    def logout(self, user_id: UUID) -> None:
        with self._lock:
            self._expires_at.pop(user_id, None)

    def active_user_ids(self) -> set[UUID]:
        now = time.monotonic()
        with self._lock:
            expired = [user_id for user_id, until in self._expires_at.items() if until <= now]
            for user_id in expired:
                self._expires_at.pop(user_id, None)
            return set(self._expires_at)


active_sessions = ActiveSessionRegistry()

