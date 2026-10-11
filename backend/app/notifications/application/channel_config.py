"""Environment-driven configuration for notification channel adapters.

All values come from environment variables so local runs work without any
external credentials. Secrets (``SMTP_PASSWORD``) are read here and passed
only to the SMTP transport; they are never logged — channel ``detail``
strings and log records must never contain them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class SmtpConfig:
    """Optional real-SMTP configuration for the email channel."""

    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    use_tls: bool = True
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        try:
            port = int(os.getenv("SMTP_PORT", "587"))
        except ValueError:
            port = 587
        try:
            timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
        except ValueError:
            timeout = 10.0
        return cls(
            enabled=_as_bool(os.getenv("SMTP_ENABLED"), False),
            host=os.getenv("SMTP_HOST", "").strip(),
            port=port,
            username=os.getenv("SMTP_USERNAME", "").strip(),
            password=os.getenv("SMTP_PASSWORD", ""),
            from_addr=os.getenv("SMTP_FROM", "").strip(),
            use_tls=_as_bool(os.getenv("SMTP_TLS"), True),
            timeout_seconds=timeout,
        )

    @property
    def is_configured(self) -> bool:
        """True only when a real delivery can be attempted."""
        return bool(self.enabled and self.host and self.from_addr)


@dataclass(frozen=True)
class SmsConfig:
    """Simulated-SMS configuration. This channel never performs real sends."""

    simulated: bool = True

    @classmethod
    def from_env(cls) -> "SmsConfig":
        return cls(simulated=_as_bool(os.getenv("SMS_SIMULATED"), True))


@dataclass(frozen=True)
class PushConfig:
    """Decoupled-push configuration. Web Push is NOT implemented in this phase."""

    enabled: bool = False

    @classmethod
    def from_env(cls) -> "PushConfig":
        return cls(enabled=_as_bool(os.getenv("PUSH_ENABLED"), False))


__all__ = ["PushConfig", "SmsConfig", "SmtpConfig"]
