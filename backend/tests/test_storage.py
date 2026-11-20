import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from starlette.websockets import WebSocketDisconnect

from app.contracts.events import ReviewInput
from app.db.models import AuditRow, IncidentRow
from app.errors import ServiceError
from app.main import create_app
from app.media import MAX_THUMBNAIL_BYTES
from app.services.events import EventBroker, event_message

from .support import OPERATOR, ORIGIN, RUN_ID, SOCKET_HEADERS, SOURCE_ID, publish_test_incident
from .support import test_candidate as make_candidate

ACK = {"decision": "acknowledged", "reason": "  Reviewed the evidence.  "}


def test_empty_storage_has_no_automatic_test_data(api):
    with TestClient(api) as client:
        assert client.get("/api/v1/sources").json() == {"items": []}
        assert client.get("/api/v1/incidents").json() == {"items": [], "total": 0}


def test_openapi_describes_operator_security_and_error_envelope(api):
    with TestClient(api) as client:
        schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/incidents/{id}/review"]["post"]
    assert operation["security"] == [{"HTTPBearer": []}]
    for status in ("401", "404", "409", "422", "503"):
        error = operation["responses"][status]["content"]["application/json"]["schema"]
        assert error == {"$ref": "#/components/schemas/ErrorEnvelope"}


def test_persistent_review_survives_restart_and_socket_reconnect(replay, database):
    with TestClient(replay) as client:
        assert "video_path" not in client.get("/api/v1/sources").json()["items"][0]
        with client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as ws:
            ready = ws.receive_json()
            assert ready["schema_version"] == "1.0" and ready["type"] == "ready" and ready["data"] == {}
            incident = publish_test_incident(replay)
            path = f"/api/v1/incidents/{incident.id}"
            created = ws.receive_json()
            assert created["type"] == "candidate_incident"
            assert created["data"] == {"incident_id": incident.id, "run_id": RUN_ID, "source_id": SOURCE_ID}
            assert client.get(path).json() == incident.model_dump(mode="json")
            assert client.get(f"{path}/audit").json()["items"][0]["action"] == "created"

        reviewed = client.post(f"{path}/review", json=ACK, headers=OPERATOR)
        assert reviewed.status_code == 200
        assert reviewed.json()["reviewer"] == "test-operator"
        snapshot = client.get("/api/v1/incidents").json()
        audit = client.get(f"{path}/audit").json()

        with client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as ws:
            assert ws.receive_json()["type"] == "ready"
            assert client.get("/api/v1/incidents").json() == snapshot

    with TestClient(create_app(database)) as restarted:
        assert restarted.get("/api/v1/incidents").json() == snapshot
        assert restarted.get(f"{path}/audit").json() == audit
        created_entry, review_entry = audit["items"]
        assert (created_entry["actor"], created_entry["reason"]) == ("system", None)
        assert (review_entry["action"], review_entry["actor"], review_entry["reason"]) == (
            "acknowledged", "test-operator", "Reviewed the evidence.",
        )


def test_idempotent_publish_and_review_notify_only_after_commit(replay, monkeypatch):
    events = []
    notify = replay.state.broker.notify

    def inspect_commit(event):
        with replay.state.sessions() as session:
            row = session.get(IncidentRow, event.data["incident_id"])
            audit = session.scalar(select(func.count()).select_from(AuditRow))
            events.append((event.type, row.review_status, audit))
        notify(event)

    monkeypatch.setattr(replay.state.broker, "notify", inspect_commit)
    with TestClient(replay) as client:
        with client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as ws:
            assert ws.receive_json()["type"] == "ready"
            original = publish_test_incident(replay)
            assert ws.receive_json()["type"] == "candidate_incident"
            assert replay.state.incidents.publish_incident(make_candidate("zone-crossing", 9000)) == original
            path = f"/api/v1/incidents/{original.id}"
            assert client.post(f"{path}/review", json=ACK, headers=OPERATOR).status_code == 200
            assert ws.receive_json()["type"] == "incident_reviewed"
            assert replay.state.incidents.publish_incident(make_candidate("zone-crossing")).review_status == "acknowledged"
            conflict = client.post(f"{path}/review", json={"decision": "dismissed", "reason": "Duplicate"}, headers=OPERATOR)
            assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "review_conflict"
    assert events == [("candidate_incident", "pending", 1), ("incident_reviewed", "acknowledged", 2)]


