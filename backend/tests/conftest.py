from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI

from app.db.session import sqlite_engine
from app.main import create_app

from .support import ORIGIN, register_test_replay


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite3"
    engine = sqlite_engine(path)
    try:
        with engine.connect() as connection:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()
    return path


@pytest.fixture
def api(database: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.setenv("ASTRA_FRONTEND_ORIGIN", ORIGIN)
    monkeypatch.setenv("ASTRA_OPERATOR_TOKEN", "test-only-token")
    monkeypatch.setenv("ASTRA_OPERATOR_NAME", "test-operator")
    app = create_app(database)
    try:
        yield app
    finally:
        app.state.sessions.kw["bind"].dispose()


@pytest.fixture
def replay(api: FastAPI) -> FastAPI:
    register_test_replay(api)
    return api
