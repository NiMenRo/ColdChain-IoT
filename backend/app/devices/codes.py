"""Automatic device code generation (always generated, never user-supplied).

Codes follow the seed convention per device type: ``CAVA-001`` for cold
rooms, ``VITRINA-001`` for refrigerated showcases. Numbering continues
past existing codes (gaps and non-numeric codes are tolerated) and the
creation endpoint retries on unique collisions, so concurrent creates
cannot produce duplicates.
"""

from __future__ import annotations

from app.database.infrastructure.models import DeviceORM

_CODE_PREFIXES = {
    "cold_room": "CAVA",
    "refrigerated_showcase": "VITRINA",
}

_MAX_ATTEMPTS = 20


def code_prefix(device_type: str) -> str:
    """Return the code prefix for a device type (KeyError on unknown type)."""
    return _CODE_PREFIXES[device_type]


def next_device_code(db, device_type: str, *, start: int = 1) -> str:
    """Return the next free ``PREFIX-NNN`` code for a device type.

    Scans existing codes with that prefix and returns the lowest free
    number. Raises ValueError on unknown device_type.
    """
    prefix = code_prefix(device_type)
    like = f"{prefix}-%"
    existing = {
        row[0]
        for row in db.query(DeviceORM.code).filter(DeviceORM.code.like(like)).all()
    }
    candidate = max(start, 1)
    while True:
        code = f"{prefix}-{candidate:03d}"
        if code not in existing:
            return code
        candidate += 1
        if candidate > start + 10000:
            raise ValueError(f"could not allocate a {prefix} code")
