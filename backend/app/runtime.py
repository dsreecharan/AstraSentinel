import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import StartupError

if os.name == "nt":
    import msvcrt
else:
    import fcntl


@contextmanager
def exclusive_worker(database: Path) -> Iterator[None]:
    """Hold one OS lock per SQLite database for the entire application lifespan."""
    database = database.resolve()
    lock_path = database.with_name(database.name + ".astra-worker.lock")
    try:
        lock = lock_path.open("ab")
    except OSError:
        raise StartupError("storage_unavailable", "Check that the SQLite directory exists and is writable") from None
    with lock:
        try:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise StartupError("worker_in_use", "Another Astra Fly process already owns this SQLite database") from None
        # Closing releases the lock, including on process exit. Keep its pathname stable.
        yield