def test_concurrent_writers_share_one_incident_and_one_review(replay):
    def compete(operation):
        barrier = Barrier(2)

        def run():
            barrier.wait(timeout=5)
            return operation()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            return [future.result(timeout=10) for future in futures]

    first, duplicate = compete(lambda: publish_test_incident(replay))
    assert first == duplicate

    def review_once():
        try:
            replay.state.incidents.review(first.id, ReviewInput.model_validate(ACK), "test-operator")
            return "reviewed"
        except ServiceError as error:
            return error.code

    assert sorted(compete(review_once)) == ["review_conflict", "reviewed"]
    assert [entry.action for entry in replay.state.incidents.get_audit(first.id)] == ["created", "acknowledged"]


def test_invalid_thumbnail_and_duplicate_retry_cannot_attach_evidence_to_reviewed_incident(replay):
    candidate = make_candidate("oversized-evidence")
    oversized = b"\xff\xd8" + b"0" * MAX_THUMBNAIL_BYTES + b"\xff\xd9"
    incident = replay.state.incidents.publish_incident(candidate, oversized)
    path = f"/api/v1/incidents/{incident.id}"
    with TestClient(replay) as client:
        dismissed = client.post(f"{path}/review", headers=OPERATOR, json={"decision": "dismissed", "reason": "Test only"})
        assert dismissed.status_code == 200
        assert client.post(f"{path}/review", json=ACK).status_code == 401
        assert client.post(f"{path}/review", headers=OPERATOR, json=ACK).status_code == 409
        retried = replay.state.incidents.publish_incident(candidate, b"\xff\xd8\xff\xd9")
        assert retried.model_dump(mode="json") == dismissed.json()
        assert retried.evidence_url is None and client.get(f"{path}/thumbnail").status_code == 404
        assert [entry["action"] for entry in client.get(f"{path}/audit").json()["items"]] == ["created", "dismissed"]


def test_failed_audit_write_rolls_back_incident_and_review(replay, monkeypatch):
    incident = publish_test_incident(replay)
    events = []
    monkeypatch.setattr(replay.state.broker, "notify", events.append)
    with replay.state.sessions.begin() as session:
        session.connection().exec_driver_sql(
            "CREATE TRIGGER reject_audit BEFORE INSERT ON audit_entries "
            "BEGIN SELECT RAISE(ABORT, 'test audit write failure'); END"
        )
    with pytest.raises(IntegrityError):
        publish_test_incident(replay, "rolled-back")
    with TestClient(replay) as client:
        response = client.post(f"/api/v1/incidents/{incident.id}/review", json=ACK, headers=OPERATOR)
        assert response.status_code == 503
        assert response.json() == {"error": {"code": "storage_unavailable", "message": "Storage could not complete the request"}}
        page = client.get("/api/v1/incidents").json()
        assert page["total"] == 1 and page["items"][0]["review_status"] == "pending"
        assert len(client.get(f"/api/v1/incidents/{incident.id}/audit").json()["items"]) == 1
    assert events == []


@pytest.mark.parametrize("statement", [update(AuditRow).values(reason="tampered"), delete(AuditRow)])
def test_sqlite_audit_is_append_only(replay, statement):
    incident = publish_test_incident(replay)
    with pytest.raises(IntegrityError, match="append-only"):
        with replay.state.sessions.begin() as session:
            session.execute(statement)
    assert len(replay.state.incidents.get_audit(incident.id)) == 1


def test_incident_rejects_run_source_mismatch(replay):
    mismatched = make_candidate("wrong-source").model_copy(update={"source_id": "another-source"})
    with pytest.raises(DBAPIError, match="FOREIGN KEY"):
        replay.state.incidents.publish_incident(mismatched)
    assert replay.state.incidents.list_incidents(None, None, 1, 0) == ([], 0)


@pytest.mark.parametrize("payload", [
    {"decision": "pending", "reason": "Invalid transition"},
    {"decision": "dismissed", "reason": "  "},
    {"decision": "dismissed", "reason": "a" * 501},
    {"decision": "dismissed", "reason": "Forged reviewer", "reviewer": "someone-else"},
])
def test_invalid_review_does_not_create_an_audit_entry(replay, payload):
    incident = publish_test_incident(replay)
    with TestClient(replay) as client:
        path = f"/api/v1/incidents/{incident.id}"
        response = client.post(f"{path}/review", json=payload, headers=OPERATOR)
        assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"
        assert [entry["action"] for entry in client.get(f"{path}/audit").json()["items"]] == ["created"]


