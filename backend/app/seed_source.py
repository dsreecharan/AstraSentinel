import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .config import PROJECT_ROOT, media_directory
from .contracts.events import Source
from .db.models import SourceRow
from .db.session import conflict_insert, storage_engine, storage_url
from .errors import StartupError
from .media import file_sha256, resolve_mp4


def required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def source_from_environment() -> tuple[Source, Path]:
    source_id = required_setting("ASTRA_SOURCE_ID")
    title = required_setting("ASTRA_SOURCE_TITLE")
    rights_note = required_setting("ASTRA_SOURCE_RIGHTS_NOTE")
    attribution = required_setting("ASTRA_SOURCE_ATTRIBUTION")
    path = resolve_mp4(media_directory(), required_setting("ASTRA_SOURCE_VIDEO_PATH"))
    sha256 = file_sha256(path)

    source = Source(
        id=source_id, title=title, video_sha256=sha256, rights_note=rights_note, attribution=attribution,
        license_url=os.getenv("ASTRA_SOURCE_LICENSE_URL", "").strip() or None, geo_mode="unavailable",
    )
    return source, path


def register_source(sessions: sessionmaker, source: Source, path: Path) -> None:
    with sessions.begin() as session:
        session.execute(
            conflict_insert(session, SourceRow).values(**source.model_dump(), video_path=str(path)).on_conflict_do_nothing()
        )
        row = session.scalars(select(SourceRow).where(SourceRow.id == source.id)).one_or_none()
        if row is None or row.video_path != str(path) or Source.model_validate(row, from_attributes=True) != source:
            raise ValueError("Source ID or checksum already belongs to a different registration")


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        source, path = source_from_environment()
        engine = storage_engine(storage_url())
        try:
            register_source(sessionmaker(engine), source, path)
        finally:
            engine.dispose()
    except (ValueError, StartupError) as error:
        raise SystemExit(str(error)) from None
    except (OSError, RuntimeError):
        raise SystemExit("Could not resolve or read the configured source file") from None
    except SQLAlchemyError:
        raise SystemExit("Could not register source. Check the database configuration and run the migrations.") from None
    print(f"Source registered: {source.id} ({source.video_sha256})")


if __name__ == "__main__":
    main()
