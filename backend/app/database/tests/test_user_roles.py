import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError

from app.database.infrastructure.base import Base
from app.database.infrastructure.models import UserORM
from app.database.infrastructure.repositories import UserRepository


HUMAN_ROLES = ("admin", "supervisor", "operador", "auditor")


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.mark.parametrize("role", HUMAN_ROLES)
def test_user_repository_accepts_supported_human_roles(db, role):
    user = UserRepository().create(
        db,
        name=role,
        email=f"{role}@example.com",
        password_hash="!",
        role=role,
    )
    assert user.role == role


@pytest.mark.parametrize("role", ("mantenimiento", "viewer", "operator", "invalid"))
def test_user_repository_rejects_unsupported_human_roles(db, role):
    with pytest.raises(ValueError):
        UserRepository().create(
            db,
            name="Invalid",
            email=f"{role}@example.com",
            password_hash="!",
            role=role,
        )


def test_system_identity_is_kept_separate_from_human_roles(db):
    system_user = UserORM(
        id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        name="system",
        email="system@coldchain.local",
        password_hash="!",
        role="system",
    )
    db.add(system_user)
    db.commit()

    assert system_user.role == "system"
    assert system_user.role not in HUMAN_ROLES


def test_database_constraint_rejects_unknown_role(db):
    with pytest.raises((ValueError, IntegrityError)):
        db.add(
            UserORM(
                name="Invalid",
                email="invalid@example.com",
                password_hash="!",
                role="viewer",
            )
        )
        db.flush()
