from typing import Annotated, Literal, Self

from pydantic import StringConstraints, model_validator

from .common import (
    Confidence,
    ContractModel,
    NonemptyString,
    NonnegativeFloat,
    NonnegativeInt,
    PositiveInt,
    Sha256,
    UtcTimestamp,
)
from .geo import GeoStatus, Point

RunStatus = Literal["starting", "running", "stopping", "stopped", "ended", "error"]
ReviewStatus = Literal["pending", "acknowledged", "dismissed"]
ReviewDecision = Literal["acknowledged", "dismissed"]


class Health(ContractModel):
    status: Literal["ok", "degraded"]
    version: NonemptyString
    inference_status: Literal["not_started", "loading", "ready", "error"]


class Source(ContractModel):
    id: NonemptyString
    title: NonemptyString
    video_sha256: Sha256
    rights_note: NonemptyString
    attribution: NonemptyString
    license_url: str | None
    geo_mode: Literal["calibrated", "unavailable"]


class ErrorDetail(ContractModel):
    code: NonemptyString
    message: NonemptyString


class ErrorEnvelope(ContractModel):
    error: ErrorDetail


class ModelProvenance(ContractModel):
    name: Literal["yolo26n"]
    weights_sha256: Sha256
    ultralytics_version: NonemptyString
    tracker: Literal["bytetrack"]


class Run(ContractModel):
    id: NonemptyString
    source_id: NonemptyString
    mode: Literal["replay"]
    status: RunStatus
    started_at: UtcTimestamp
    stopped_at: UtcTimestamp | None
    error: ErrorDetail | None
    model: ModelProvenance | None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        terminal = self.status in {"stopped", "ended", "error"}
        if terminal != (self.stopped_at is not None):
            raise ValueError("a stop timestamp is required exactly when a run is terminal")
        if (self.status == "error") != (self.error is not None):
            raise ValueError("run error state requires error details")
        if self.status == "running" and self.model is None:
            raise ValueError("a running replay requires verified model provenance")
        return self


class RuleDetails(ContractModel):
    trigger_frame_index: NonnegativeInt
    consecutive_frames: PositiveInt
    cooldown_ms: NonnegativeInt


class CrowdRuleDetails(RuleDetails):
    person_count: NonnegativeInt
    threshold_count: NonnegativeInt
    clear_count: NonnegativeInt
    min_detector_confidence: Confidence
    region_id: NonemptyString | None

    @model_validator(mode="after")
    def validate_crossing(self) -> Self:
        if not self.clear_count < self.threshold_count < self.person_count:
            raise ValueError("a crowd candidate requires clear count < threshold < person count")
        return self


class ZoneRuleDetails(RuleDetails):
    zone_id: NonemptyString
    track_id: NonemptyString


class IncidentContext(ContractModel):
    run_id: NonemptyString
    source_id: NonemptyString
    event_type: Literal["crowd_threshold", "zone_intrusion"]
    rule_name: Literal["crowd_count_above_threshold", "restricted_zone_entry"]
    rule_details: CrowdRuleDetails | ZoneRuleDetails
    video_time_ms: NonnegativeInt
    observed_at: UtcTimestamp | None
    location: Point | None
    geo_status: GeoStatus
    horizontal_error_m: NonnegativeFloat | None

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if (self.geo_status == "calibrated") != (self.location is not None):
            raise ValueError("a calibrated incident requires a world location")
        if self.location is None and self.horizontal_error_m is not None:
            raise ValueError("horizontal uncertainty requires a world location")
        if self.event_type == "crowd_threshold":
            if self.rule_name != "crowd_count_above_threshold" or not isinstance(self.rule_details, CrowdRuleDetails):
                raise ValueError("crowd_threshold requires crowd count rule details")
            expected_geo = "image_roi_only" if self.rule_details.region_id else "unavailable"
            if self.geo_status != expected_geo:
                raise ValueError("crowd alerts describe a scene or image region without a world point")
        elif self.rule_name != "restricted_zone_entry" or not isinstance(self.rule_details, ZoneRuleDetails):
            raise ValueError("zone_intrusion requires restricted zone entry rule details")
        else:
            prefix = f"{self.run_id}:"
            if not self.rule_details.track_id.startswith(prefix) or self.rule_details.track_id == prefix:
                raise ValueError("the zone entry track must belong to the incident run")
        return self


class IncidentCandidate(IncidentContext):
    """Internal input from the rules worker. Review metadata is assigned by the service."""

    idempotency_key: NonemptyString


class Incident(IncidentContext):
    id: NonemptyString
    severity: Literal["review"]
    created_at: UtcTimestamp
    evidence_url: str | None
    review_status: ReviewStatus
    reviewer: NonemptyString | None
    reviewed_at: UtcTimestamp | None

    @model_validator(mode="after")
    def validate_review(self) -> Self:
        if self.review_status == "pending":
            if self.reviewer is not None or self.reviewed_at is not None:
                raise ValueError("a pending incident must have null review metadata")
        elif self.reviewer is None or self.reviewed_at is None:
            raise ValueError("a reviewed incident requires a reviewer and review timestamp")
        return self


class ReviewInput(ContractModel):
    decision: ReviewDecision
    reason: Annotated[str, StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=500, pattern=r"^[^\x00]+$"
    )]


class AuditEntry(ContractModel):
    id: NonemptyString
    incident_id: NonemptyString
    actor: NonemptyString
    action: Literal["created", "acknowledged", "dismissed"]
    reason: str | None
    created_at: UtcTimestamp


EventType = Literal["ready", "candidate_incident", "incident_reviewed", "run_status"]


class EventEnvelope(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    type: EventType
    emitted_at: UtcTimestamp
    data: dict[str, str]
