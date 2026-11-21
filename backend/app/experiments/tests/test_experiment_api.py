"""TSK-059.6 — experiment runs/metrics query API."""

import sys
import uuid
from datetime import datetime, timezone
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
from app.security.dependencies import require_admin


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
    # Explicit, increasing timestamps: ordering is (timestamp, id) and two
    # metrics created in the same clock tick would tie on random UUIDs.
    metrics.append(
        s, run_id=r1.id, metric_type="readings_persisted", value=10.0,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    metrics.append(
        s, run_id=r1.id, metric_type="alerts_generated", value=1.0,
        timestamp=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
    )
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
    assert anon.get(f"/experiment-runs/{uuid.uuid4()}/analysis").status_code in (401, 403)


def test_analysis_includes_more_than_ten_thousand_samples_with_bounded_series():
    from datetime import datetime, timedelta, timezone
    from app.database.infrastructure.models import ExperimentMetricORM

    Session = _factory()
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with Session() as db:
        run = ExperimentRunRepository().create(
            db, scenario="WITH_QOS", started_at=started,
            finished_at=started + timedelta(seconds=100),
        )
        run_id = run.id
        rows = [
            {"id": uuid.UUID(int=i + 1), "run_id": run_id,
             "metric_type": "readings_persisted", "value": 1.0,
             "timestamp": started + timedelta(seconds=i / 120)}
            for i in range(12001)
        ]
        rows += [
            {"id": uuid.uuid4(), "run_id": run_id, "metric_type": "queue_wait_ms",
             "value": value, "timestamp": started + timedelta(seconds=5)}
            for value in (0, 20, 40)
        ]
        db.bulk_insert_mappings(ExperimentMetricORM, rows)
        other = ExperimentRunRepository().create(db, scenario="WITHOUT_QOS")
        ExperimentMetricRepository().append(db, run_id=other.id,
                                           metric_type="readings_persisted", value=999999)
        db.commit()
    response = _client(Session).get(f"/experiment-runs/{run_id}/analysis?max_points=7")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_samples"] == 12004
    assert body["provisional"] is False
    assert body["metrics"]["readings_persisted"]["sum"] == 12001
    assert body["metrics"]["queue_wait_ms"]["mean"] == 20
    assert body["metrics"]["queue_wait_ms"]["max"] == 40
    assert "alerts_generated" not in body["metrics"]
    assert len(body["series"]["readings_persisted"]) <= 7
    assert sum(p["value"] for p in body["series"]["readings_persisted"]) == 12001
    assert sum(p["count"] for p in body["series"]["queue_wait_ms"]) == 3


def test_analysis_empty_zero_limits_and_missing_run():
    Session = _factory()
    with Session() as db:
        run = ExperimentRunRepository().create(db, scenario="WITH_QOS")
        run_id = run.id
        db.commit()
    client = _client(Session)
    empty = client.get(f"/experiment-runs/{run_id}/analysis").json()
    assert empty["total_samples"] == 0 and empty["metrics"] == {} and empty["series"] == {}
    assert empty["provisional"] is True
    with Session() as db:
        ExperimentMetricRepository().append(db, run_id=run_id,
                                           metric_type="queue_wait_ms", value=0)
        db.commit()
    zero = client.get(f"/experiment-runs/{run_id}/analysis").json()
    assert zero["metrics"]["queue_wait_ms"] == {
        "count": 1, "sum": 0, "mean": 0, "max": 0, "latest": 0,
    }
    for limit in (0, 501):
        assert client.get(f"/experiment-runs/{run_id}/analysis?max_points={limit}").status_code == 422
    assert client.get(f"/experiment-runs/{uuid.uuid4()}/analysis").status_code == 404


def test_analysis_common_intervals_preserve_spikes_and_all_samples():
    from datetime import datetime, timedelta, timezone

    Session = _factory()
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = []
    with Session() as db:
        for scenario, duration in (("WITH_QOS", 30), ("WITHOUT_QOS", 60)):
            run = ExperimentRunRepository().create(
                db, scenario=scenario, started_at=started,
                finished_at=started + timedelta(seconds=duration),
            )
            ids.append(run.id)
            for seconds, value in ((1, 0), (2, 0), (2, 900), (11, 2)):
                ExperimentMetricRepository().append(
                    db, run_id=run.id, metric_type="queue_wait_ms", value=value,
                    timestamp=started + timedelta(seconds=seconds),
                )
        db.commit()
    client = _client(Session)
    bodies = [client.get(f"/experiment-runs/{id}/analysis?bucket_seconds=10").json() for id in ids]
    for body in bodies:
        assert body["bucket_seconds"] == 10
        assert body["total_samples"] == 4
        assert body["metrics"]["queue_wait_ms"]["mean"] == 225.5
        points = body["series"]["queue_wait_ms"]
        assert points[0] == {
            "elapsedMin": 5 / 60, "start_seconds": 0, "end_seconds": 10,
            "value": 300, "max": 900, "count": 3,
        }
        assert points[1]["value"] == 2 and points[1]["count"] == 1
        assert sum(p["count"] for p in points) == 4
    assert bodies[0]["series"] == bodies[1]["series"]
    # A too-fine request cannot bypass the server's bounded response.
    tiny = client.get(f"/experiment-runs/{ids[1]}/analysis?bucket_seconds=0.001&max_points=1").json()
    assert len(tiny["series"]["queue_wait_ms"]) == 1
    assert tiny["metrics"]["queue_wait_ms"]["mean"] == 225.5
    for width in ("0", "-1", "nan", "inf", "1000000001"):
        assert client.get(f"/experiment-runs/{ids[0]}/analysis?bucket_seconds={width}").status_code == 422


def test_start_run_conflicts_while_the_previous_run_is_draining():
    from app.experiments import active
    from app.qos.application.dispatcher import DispatchCoordinator
    from app.qos.application.traffic_planning_service import TrafficPlanningService

    Session = _factory()
    c = _client(Session)
    c.app.dependency_overrides[require_admin] = lambda: AuthenticatedUser(
        id=uuid.uuid4(), email="admin@example.com", name="Admin", role="admin",
        is_active=True,
    )
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=5)
    c.app.state.dispatch_coordinator = coordinator
    try:
        active.clear_active_run()
        coordinator.begin_drain(uuid.uuid4())
        r = c.post("/experiment-runs", json={"scenario": "WITH_QOS"})
        assert r.status_code == 409, r.text
        assert "draining" in r.json()["detail"]
        coordinator.end_drain()
        r = c.post("/experiment-runs", json={"scenario": "WITH_QOS"})
        assert r.status_code == 201, r.text
    finally:
        active.clear_active_run()


