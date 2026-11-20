from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import create_app

from .replay_support import configure_replay, generate_mp4
from .support import OPERATOR, ORIGIN

UPLOAD = "/api/v1/sources/upload"
METADATA = {
    "Content-Type": "video/mp4",
    "X-Astra-Title": "Test%20replay",
    "X-Astra-Attribution": "Team%20test%20fixture",
    "X-Astra-Rights-Confirmed": "true",
}


def test_upload_lifecycle_and_deduplication(database, tmp_path, monkeypatch):
    media = tmp_path / "media"
    configure_replay(monkeypatch, media)
    content = generate_mp4(tmp_path / "fixture.mp4").read_bytes()
    with TestClient(create_app(database)) as client:
        assert client.get("/api/v1/access").json() == {"mode": "token"}
        assert client.post(UPLOAD, headers=METADATA, content=content).status_code == 401
        headers = METADATA | OPERATOR
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: client.post(UPLOAD, headers=headers, content=content), range(2)))
        assert [response.status_code for response in results] == [200, 200]
        source = results[0].json()
        assert results[1].json() == source
        assert source["title"] == "Test replay" and source["geo_mode"] == "unavailable"
        assert "video_path" not in source and len(list((media / "uploads").iterdir())) == 1
    with TestClient(create_app(database)) as client:
        assert client.get("/api/v1/sources").json() == {"items": [source]}


def test_invalid_uploads_leave_no_sources_or_files(database, tmp_path, monkeypatch):
    media = tmp_path / "media"
    configure_replay(monkeypatch, media)
    monkeypatch.setattr("app.services.uploads.UPLOAD_LIMIT", 24)
    headers = METADATA | OPERATOR
    with TestClient(create_app(database)) as client:
        unconfirmed = client.post(UPLOAD, headers=headers | {"X-Astra-Rights-Confirmed": "false"}, content=b"test")
        assert unconfirmed.status_code == 422 and unconfirmed.json()["error"]["code"] == "upload_rights_required"
        for content in (b"0" * 25, iter([b"0" * 12, b"0" * 13])):
            assert client.post(UPLOAD, headers=headers, content=content).status_code == 413
        assert client.post(UPLOAD, headers=headers, content=b"test").status_code == 415
        corrupt = b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00"
        response = client.post(UPLOAD, headers=headers, content=corrupt)
        assert response.status_code == 422 and response.json()["error"]["code"] == "decode_failed"
        assert client.get("/api/v1/sources").json() == {"items": []}
        assert not list((media / "uploads").iterdir())


def test_judge_writes_require_allowlisted_origin_and_loopback(database, tmp_path, monkeypatch):
    configure_replay(monkeypatch, tmp_path / "media")
    monkeypatch.setenv("ASTRA_JUDGE_MODE", "1")
    monkeypatch.delenv("ASTRA_OPERATOR_TOKEN")
    content = generate_mp4(tmp_path / "fixture.mp4").read_bytes()
    app = create_app(database)
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 5000)) as client:
        assert client.get("/api/v1/access").json() == {"mode": "judge"}
        assert client.post(UPLOAD, headers=METADATA, content=content).status_code == 401
        assert client.post(UPLOAD, headers=METADATA | {"Origin": "http://other.example"}, content=content).status_code == 401
        assert client.post(UPLOAD, headers=METADATA | {"Origin": ORIGIN}, content=content).status_code == 200
    with TestClient(create_app(database), base_url="http://127.0.0.1:8000", client=("192.0.2.12", 5000)) as client:
        assert client.post(UPLOAD, headers=METADATA | {"Origin": ORIGIN}, content=content).status_code == 401
