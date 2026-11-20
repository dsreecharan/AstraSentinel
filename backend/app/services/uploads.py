from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import unquote
from uuid import uuid4

from anyio import to_thread
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import sessionmaker

from app.contracts.events import Source
from app.db.models import SourceRow
from app.errors import ServiceError
from app.vision.errors import ReplayError
from app.vision.source import OpenCVVideoSource

UPLOAD_LIMIT = 100 * 1024 * 1024


def metadata(request: Request, header: str) -> str:
    try:
        value = unquote(request.headers.get(header, ""), errors="strict").strip()
    except UnicodeError:
        value = ""
    if not value or len(value) > 160 or not value.isprintable():
        raise ServiceError(422, "upload_metadata_invalid", "Enter a title and owner or attribution up to 160 characters.")
    return value


def validate_mp4(media_root: Path, temporary: Path, digest: str) -> None:
    # Inspect ISO base media boxes before asking a native decoder to open the file.
    with temporary.open("rb") as file:
        while file.tell() < 65536:
            header = file.read(16)
            size = int.from_bytes(header[:4], "big")
            if len(header) < 16 or size < 8:
                break
            if header[4:8] == b"ftyp" and size >= 16 and header[8:12] != b"qt  ":
                try:
                    with OpenCVVideoSource(media_root, temporary, digest) as video:
                        video.read()
                except ReplayError as error:
                    raise ServiceError(422, error.code, str(error)) from None
                return
            if header[4:8] not in {b"free", b"skip", b"wide"}:
                break
            file.seek(size - len(header), 1)
    raise ServiceError(415, "upload_not_mp4", "Choose a valid MP4 file.")


def register_upload(sessions: sessionmaker, temporary: Path, source: Source) -> Source:
    destination = temporary.with_name(f"{uuid4().hex}.mp4")
    temporary.replace(destination)
    retained = False
    try:
        with sessions.begin() as session:
            session.execute(insert(SourceRow).values(**source.model_dump(), video_path=str(destination))
                            .on_conflict_do_nothing(index_elements=[SourceRow.video_sha256]))
            row = session.scalars(select(SourceRow).where(SourceRow.video_sha256 == source.video_sha256)).one()
            result = Source.model_validate(row, from_attributes=True)
            owns_row = row.video_path == str(destination)
        retained = owns_row
        return result
    finally:
        if not retained:
            destination.unlink(missing_ok=True)


async def upload_source(request: Request) -> Source:
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "video/mp4":
        raise ServiceError(415, "upload_not_mp4", "Upload an MP4 with content type video/mp4.")
    if request.headers.get("x-astra-rights-confirmed") != "true":
        raise ServiceError(422, "upload_rights_required", "Confirm that you have permission to process and display this footage.")
    title = metadata(request, "x-astra-title")
    attribution = metadata(request, "x-astra-attribution")
    length = request.headers.get("content-length", "")
    if length.isdecimal() and int(length) > UPLOAD_LIMIT:
        raise ServiceError(413, "upload_too_large", "The MP4 exceeds the 100 MiB upload limit.")

    media_root = request.app.state.media_directory
    directory = (media_root / "uploads").resolve()
    if not directory.is_relative_to(media_root) or directory == media_root:
        raise ServiceError(503, "storage_unavailable", "The private upload directory is unavailable.")
    temporary = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        size = 0
        digest = sha256()
        with NamedTemporaryFile(dir=directory, prefix="incoming-", suffix=".mp4", delete=False) as file:
            temporary = Path(file.name)
            async for chunk in request.stream():
                size += len(chunk)
                if size > UPLOAD_LIMIT:
                    raise ServiceError(413, "upload_too_large", "The MP4 exceeds the 100 MiB upload limit.")
                await to_thread.run_sync(file.write, chunk)
                digest.update(chunk)

        checksum = digest.hexdigest()
        await to_thread.run_sync(validate_mp4, media_root, temporary, checksum)
        source = Source(
            id=f"upload-{checksum}", title=title, video_sha256=checksum, attribution=attribution,
            rights_note="Uploaded locally. The operator confirmed permission to process and display this replay.",
            license_url=None, geo_mode="unavailable",
        )
        return await to_thread.run_sync(register_upload, request.app.state.sessions, temporary, source)
    except OSError:
        raise ServiceError(503, "storage_unavailable", "Could not save the MP4 in the private upload directory.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
