from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event


def sqlite_url(path: Path) -> URL:
    return URL.create("sqlite+pysqlite", database=str(path))


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
