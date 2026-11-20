from alembic import context
from dotenv import load_dotenv

from app.config import PROJECT_ROOT
from app.db.models import Base
from app.db.session import storage_engine, storage_url


def include_object(obj, name, kind, reflected, compare_to):
    if reflected and compare_to is None:
        if kind == "column" and name == "world_geom":
            return False
        if kind == "index" and name in {"ix_incidents_world_geom", "ix_geofences_world_geom"}:
            return False
    return True


def include_postgres_name(name, kind, parents):
    # The container also owns PostGIS extension tables on its search path.
    return kind != "table" or name in Base.metadata.tables


def run_online(connection):
    sqlite = connection.dialect.name == "sqlite"
    context.configure(
        connection=connection, target_metadata=Base.metadata, render_as_batch=sqlite,
        transactional_ddl=True, include_object=include_object, include_name=None if sqlite else include_postgres_name,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_online(connection)
else:
    load_dotenv(PROJECT_ROOT / ".env")
    url = storage_url()
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = storage_engine(url)
        try:
            with engine.connect() as connection:
                run_online(connection)
        finally:
            engine.dispose()
