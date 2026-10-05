"""TSK-059.6 — experiment runs/metrics query API."""

import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.database.infrastructure.base import Base
from app.database.infrastructure.repositories import (
    ExperimentMetricRepository,
    ExperimentRunRepository,
)
from app.database.infrastructure.session import get_db
from app.experiments.api import router


def _factory():
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
    return sessionmaker(bind=engine, future=True)


def _client(Session):
    app = FastAPI()
    app.include_router(router)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid.uuid4(),
        email="auditor@example.com",
        name="Auditor",
        role="auditor",
        is_active=True,
    )
    return TestClient(app)


def _seed(Session):
    s = Session()
    runs = ExperimentRunRepository()
    metrics = ExperimentMetricRepository()
    r1 = runs.create(s, scenario="WITH_QOS")
    r2 = runs.create(s, scenario="WITHOUT_QOS")
    s.commit()
    metrics.append(s, run_id=r1.id, metric_type="readings_persisted", value=10.0)
    metrics.append(s, run_id=r1.id, metric_type="alerts_generated", value=1.0)
    metrics.append(s, run_id=r2.id, metric_type="readings_persisted", value=10.0)
    s.commit()
    ids = (r1.id, r2.id)
    s.close()
    return ids


def test_list_runs_and_filter_by_scenario():
    Session = _factory()
    r1, _r2 = _seed(Session)
    c = _client(Session)
    body = c.get("/experiment-runs").json()
    assert body["total"] == 2
    body = c.get("/experiment-runs", params={"scenario": "WITH_QOS"}).json()
    assert body["total"] == 1
    assert body["results"][0]["id"] == str(r1)
    assert body["results"][0]["scenario"] == "WITH_QOS"
    body = c.get("/experiment-runs", params={"scenario": "WITH_CACHE"})
    assert body.status_code == 400


def test_get_run_and_404():
    Session = _factory()
    r1, _r2 = _seed(Session)
    c = _client(Session)
    body = c.get(f"/experiment-runs/{r1}").json()
    assert body["id"] == str(r1)
    assert body["finished_at"] is None
    assert body["config_snapshot"] is None
    r = c.get(f"/experiment-runs/{uuid.uuid4()}")
    assert r.status_code == 404


def test_list_metrics_filter_and_404():
    Session = _factory()
    r1, _r2 = _seed(Session)
    c = _client(Session)
    body = c.get(f"/experiment-runs/{r1}/metrics").json()
    assert body["total"] == 2
    assert [m["value"] for m in body["results"]] == [10.0, 1.0]
    body = c.get(
        f"/experiment-runs/{r1}/metrics", params={"metric_type": "alerts_generated"}
    ).json()
    assert body["total"] == 1
    other = c.get(
        f"/experiment-runs/{_r2}/metrics", params={"metric_type": "alerts_generated"}
    ).json()
    assert other["total"] == 0
    r = c.get(f"/experiment-runs/{r1}/metrics", params={"metric_type": "latency"})
    assert r.status_code == 400
    r = c.get(f"/experiment-runs/{uuid.uuid4()}/metrics")
    assert r.status_code == 404


def test_pagination_and_unauthenticated():
    from fastapi import FastAPI as _FastAPI

    Session = _factory()
    _seed(Session)
    c = _client(Session)
    body = c.get("/experiment-runs", params={"page": 2, "per_page": 1}).json()
    assert body["total"] == 2 and body["count"] == 1
    r = c.get("/experiment-runs", params={"per_page": 200})
    assert r.status_code in (400, 422)

    app = _FastAPI()
    app.include_router(router)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    anon = TestClient(app)
    assert anon.get("/experiment-runs").status_code in (401, 403)
