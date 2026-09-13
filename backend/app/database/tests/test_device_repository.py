import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.infrastructure.base import Base
from app.database.infrastructure.models import DeviceORM
from app.database.infrastructure.repositories import DeviceRepository


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_device_create_and_get_by_code(db):
    repo = DeviceRepository()
    d = repo.create(db, code="CAVA-001", name="Cava", location="Lab A", device_type="cold_room", status="active")
    db.commit()
    assert d.code == "CAVA-001"
    # get_by_code exact & strip
    assert repo.get_by_code(db, "CAVA-001").id == d.id
    assert repo.get_by_code(db, "  CAVA-001  ").id == d.id
    assert repo.get_by_code(db, "NOPE") is None
    assert repo.get_by_code(db, "   ") is None
    assert repo.get_by_code(db, 123) is None  # type: ignore


def test_device_get_by_id(db):
    repo = DeviceRepository()
    d = repo.create(db, code="CAVA-002", name="Cava 2", location="Lab", device_type="cold_room", status="maintenance")
    db.commit()
    assert repo.get_by_id(db, d.id).code == "CAVA-002"
    assert repo.get_by_id(db, uuid.uuid4()) is None


def test_device_exists(db):
    repo = DeviceRepository()
    repo.create(db, code="VITRINA-001", name="Vitrina", location="Salon", device_type="refrigerated_showcase", status="active")
    db.commit()
    assert repo.exists(db, "VITRINA-001") is True
    assert repo.exists(db, "  VITRINA-001 ") is True
    assert repo.exists(db, "NOPE") is False


def test_device_duplicate_uses_db_unique(db):
    repo = DeviceRepository()
    repo.create(db, code="DUP-001", name="A", location="L", device_type="cold_room", status="active")
    db.commit()
    # second with same code must raise IntegrityError on flush (UNIQUE uq_devices_code)
    with pytest.raises(IntegrityError):
        repo.create(db, code="DUP-001", name="B", location="L2", device_type="cold_room", status="active")
        db.flush()
    db.rollback()
    # integrity error is DB source of truth, not ValueError 409
    assert repo.exists(db, "DUP-001") is True


def test_device_list_pagination_and_filters(db):
    repo = DeviceRepository()
    for code, st, dt in [
        ("CAVA-001", "active", "cold_room"),
        ("CAVA-002", "inactive", "cold_room"),
        ("VITRINA-001", "maintenance", "refrigerated_showcase"),
        ("VITRINA-002", "error", "refrigerated_showcase"),
    ]:
        repo.create(db, code=code, name=f"N {code}", location=f"Loc {code}", device_type=dt, status=st)
    db.commit()

    total, items = repo.list(db, page=1, per_page=2)
    assert total == 4
    assert len(items) == 2
    assert items[0].code == "CAVA-001"  # ordered by code asc

    total, items = repo.list(db, status="active")
    assert total == 1 and items[0].code == "CAVA-001"

    total, items = repo.list(db, device_type="refrigerated_showcase")
    assert total == 2

    total, items = repo.list(db, search="CAVA")
    assert total == 2

    total, items = repo.list(db, search="  cava  ")
    assert total == 2  # ilike case-insensitive

    total, items = repo.list(db, search="   ")
    assert total == 4  # empty search ignored


def test_device_create_validations(db):
    repo = DeviceRepository()
    with pytest.raises(ValueError):
        repo.create(db, code="  ", name="A", location="L", device_type="cold_room", status="active")
    with pytest.raises(ValueError):
        repo.create(db, code="X", name="  ", location="L", device_type="cold_room", status="active")
    with pytest.raises(ValueError):
        repo.create(db, code="X2", name="A", location="L", device_type="invalid", status="active")
    with pytest.raises(ValueError):
        repo.create(db, code="X3", name="A", location="L", device_type="cold_room", status="BAD")


def test_device_update_and_update_status(db):
    repo = DeviceRepository()
    d = repo.create(db, code="UPD-001", name="Old", location="OldLoc", device_type="cold_room", status="active")
    db.commit()

    repo.update(db, d, name="New", location="NewLoc")
    db.commit()
    assert d.name == "New" and d.location == "NewLoc"

    repo.update(db, d, device_type="refrigerated_showcase", status="maintenance")
    db.commit()
    assert d.device_type == "refrigerated_showcase" and d.status == "maintenance"

    # update_status helper
    res = repo.update_status(db, d.id, "error")
    db.commit()
    assert res.status == "error"

    assert repo.update_status(db, uuid.uuid4(), "active") is None

    with pytest.raises(ValueError):
        repo.update(db, d, status="INVALID")
    with pytest.raises(ValueError):
        repo.update(db, d, device_type="bad")
    with pytest.raises(ValueError):
        repo.update(db, d, unknown_field="x")  # type: ignore


def test_device_repos_do_not_commit(db):
    """Repositories use flush only; commit is caller's responsibility."""
    repo = DeviceRepository()
    d = repo.create(db, code="NOCOMMIT-001", name="A", location="L", device_type="cold_room", status="active")
    # without commit, should be visible in same session but not after rollback
    assert repo.get_by_code(db, "NOCOMMIT-001") is not None
    db.rollback()
    assert repo.get_by_code(db, "NOCOMMIT-001") is None


def test_device_inexistente_retorna_none(db):
    repo = DeviceRepository()
    assert repo.get_by_id(db, uuid.uuid4()) is None
    assert repo.get_by_code(db, "NO-EXISTE") is None
    assert repo.update_status(db, uuid.uuid4(), "active") is None