def test_start_records_effective_dispatch_config_even_with_client_metadata(monkeypatch):
    import json
    from app.experiments import active
    import app.experiments.api as api

    Session = _factory()
    c = _client(Session)
    c.app.dependency_overrides[require_admin] = lambda: AuthenticatedUser(
        id=uuid.uuid4(), email="admin@example.com", name="Admin",
        role="admin", is_active=True,
    )
    effective = {"class_quotas": {"high": 4, "medium": 2, "low": 1},
                 "wfq_flow_weights": {}, "capacities": {"pending_work_items": 7}}
    c.app.state.backend_config = type("Config", (), {
        "effective_qos_config": lambda self: effective,
    })()
    monkeypatch.setattr(api, "start_worker", lambda _id: True)
    try:
        active.clear_active_run()
        response = c.post("/experiment-runs", json={
            "scenario": "WITH_QOS",
            "config_snapshot": {"sensor_condition": "normal", "dispatch": "untrusted"},
        })
        assert response.status_code == 201
        snapshot = json.loads(response.json()["config_snapshot"])
        assert snapshot["sensor_condition"] == "normal"
        assert snapshot["dispatch"]["processing_version"] == 2
        assert snapshot["dispatch"]["work_unit"] == "sensor_reading"
        assert snapshot["dispatch"]["effective_config"] == effective
    finally:
        active.clear_active_run()


