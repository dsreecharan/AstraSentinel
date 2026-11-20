import os
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.contracts.events import IncidentCandidate, ReviewInput
from app.db.session import storage_engine
from app.errors import StartupError
from app.main import create_app

from .support import OPERATOR, SOCKET_HEADERS, SOURCE_ID, publish_test_incident, register_test_replay
from .support import test_candidate as candidate

pytestmark = pytest.mark.phase2


@pytest.fixture
def postgis(monkeypatch):
    value = os.getenv("ASTRA_TEST_POSTGIS_URL")
    if not value:
        pytest.skip("Set ASTRA_TEST_POSTGIS_URL to the disposable Compose service")
    import psycopg
    from psycopg import sql

    url = make_url(value)
    assert url.drivername == "postgresql+psycopg" and url.host in {"localhost", "127.0.0.1", "::1"}
    name = f"astra_test_{uuid4().hex}"
    server = url.set(drivername="postgresql")
    with psycopg.connect(server.render_as_string(hide_password=False), autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        test_url = url.set(database=name)
        engine = storage_engine(test_url)
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        try:
            with engine.connect() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            monkeypatch.setenv("ASTRA_POSTGIS_URL", test_url.render_as_string(hide_password=False))
            monkeypatch.setenv("ASTRA_OPERATOR_TOKEN", "test-only-token")
            monkeypatch.delenv("ASTRA_ANALYSIS_CONFIG", raising=False)
            yield engine
        finally:
            engine.dispose()
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_postgis_geometry_rest_review_websocket_and_worker_lock(postgis):
    app = create_app()
    register_test_replay(app)
    world_payload = {
        **candidate("world").model_dump(),
        "geo_status": "calibrated",
        "location": {"type": "Point", "coordinates": [78.4, 17.4]},
    }
    world = IncidentCandidate.model_validate(world_payload)
    with TestClient(app) as client, client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as socket:
        assert socket.receive_json()["type"] == "ready"
        with pytest.raises(StartupError, match="worker_in_use"):
            with TestClient(create_app()):
                pytest.fail("A second PostGIS worker started")
        image = publish_test_incident(app)
        assert socket.receive_json()["data"]["incident_id"] == image.id
        incident = app.state.incidents.publish_incident(world)
        assert socket.receive_json()["data"]["incident_id"] == incident.id
        assert app.state.incidents.publish_incident(world) == incident
        for space, ring, size in [
            ("world", [[78, 17], [79, 17], [79, 18], [78, 18], [78, 17]], None),
            ("image", [[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]], [40, 40]),
        ]:
            response = client.post("/api/v1/geofences", headers=OPERATOR, json={
                "source_id": SOURCE_ID, "label": space, "space_type": space, "enabled": True,
                "geometry": {"type": "Polygon", "coordinates": [ring]}, "frame_size_px": size,
            })
            assert response.status_code == 201, response.text

        route = f"/api/v1/incidents/{incident.id}"
        decision = {"decision": "acknowledged", "reason": "Verified test evidence"}
        assert client.post(f"{route}/review", json=decision).status_code == 401
        reviewed = client.post(f"{route}/review", headers=OPERATOR, json=decision)
        assert reviewed.status_code == 200
        assert socket.receive_json()["type"] == "incident_reviewed"
        assert client.post(f"{route}/review", headers=OPERATOR, json=decision).status_code == 409
        audit = client.get(f"{route}/audit").json()
        assert [r["action"] for r in audit["items"]] == ["created", "acknowledged"]

    with postgis.connect() as connection:
        assert connection.execute(text("""
            SELECT ST_X(i.world_geom), ST_Y(i.world_geom), ST_SRID(i.world_geom),
                   ST_Covers(g.world_geom, i.world_geom)
            FROM incidents i CROSS JOIN geofences g
            WHERE i.id = :id AND g.space_type = 'world'
        """), {"id": incident.id}).one() == (78.4, 17.4, 4326, True)
        assert connection.scalar(text("SELECT count(*) FROM incidents WHERE world_geom IS NULL")) == 1
        assert connection.scalar(text("SELECT count(*) FROM geofences WHERE world_geom IS NULL")) == 1
        assert connection.scalar(text("""
            SELECT count(*) FROM pg_indexes WHERE indexname IN ('ix_incidents_world_geom', 'ix_geofences_world_geom')
                AND indexdef LIKE '%USING gist%'
        """)) == 2
    for statement in ["UPDATE audit_entries SET reason = 'changed'", "DELETE FROM audit_entries", "TRUNCATE audit_entries"]:
        with pytest.raises(DBAPIError, match="append-only"):
            with postgis.begin() as connection:
                connection.execute(text(statement))
    with TestClient(create_app()) as restarted:
        assert restarted.get(route).json() == reviewed.json()
        assert restarted.get(f"{route}/audit").json() == audit


def test_storage_profile_comparison(postgis, database):
    review = ReviewInput(decision="acknowledged", reason="Benchmark fixture")
    for profile, app in (("SQLite", create_app(database)), ("PostGIS", create_app())):
        register_test_replay(app)
        samples = []
        try:
            for index in range(35):
                fixture = candidate(f"bench-{index}")
                start = perf_counter_ns()
                incident = app.state.incidents.publish_incident(fixture)
                app.state.incidents.review(incident.id, review, "benchmark")
                samples.append((perf_counter_ns() - start) / 1_000_000)
            assert app.state.incidents.list_incidents(None, None, 1, 0)[1] == 35
            print(f"{profile}: {median(samples[5:]):.3f} ms median publish + review, 30 samples after 5 warm-ups")
        finally:
            app.state.sessions.kw["bind"].dispose()
