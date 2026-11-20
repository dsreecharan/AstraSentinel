from alembic import context
from dotenv import load_dotenv

from app.config import PROJECT_ROOT, database_path
from app.db.models import Base
from app.db.session import sqlite_engine, sqlite_url


def run_online(connection):
    context.configure(
        connection=connection, target_metadata=Base.metadata, render_as_batch=True, transactional_ddl=True
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_online(connection)
else:
    load_dotenv(PROJECT_ROOT / ".env")
    path = database_path()
    if context.is_offline_mode():
        context.configure(url=str(sqlite_url(path)), target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = sqlite_engine(path)
        try:
            with engine.connect() as connection:
                run_online(connection)
        finally:
            engine.dispose()
