import hashlib
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def test_seed_source_command_registers_only_a_source(api, database: Path, monkeypatch):
    media = database.parent / "media"
    media.mkdir()
    data = b"TEST DATA: synthetic registration fixture, no video decoding"
    (media / "example.mp4").write_bytes(data)
    outside = database.parent / "outside.mp4"
    outside.write_bytes(data)
    settings = {
        "PYTHON_DOTENV_DISABLED": "1",
        "ASTRA_DB_PATH": str(database),
        "ASTRA_MEDIA_DIR": str(media),
        "ASTRA_SOURCE_VIDEO_PATH": "example.mp4",
        "ASTRA_SOURCE_ID": "seed_test",
        "ASTRA_SOURCE_TITLE": "TEST DATA - registration only",
        "ASTRA_SOURCE_RIGHTS_NOTE": "TEST DATA for offline tests",
        "ASTRA_SOURCE_ATTRIBUTION": "Test fixture",
        "ASTRA_SOURCE_LICENSE_URL": "",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)

    command = [sys.executable, "-m", "app.seed_source"]
    for _ in range(2):
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr

    monkeypatch.setenv("ASTRA_SOURCE_VIDEO_PATH", str(outside))
    rejected = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert rejected.returncode == 1 and "must resolve inside ASTRA_MEDIA_DIR" in rejected.stderr
    assert str(outside) not in rejected.stderr

    with TestClient(api) as client:
        assert client.get("/api/v1/sources").json() == {"items": [{
            "id": "seed_test", "title": settings["ASTRA_SOURCE_TITLE"],
            "video_sha256": hashlib.sha256(data).hexdigest(),
            "rights_note": settings["ASTRA_SOURCE_RIGHTS_NOTE"],
            "attribution": settings["ASTRA_SOURCE_ATTRIBUTION"],
            "license_url": None, "geo_mode": "unavailable",
        }]}
        assert client.get("/api/v1/incidents").json() == {"items": [], "total": 0}
