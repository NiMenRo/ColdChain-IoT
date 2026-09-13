import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.infrastructure.base import Base
from app.database.infrastructure.models import UserORM
from app.database.infrastructure.repositories import UserRepository
from app.database.seed import SYSTEM_USER_ID


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


def test_user_create_and_normalize_email(db):
    repo = UserRepository()
    u = repo.create(db, name="Admin", email="  ADMIN@Example.COM  ", password_hash="hash", role="admin")
    db.commit()
    # @validates lower/strip -> stored lower
    assert u.email == "admin@example.com"
    # get_by_email normalizes too
    assert repo.get_by_email(db, "ADMIN@EXAMPLE.COM").id == u.id
    assert repo.get_by_email(db, "  admin@example.com  ").id == u.id
    assert repo.get_by_email(db, "nope@example.com") is None


def test_user_get_by_id_and_system_user(db):
    repo = UserRepository()
    # system user via seed id
    uid = uuid.UUID(SYSTEM_USER_ID)
    # create system user manually (simulate seed)
    u_sys = UserORM(id=uid, name="system", email="system@coldchain.local", password_hash="!", role="system")
    db.add(u_sys)
    db.commit()
    assert repo.get_system_user(db).id == uid
    assert repo.get_by_id(db, uid).email == "system@coldchain.local"
    assert repo.get_by_id(db, uuid.uuid4()) is None


def test_user_exists_email(db):
    repo = UserRepository()
    repo.create(db, name="A", email="a@example.com", password_hash="!", role="admin")
    db.commit()
    assert repo.exists_email(db, "a@example.com") is True
    assert repo.exists_email(db, "  A@Example.COM ") is True  # normalized
    assert repo.exists_email(db, "nope@example.com") is False


def test_user_duplicate_uses_db_unique(db):
    repo = UserRepository()
    repo.create(db, name="A", email="dup@example.com", password_hash="!", role="admin")
    db.commit()
    with pytest.raises(IntegrityError):
        repo.create(db, name="B", email="dup@example.com", password_hash="!", role="admin")
        db.flush()
    db.rollback()
    # case-variant duplicate also rejected (normalized before flush -> same lower value)
    with pytest.raises(IntegrityError):
        repo.create(db, name="C", email="  DUP@Example.com ", password_hash="!", role="admin")
        db.flush()
    db.rollback()


def test_user_list_pagination_and_filters(db):
    repo = UserRepository()
    for name, email, role in [
        ("Alice", "alice@example.com", "admin"),
        ("Bob", "bob@example.com", "operator"),
        ("Carol", "carol@example.com", "admin"),
    ]:
        repo.create(db, name=name, email=email, password_hash="!", role=role)
    db.commit()

    total, items = repo.list(db, page=1, per_page=2)
    assert total == 3 and len(items) == 2
    assert items[0].email == "alice@example.com"  # ordered by email asc

    total, items = repo.list(db, role="admin")
    assert total == 2

    total, items = repo.list(db, search="bob")
    assert total == 1 and items[0].name == "Bob"

    total, items = repo.list(db, search="  ALICE  ")
    assert total == 1

    total, items = repo.list(db, search="   ")
    assert total == 3


def test_user_create_validations(db):
    repo = UserRepository()
    with pytest.raises(ValueError):
        repo.create(db, name="  ", email="a@b.com", password_hash="!", role="admin")
    with pytest.raises(ValueError):
        repo.create(db, name="A", email="  ", password_hash="!", role="admin")
    with pytest.raises(ValueError):
        repo.create(db, name="A", email="a@b.com", password_hash="", role="admin")
    with pytest.raises(ValueError):
        repo.create(db, name="A", email="a@b.com", password_hash="!", role="  ")


def test_user_update(db):
    repo = UserRepository()
    u = repo.create(db, name="Old", email="old@example.com", password_hash="!", role="admin")
    db.commit()

    repo.update(db, u, name="New", role="operator")
    db.commit()
    assert u.name == "New" and u.role == "operator"

    repo.update(db, u, email="  NEW@Example.COM ")
    db.commit()
    assert u.email == "new@example.com"

    repo.update(db, u, password_hash="newhash")
    db.commit()
    assert u.password_hash == "newhash"

    with pytest.raises(ValueError):
        repo.update(db, u, email="  ")
    with pytest.raises(ValueError):
        repo.update(db, u, unknown="x")  # type: ignore


def test_user_repos_do_not_commit(db):
    repo = UserRepository()
    repo.create(db, name="A", email="nocommit@example.com", password_hash="!", role="admin")
    assert repo.get_by_email(db, "nocommit@example.com") is not None
    db.rollback()
    assert repo.get_by_email(db, "nocommit@example.com") is None


def test_user_inexistente_retorna_none(db):
    repo = UserRepository()
    assert repo.get_by_id(db, uuid.uuid4()) is None
    assert repo.get_by_email(db, "nope@example.com") is None
    assert repo.get_system_user(db) is None if db.query(UserORM).count() == 0 else True
