from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.errors import StartupError
from app.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ASTRA_FRONTEND_ORIGIN", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health_reports_inference_not_started(client: TestClient):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "inference_status": "not_started",
    }


def test_health_response_is_in_openapi(client: TestClient):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    health_response = schema["paths"]["/api/v1/health"]["get"]["responses"]["200"]
    assert health_response["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/Health"


@pytest.mark.parametrize(
    ("origin", "allowed_origin"),
    [
        ("http://localhost:5173", "http://localhost:5173"),
        ("http://localhost:5174", None),
        ("https://outside.example", None),
    ],
)
def test_cors_allows_only_the_configured_origin(
    client: TestClient, origin: str, allowed_origin: str | None
):
    response = client.get("/api/v1/health", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == allowed_origin


def test_cors_can_use_an_explicit_loopback_override(monkeypatch: pytest.MonkeyPatch):
    origin = "http://127.0.0.1:5173"
    monkeypatch.setenv("ASTRA_FRONTEND_ORIGIN", origin)

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


def test_second_lifespan_cannot_recover_or_own_active_database(database):
    with TestClient(create_app(database)) as first:
        with pytest.raises(StartupError, match="worker_in_use"):
            with TestClient(create_app(database)):
                pytest.fail("Two apps owned the same database")
        assert first.get("/api/v1/runs/status").json() == {"run": None}
    with TestClient(create_app(database)) as restarted:
        assert restarted.get("/api/v1/runs/status").json() == {"run": None}


def test_analysis_config_startup_error_hides_local_path(monkeypatch, tmp_path):
    config = tmp_path / "private_calibration.json"
    config.write_text("invalid JSON", encoding="utf-8")
    monkeypatch.setenv("ASTRA_ANALYSIS_CONFIG", str(config))
    with pytest.raises(StartupError) as failure:
        create_app(tmp_path / "smoke.sqlite3")
    assert failure.value.code == "analysis_config_invalid"
    assert str(config) not in str(failure.value)


def test_unmigrated_storage_returns_structured_error(tmp_path):
    with TestClient(create_app(tmp_path / "unmigrated.sqlite3")) as app:
        response = app.get("/api/v1/sources")
    assert response.status_code == 503
    assert response.json() == {"error": {
        "code": "storage_unavailable", "message": "Storage could not complete the request",
    }}
