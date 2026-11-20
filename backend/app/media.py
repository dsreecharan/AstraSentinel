import hashlib
from pathlib import Path

MAX_THUMBNAIL_BYTES = 128 * 1024


def resolve_mp4(media_root: Path, name: str | Path) -> Path:
    root = media_root.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Source MP4 must resolve inside ASTRA_MEDIA_DIR")
    if path.suffix.lower() != ".mp4" or not path.is_file():
        raise ValueError("Source must be an existing local MP4")
    return path


def file_sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()
