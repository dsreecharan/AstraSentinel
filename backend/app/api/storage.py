from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field
from sqlalchemy import select

from app.auth import require_operator
from app.contracts.common import ContractModel
from app.contracts.events import AuditEntry, Incident, ReviewInput, ReviewStatus, Source
from app.contracts.geo import Geofence, GeofenceInput
from app.db.models import GeofenceRow, SourceRow
from app.errors import ServiceError
from app.services.uploads import upload_source

from . import errors

router = APIRouter(prefix="/api/v1", responses=errors(503))


class SourceList(ContractModel):
    items: list[Source]
    simulated_source_ids: list[str] = Field(default_factory=list)


class AccessPolicy(ContractModel):
    mode: Literal["judge", "token"]


class IncidentPage(ContractModel):
    items: list[Incident]
    total: int


class AuditList(ContractModel):
    items: list[AuditEntry]


class GeofenceList(ContractModel):
    items: list[Geofence]


@router.get("/access")
def access_policy(request: Request) -> AccessPolicy:
    return AccessPolicy(mode="judge" if request.app.state.judge_mode else "token")


@router.post(
    "/sources/upload", dependencies=[Depends(require_operator)], responses=errors(401, 413, 415, 422),
    openapi_extra={
        "parameters": [
            {"name": name, "in": "header", "required": True, "schema": {"type": "string"}}
            for name in ("X-Astra-Title", "X-Astra-Attribution", "X-Astra-Rights-Confirmed")
        ],
        "requestBody": {"required": True, "content": {"video/mp4": {"schema": {"type": "string", "format": "binary"}}}},
    },
)
async def create_uploaded_source(request: Request) -> Source:
    return await upload_source(request)


@router.get("/sources", response_model_exclude_defaults=True)
def list_sources(request: Request) -> SourceList:
    with request.app.state.sessions() as session:
        rows = session.scalars(select(SourceRow).order_by(SourceRow.id))
        items = []
        simulated_source_ids = []
        for row in rows:
            source = Source.model_validate(row, from_attributes=True)
            settings = request.app.state.analysis.sources.get(source.id)
            calibration = settings.calibration if settings else None
            eligible = calibration is not None and calibration.video_sha256 == source.video_sha256
            if eligible and calibration.reference == "simulated":
                simulated_source_ids.append(source.id)
            items.append(source.model_copy(update={"geo_mode": "calibrated" if eligible else "unavailable"}))
        return SourceList(items=items, simulated_source_ids=simulated_source_ids)


@router.get("/incidents", responses=errors(422))
def list_incidents(
    request: Request,
    review_status: ReviewStatus | None = None,
    run_id: Annotated[str | None, Query(min_length=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IncidentPage:
    items, total = request.app.state.incidents.list_incidents(review_status, run_id, limit, offset)
    return IncidentPage(items=items, total=total)


@router.get("/incidents/{id}", responses=errors(404))
def get_incident(request: Request, id: str) -> Incident:
    return request.app.state.incidents.get_incident(id)


@router.get(
    "/incidents/{id}/thumbnail", response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}, **errors(404)},
)
def thumbnail(request: Request, id: str) -> Response:
    return Response(
        request.app.state.incidents.get_thumbnail(id), media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "Cross-Origin-Resource-Policy": "same-origin"},
    )


@router.post("/incidents/{id}/review", responses=errors(401, 404, 409, 422))
def review_incident(
    request: Request, id: str, review: ReviewInput, operator: Annotated[str, Depends(require_operator)]
) -> Incident:
    return request.app.state.incidents.review(id, review, operator)


@router.get("/incidents/{id}/audit", responses=errors(404))
def get_audit(request: Request, id: str) -> AuditList:
    return AuditList(items=request.app.state.incidents.get_audit(id))


@router.get("/geofences", responses=errors(422))
def list_geofences(
    request: Request, source_id: Annotated[str | None, Query(min_length=1)] = None
) -> GeofenceList:
    query = select(GeofenceRow).order_by(GeofenceRow.id)
    if source_id is not None:
        query = query.where(GeofenceRow.source_id == source_id)
    with request.app.state.sessions() as session:
        rows = session.scalars(query)
        return GeofenceList(items=[Geofence.model_validate(row, from_attributes=True) for row in rows])


@router.post(
    "/geofences", status_code=201, dependencies=[Depends(require_operator)],
    responses=errors(401, 404, 422),
)
def create_geofence(request: Request, payload: GeofenceInput) -> Geofence:
    sessions = request.app.state.sessions
    with sessions() as session:
        if session.get(SourceRow, payload.source_id) is None:
            raise ServiceError(404, "source_not_found", "Source not found")

    result = Geofence(id=uuid4().hex, **payload.model_dump())
    with sessions.begin() as session:
        session.add(GeofenceRow(**result.model_dump(mode="json")))
    return result
