from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.contracts.events import AuditEntry, Incident, IncidentCandidate, ReviewInput, ReviewStatus
from app.db.models import AuditRow, IncidentRow
from app.db.session import conflict_insert
from app.errors import ServiceError
from app.media import MAX_THUMBNAIL_BYTES

from .events import EventBroker, event_message


def as_incident(row: IncidentRow) -> Incident:
    values = {name: getattr(row, name) for name in Incident.model_fields.keys() - {"severity", "evidence_url"}}
    return Incident(
        **values, severity="review",
        evidence_url=f"/api/v1/incidents/{row.id}/thumbnail" if row.has_evidence else None,
    )


def incident_not_found() -> ServiceError:
    return ServiceError(404, "incident_not_found", "Incident not found")


class IncidentService:
    def __init__(self, sessions: sessionmaker, broker: EventBroker):
        self.sessions = sessions
        self.broker = broker

    def publish_incident(self, candidate: IncidentCandidate, thumbnail: bytes | None = None) -> Incident:
        if thumbnail is not None and (
            len(thumbnail) > MAX_THUMBNAIL_BYTES
            or not thumbnail.startswith(b"\xff\xd8") or not thumbnail.endswith(b"\xff\xd9")
        ):
            thumbnail = None
        created_at = datetime.now(UTC)
        values = candidate.model_dump(exclude={"observed_at"})
        with self.sessions.begin() as session:
            row = session.scalars(
                conflict_insert(session, IncidentRow)
                .values(
                    **values, id=uuid4().hex, created_at=created_at,
                    observed_at=candidate.observed_at, review_status="pending",
                    evidence_jpeg=thumbnail,
                )
                .on_conflict_do_nothing(index_elements=[IncidentRow.idempotency_key])
                .returning(IncidentRow)
            ).one_or_none()
            if row is None:
                original = session.scalars(
                    select(IncidentRow).where(IncidentRow.idempotency_key == candidate.idempotency_key)
                ).one()
                return as_incident(original)

            session.add(AuditRow(incident_id=row.id, actor="system", action="created", created_at=created_at))
            incident = as_incident(row)

        self.broker.notify(event_message(
            "candidate_incident", incident_id=incident.id, run_id=incident.run_id, source_id=incident.source_id
        ))
        return incident

    def get_thumbnail(self, incident_id: str) -> bytes:
        with self.sessions() as session:
            row = session.execute(select(IncidentRow.evidence_jpeg).where(IncidentRow.id == incident_id)).one_or_none()
            if row is None:
                raise incident_not_found()
            if row[0] is None:
                raise ServiceError(404, "evidence_unavailable", "No thumbnail is retained for this incident")
            return row[0]

    def review(self, incident_id: str, review: ReviewInput, operator: str) -> Incident:
        reviewed_at = datetime.now(UTC)
        with self.sessions.begin() as session:
            row = session.scalars(
                update(IncidentRow)
                .where(IncidentRow.id == incident_id, IncidentRow.review_status == "pending")
                .values(review_status=review.decision, reviewer=operator, reviewed_at=reviewed_at)
                .returning(IncidentRow)
            ).one_or_none()
            if row is None:
                if session.get(IncidentRow, incident_id) is None:
                    raise incident_not_found()
                raise ServiceError(409, "review_conflict", "This incident has already been reviewed")

            session.add(AuditRow(
                incident_id=incident_id, actor=operator, action=review.decision,
                reason=review.reason, created_at=reviewed_at,
            ))
            incident = as_incident(row)

        self.broker.notify(event_message(
            "incident_reviewed", incident_id=incident.id, run_id=incident.run_id, source_id=incident.source_id
        ))
        return incident

    def list_incidents(
        self, review_status: ReviewStatus | None, run_id: str | None, limit: int, offset: int
    ) -> tuple[list[Incident], int]:
        query = select(IncidentRow)
        if review_status is not None:
            query = query.where(IncidentRow.review_status == review_status)
        if run_id is not None:
            query = query.where(IncidentRow.run_id == run_id)
        with self.sessions() as session:
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            page = query.order_by(IncidentRow.created_at.desc(), IncidentRow.id.desc()).limit(limit)
            return [as_incident(row) for row in session.scalars(page.offset(min(offset, total)))], total

    def get_incident(self, incident_id: str) -> Incident:
        with self.sessions() as session:
            row = session.get(IncidentRow, incident_id)
            if row is None:
                raise incident_not_found()
            return as_incident(row)

    def get_audit(self, incident_id: str) -> list[AuditEntry]:
        with self.sessions() as session:
            if session.get(IncidentRow, incident_id) is None:
                raise incident_not_found()
            rows = session.scalars(
                select(AuditRow).where(AuditRow.incident_id == incident_id).order_by(AuditRow.id)
            )
            return [
                AuditEntry(
                    id=str(row.id), incident_id=row.incident_id, actor=row.actor,
                    action=row.action, reason=row.reason, created_at=row.created_at,
                )
                for row in rows
            ]
