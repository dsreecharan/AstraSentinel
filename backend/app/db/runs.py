from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.contracts.events import ErrorDetail, ModelProvenance, Run, RunStatus
from app.contracts.geo import Geofence
from app.errors import ServiceError

from .models import GeofenceRow, RunRow, SourceRow

ACTIVE_STATUSES = ("starting", "running", "stopping")
TERMINAL_STATUSES = ("stopped", "ended", "error")


@dataclass(frozen=True)
class ReplayAsset:
    path: Path
    sha256: str
    geofences: tuple[Geofence, ...]


class RunStore:
    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions

    def create(self, source_id: str) -> tuple[Run, ReplayAsset]:
        with self._sessions() as session:
            source = session.get(SourceRow, source_id)
            if source is None:
                raise ServiceError(404, "source_not_found", "Source not found")
            fences = session.scalars(
                select(GeofenceRow).where(GeofenceRow.source_id == source_id, GeofenceRow.enabled.is_(True))
                .order_by(GeofenceRow.id)
            )
            asset = ReplayAsset(
                Path(source.video_path), source.video_sha256,
                tuple(Geofence.model_validate(row, from_attributes=True) for row in fences),
            )
        with self._sessions.begin() as session:
            row = RunRow(id=uuid4().hex, source_id=source_id, mode="replay", status="starting", started_at=datetime.now(UTC))
            session.add(row)
            result = Run.model_validate(row, from_attributes=True)
        return result, asset

    def get(self, run_id: str) -> Run:
        with self._sessions() as session:
            row = session.get(RunRow, run_id)
            if row is None:
                raise ServiceError(404, "run_not_found", "Run not found")
            return Run.model_validate(row, from_attributes=True)

    def latest(self) -> Run | None:
        with self._sessions() as session:
            row = session.scalars(select(RunRow).order_by(RunRow.started_at.desc(), RunRow.id.desc()).limit(1)).first()
            return Run.model_validate(row, from_attributes=True) if row is not None else None

    def transition(
        self, run_id: str, status: RunStatus, *,
        model: ModelProvenance | None = None, error: ErrorDetail | None = None,
    ) -> Run:
        values = {
            "status": status,
            "stopped_at": datetime.now(UTC) if status in TERMINAL_STATUSES else None,
            "error": error.model_dump() if error else None,
        }
        if model is not None:
            values["model"] = model.model_dump()
        with self._sessions.begin() as session:
            row = session.scalars(update(RunRow).where(RunRow.id == run_id).values(**values).returning(RunRow)).one()
            result = Run.model_validate(row, from_attributes=True)
        return result

    def recover_interrupted(self) -> list[Run]:
        error = ErrorDetail(code="run_interrupted", message="The service stopped before this replay finished")
        query = (
            update(RunRow).where(RunRow.status.in_(ACTIVE_STATUSES))
            .values(status="error", stopped_at=datetime.now(UTC), error=error.model_dump())
            .returning(RunRow)
        )
        with self._sessions.begin() as session:
            interrupted = [Run.model_validate(row, from_attributes=True) for row in session.scalars(query)]
        return interrupted