def test_incident_pagination_filter_and_order(replay):
    first = publish_test_incident(replay, "older")
    latest = publish_test_incident(replay, "newer")
    pair = sorted([first, latest], key=lambda item: (item.created_at, item.id), reverse=True)
    with TestClient(replay) as client:
        for offset, expected in enumerate(pair):
            page = client.get("/api/v1/incidents", params={"limit": 1, "offset": offset, "run_id": RUN_ID}).json()
            assert page["total"] == 2 and [item["id"] for item in page["items"]] == [expected.id]
        response = client.post(
            f"/api/v1/incidents/{latest.id}/review", json={"decision": "dismissed", "reason": "Closed"},
            headers=OPERATOR,
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == "dismissed"
        pending = client.get("/api/v1/incidents", params={"review_status": "pending"}).json()
        assert pending["total"] == 1 and pending["items"][0]["id"] == first.id
        assert client.get("/api/v1/incidents/unknown/audit").json()["error"]["code"] == "incident_not_found"
        assert client.get("/api/v1/incidents", params={"limit": 101}).status_code == 422


def geofence_payload():
    return {
        "source_id": SOURCE_ID, "label": "TEST DATA - ROI", "space_type": "image", "enabled": True,
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 0]]]},
        "frame_size_px": [20, 20],
    }


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_both_write_endpoints_require_operator_token(replay, headers):
    incident = publish_test_incident(replay)
    with TestClient(replay) as client:
        requests = [
            (f"/api/v1/incidents/{incident.id}/review", ACK),
            ("/api/v1/geofences", geofence_payload()),
        ]
        for path, payload in requests:
            result = client.post(path, json=payload, headers=headers)
            assert result.status_code == 401 and result.json()["error"]["code"] == "unauthorized"


def test_geofence_world_and_image_round_trip(replay):
    image = geofence_payload()
    world = {
        **geofence_payload(), "label": "TEST DATA - world", "space_type": "world", "frame_size_px": None,
        "geometry": {"type": "Polygon", "coordinates": [[[78, 17], [79, 17], [79, 18], [78, 17]]]},
    }
    with TestClient(replay) as client:
        for payload in (image, world):
            result = client.post("/api/v1/geofences", headers=OPERATOR, json=payload)
            assert result.status_code == 201
            assert result.json() == {**payload, "id": result.json()["id"]}
        results = client.get("/api/v1/geofences", params={"source_id": SOURCE_ID}).json()
        assert {result["space_type"] for result in results["items"]} == {"world", "image"}
        unknown = client.post("/api/v1/geofences", headers=OPERATOR, json={**image, "source_id": "unknown"})
        assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "source_not_found"


@pytest.mark.parametrize("changes", [
    {"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [6, 4], [0, 5], [5, 0], [0, 0]]]}},
    {"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [1, 0]]]}},
    {"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [30, 10], [0, 0]]]}},
    {"space_type": "world"},
    {"space_type": "unknown"},
])
def test_invalid_geofence_rejected(replay, changes):
    with TestClient(replay) as client:
        payload = {**geofence_payload(), **changes}
        response = client.post("/api/v1/geofences", headers=OPERATOR, json=payload)
        assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"


def test_cors_preflight_and_websocket_origin_allowlist(api):
    with TestClient(api) as client:
        headers = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"}
        matches = client.options("/api/v1/geofences", headers={**headers, "Origin": ORIGIN})
        assert matches.status_code == 200 and matches.headers["access-control-allow-origin"] == ORIGIN
        for origin in ({}, {"Origin": "http://localhost:5174"}):
            with pytest.raises(WebSocketDisconnect) as rejected:
                with client.websocket_connect("/ws/events", headers=origin):
                    pytest.fail("unauthorized origin was accepted")
            assert rejected.value.code == 1008
        with client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as ws:
            assert ws.receive_json()["type"] == "ready"
            ws.send_text("write")
            with pytest.raises(WebSocketDisconnect) as read_only:
                ws.receive_json()
            assert read_only.value.code == 1008


def test_broker_signals_overflow_from_another_thread():
    async def verify():
        broker = EventBroker(queue_size=1)
        broker.start()
        with broker.subscribe() as subscription:
            event = event_message("candidate_incident", incident_id="test")

            def publish_two():
                broker.notify(event)
                broker.notify(event)

            await asyncio.to_thread(publish_two)
            await asyncio.wait_for(subscription.overflow.wait(), timeout=2)
            assert subscription.events.qsize() == 1
        broker.stop()

    asyncio.run(verify())


def test_websocket_closes_on_subscriber_overflow(api, monkeypatch):
    broker = api.state.broker
    monkeypatch.setattr(broker, "_queue_size", 1)

    def burst():
        event = event_message("candidate_incident", incident_id="test")
        broker.notify(event)
        broker.notify(event)

    with TestClient(api) as client:
        with client.websocket_connect("/ws/events", headers=SOCKET_HEADERS) as ws:
            assert ws.receive_json()["type"] == "ready"
            # Queue both callbacks before the event loop can resume the subscriber.
            client.portal.call(burst)
            with pytest.raises(WebSocketDisconnect) as overflow:
                while True:
                    ws.receive_json()
            assert overflow.value.code == 1013
