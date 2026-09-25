from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.database.infrastructure.models import DeviceORM, SystemConfigORM, UserORM

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"
SYSTEM_CONFIG_ID = "00000000-0000-0000-0000-000000000001"

DEFAULT_SYSTEM_CONFIG = {
    "max_temperature": 4.0,
    "min_temperature": 0.0,
    "max_humidity": 90.0,
    "min_humidity": 85.0,
    "qos_algorithm": "wfq",
    "qos_enabled": True,
}

# Source of truth — simulator fetches via DB; keep data only here (no duplicate definition in simulator/main.py)
DEVICE_SEED = [
    {"code": "CAVA-001", "name": "Cava Principal", "location": "Sótano - Sector A", "device_type": "cold_room", "status": "active"},
    {"code": "CAVA-002", "name": "Cava Secundaria", "location": "Sótano - Sector B", "device_type": "cold_room", "status": "maintenance"},
    {"code": "VITRINA-001", "name": "Vitrina Mostrador 1", "location": "Salón Principal - Zona Clientes", "device_type": "refrigerated_showcase", "status": "active"},
]


def seed_devices(db: Session) -> int:
    inserted = 0
    for d in DEVICE_SEED:
        exists = db.query(DeviceORM).filter_by(code=d["code"]).first()
        if exists:
            continue
        db.add(DeviceORM(code=d["code"], name=d["name"], location=d["location"], device_type=d["device_type"], status=d["status"]))
        inserted += 1
    if inserted:
        db.commit()
        logger.info("Seeded %d devices", inserted)
    return inserted


def seed_user(db: Session) -> int:
    import uuid

    uid = uuid.UUID(SYSTEM_USER_ID)
    if db.query(UserORM).filter_by(id=uid).first():
        return 0
    db.add(UserORM(id=uid, name="system", email="system@coldchain.local", password_hash="!", role="system", is_active=True))
    db.commit()
    logger.info("Seeded system user %s", SYSTEM_USER_ID)
    return 1


def seed_system_config(db: Session) -> int:
    if db.query(SystemConfigORM).first():
        return 0

    db.add(
        SystemConfigORM(
            id=SYSTEM_CONFIG_ID,
            **DEFAULT_SYSTEM_CONFIG,
        )
    )
    db.commit()
    logger.info("Seeded initial system threshold configuration")
    return 1


def seed_all(db: Session) -> int:
    return seed_devices(db) + seed_user(db) + seed_system_config(db)
