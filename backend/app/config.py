import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def local_path(variable: str, default: str) -> Path:
    return (PROJECT_ROOT / os.getenv(variable, default)).resolve()


def database_path() -> Path:
    return local_path("ASTRA_DB_PATH", "data/astra.sqlite3")


def media_directory() -> Path:
    return local_path("ASTRA_MEDIA_DIR", "data/demo_video")