def test_finish_run_drains_the_closing_run_with_a_bounded_wait():
    from app.experiments import active
    from app.qos.application.dispatcher import DispatchCoordinator
    from app.qos.application.traffic_planning_service import TrafficPlanningService

    Session = _factory()
    c = _client(Session)
    c.app.dependency_overrides[require_admin] = lambda: AuthenticatedUser(
        id=uuid.uuid4(), email="admin@example.com", name="Admin", role="admin",
        is_active=True,
    )
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=5)
    c.app.state.dispatch_coordinator = coordinator
    c.app.state.backend_config = type(
        "Config", (), {"qos_drain_timeout_s": 7.5}
    )()
    calls = []
    coordinator.begin_drain = lambda run_id: calls.append(("begin", run_id))
    coordinator.wait_until_idle = lambda timeout: (
        calls.append(("wait", timeout)) or True
    )
    coordinator.end_drain = lambda: calls.append(("end", None))
    try:
        active.clear_active_run()
        r = c.post("/experiment-runs", json={"scenario": "WITH_QOS"})
        assert r.status_code == 201, r.text
        run_id = uuid.UUID(r.json()["id"])

        f = c.post(f"/experiment-runs/{run_id}/finish")

        assert f.status_code == 200, f.text
        assert calls[0] == ("begin", run_id)
        assert calls[1][0] == "wait" and 0 < calls[1][1] <= 7.5
        assert calls[2] == ("end", None)
        assert active.get_active_run() is None
    finally:
        active.clear_active_run()


def test_finish_timeout_retains_run_and_drain_until_retry(monkeypatch):
    from app.experiments import active
    from app.qos.application.dispatcher import DispatchCoordinator
    from app.qos.application.traffic_planning_service import TrafficPlanningService
    import app.experiments.api as api

    Session = _factory()
    c = _client(Session)
    c.app.dependency_overrides[require_admin] = lambda: AuthenticatedUser(
        id=uuid.uuid4(), email="admin@example.com", name="Admin", role="admin",
        is_active=True,
    )
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=5)
    c.app.state.dispatch_coordinator = coordinator
    c.app.state.backend_config = type("Config", (), {"qos_drain_timeout_s": 0.01})()
    monkeypatch.setattr(api, "start_worker", lambda _id: True)
    monkeypatch.setattr(api, "stop_worker", lambda _id: None)
    attempts = iter((False, True))
    monkeypatch.setattr(coordinator, "wait_until_idle", lambda _timeout: next(attempts))
    try:
        active.clear_active_run()
        run_id = c.post("/experiment-runs", json={"scenario": "WITH_QOS"}).json()["id"]
        response = c.post(f"/experiment-runs/{run_id}/finish")
        assert response.status_code == 409
        assert c.get(f"/experiment-runs/{run_id}").json()["finished_at"] is None
        assert active.get_active_run()[0] == uuid.UUID(run_id)
        assert coordinator.draining_run_id == uuid.UUID(run_id)
        assert c.post("/experiment-runs", json={"scenario": "WITHOUT_QOS"}).status_code == 409
        response = c.post(f"/experiment-runs/{run_id}/finish")
        assert response.status_code == 200
        assert response.json()["finished_at"] is not None
        assert active.get_active_run() is None
        assert not coordinator.is_draining
    finally:
        active.clear_active_run()


def test_finish_timeout_with_transport_and_ingestion_then_retry(monkeypatch):
    from app.acquisition.message_queue import MessageQueue
    from app.experiments import active
    from app.qos.application.dispatcher import DispatchCoordinator
    from app.qos.application.traffic_planning_service import TrafficPlanningService
    import app.experiments.api as api

    Session = _factory()
    c = _client(Session)
    c.app.dependency_overrides[require_admin] = lambda: AuthenticatedUser(
        id=uuid.uuid4(), email="admin@example.com", name="Admin", role="admin",
        is_active=True,
    )
    queue = MessageQueue(5)
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=5)
    c.app.state.message_queue = queue
    c.app.state.dispatch_coordinator = coordinator
    c.app.state.backend_config = type("Config", (), {"qos_drain_timeout_s": 0.01})()
    monkeypatch.setattr(api, "start_worker", lambda _id: True)
    monkeypatch.setattr(api, "stop_worker", lambda _id: None)
    try:
        active.clear_active_run()
        run_id = c.post("/experiment-runs", json={"scenario": "WITH_QOS"}).json()["id"]
        assert queue.append_received({"payload": "fixture"})
        assert c.post(f"/experiment-runs/{run_id}/finish").status_code == 409
        assert c.get(f"/experiment-runs/{run_id}").json()["finished_at"] is None
        assert not queue.append_received({"payload": "too late"})
        claimed = queue.pop_for_processing()
        assert c.post(f"/experiment-runs/{run_id}/finish").status_code == 409
        queue.finish_processing(claimed)
        response = c.post(f"/experiment-runs/{run_id}/finish")
        assert response.status_code == 200
        assert response.json()["finished_at"] is not None
        assert active.get_active_run() is None
        assert not coordinator.is_draining
    finally:
        active.clear_active_run()
