import os
from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.config import database_path
from app.errors import StartupError


def sqlite_url(path: Path) -> URL:
    return URL.create("sqlite+pysqlite", database=str(path))


def storage_url(path: Path | None = None) -> URL:
    configured = os.getenv("ASTRA_POSTGIS_URL")
    if path is not None or not configured:
        return sqlite_url(path if path is not None else database_path())
    try:
        url = make_url(configured)
        if url.drivername == "postgresql+psycopg" and url.database and url.host:
            return url
    except (ArgumentError, ValueError):
        pass
    raise StartupError("storage_config_invalid", "Use a postgresql+psycopg URL with a host and database name")


def storage_engine(url: URL) -> Engine:
    if url.get_backend_name() == "sqlite":
        return sqlite_engine(Path(url.database))
    try:
        return create_engine(
            url, hide_parameters=True, pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "options": "-c timezone=UTC"},
        )
    except ImportError:
        raise StartupError("storage_config_invalid", "Install the optional postgis backend extra") from None


def conflict_insert(session, model):
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql.insert(model)
    return sqlite.insert(model)


def sqlite_engine(path: Path) -> Engine:
    engine = create_engine(sqlite_url(path), hide_parameters=True)

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        # Python 3.11's sqlite3 otherwise leaves SELECT and DDL outside transactions.
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA recursive_triggers = ON")

    @event.listens_for(engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")

    return engine
