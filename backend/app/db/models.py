from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, column_property, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UtcDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("stored timestamps must include a timezone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.current_timestamp())


class SourceRow(Timestamped, Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str]
    video_path: Mapped[str] = mapped_column(Text)
    video_sha256: Mapped[str] = mapped_column(unique=True)
    rights_note: Mapped[str] = mapped_column(Text)
    attribution: Mapped[str] = mapped_column(Text)
    license_url: Mapped[str | None] = mapped_column(Text)
    geo_mode: Mapped[str]


class RunRow(Timestamped, Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("id", "source_id", name="uq_runs_id_source"),
        Index("ix_runs_source_created", "source_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    mode: Mapped[str]
    status: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(UtcDateTime())
    stopped_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    error: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    model: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))


class GeofenceRow(Timestamped, Base):
    __tablename__ = "geofences"
    __table_args__ = (
        CheckConstraint("space_type IN ('world', 'image')", name="ck_geofences_space"),
        Index("ix_geofences_source_id", "source_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    label: Mapped[str]
    space_type: Mapped[str]
    enabled: Mapped[bool]
    geometry: Mapped[dict] = mapped_column(JSON)
    frame_size_px: Mapped[list | None] = mapped_column(JSON(none_as_null=True))


class CalibrationRow(Timestamped, Base):
    __tablename__ = "calibrations"
    __table_args__ = (Index("ix_calibrations_source_id", "source_id"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    method: Mapped[str]
    frame_size_px: Mapped[list] = mapped_column(JSON)
    pixel_points: Mapped[list] = mapped_column(JSON)
    geo_points: Mapped[list] = mapped_column(JSON)
    reprojection_error_px: Mapped[float]
    valid_for_frame_range: Mapped[list | None] = mapped_column(JSON(none_as_null=True))


class IncidentRow(Timestamped, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "source_id"], ["runs.id", "runs.source_id"], name="fk_incidents_run_source"),
        CheckConstraint("video_time_ms >= 0", name="ck_incidents_video_time"),
        CheckConstraint(
            "(review_status = 'pending' AND reviewer IS NULL AND reviewed_at IS NULL) OR "
            "(review_status IN ('acknowledged', 'dismissed') AND reviewer IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_incidents_review",
        ),
        Index("ix_incidents_created_id", "created_at", "id"),
        Index("ix_incidents_review_created_id", "review_status", "created_at", "id"),
        Index("ix_incidents_run_created_id", "run_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    run_id: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str]
    rule_name: Mapped[str]
    rule_details: Mapped[dict] = mapped_column(JSON)
    video_time_ms: Mapped[int]
    observed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    location: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    geo_status: Mapped[str]
    horizontal_error_m: Mapped[float | None]
    evidence_path: Mapped[str | None] = mapped_column(Text)
    evidence_jpeg: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    has_evidence: Mapped[bool] = column_property(evidence_jpeg.is_not(None))
    review_status: Mapped[str]
    reviewer: Mapped[str | None]
    reviewed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class AuditRow(Timestamped, Base):
    __tablename__ = "audit_entries"
    __table_args__ = (
        CheckConstraint(
            "(action = 'created' AND actor = 'system' AND reason IS NULL) OR "
            "(action IN ('acknowledged', 'dismissed') AND length(coalesce(reason, '')) BETWEEN 1 AND 500)",
            name="ck_audit_entries_action",
        ),
        UniqueConstraint("incident_id", "action", name="uq_audit_entries_incident_action"),
        Index("ix_audit_entries_incident_id", "incident_id", "id"),
        Index("uq_audit_entries_review", "incident_id", unique=True, sqlite_where=text("action <> 'created'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    actor: Mapped[str]
    action: Mapped[str]
    reason: Mapped[str | None] = mapped_column(Text)
