import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.auth import require_operator
from app.contracts.common import ContractModel, NonemptyString
from app.contracts.events import Run
from app.db.runs import TERMINAL_STATUSES
from app.errors import ServiceError
from app.vision.frames import LatestFrameStore

from . import errors

router = APIRouter(prefix="/api/v1", responses=errors(503))


class RunStart(ContractModel):
    source_id: NonemptyString
    mode: Literal["replay"]


class RunStop(ContractModel):
    run_id: NonemptyString


class RunSnapshot(ContractModel):
    run: Run | None


@router.post("/runs/start", status_code=202, dependencies=[Depends(require_operator)], responses=errors(401, 404, 409, 422))
def start_run(request: Request, payload: RunStart) -> Run:
    return request.app.state.video.start(payload.source_id)


@router.post(
    "/runs/stop", status_code=202, dependencies=[Depends(require_operator)],
    responses={200: {"model": Run}, **errors(401, 404, 422)},
)
def stop_run(request: Request, response: Response, payload: RunStop) -> Run:
    run = request.app.state.video.stop(payload.run_id)
    if run.status in TERMINAL_STATUSES:
        response.status_code = 200
    return run


@router.get("/runs/status")
def run_status(request: Request) -> RunSnapshot:
    return RunSnapshot(run=request.app.state.video.status())


async def replay_jpegs(frames: LatestFrameStore, run_id: str) -> AsyncIterator[bytes]:
    last_index = -1
    while (frame := frames.get()) is not None and frame.run_id == run_id:
        if frame.frame_index != last_index:
            last_index = frame.frame_index
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(frame.jpeg)).encode("ascii") + b"\r\n\r\n" + frame.jpeg + b"\r\n"
            )
        await asyncio.sleep(0.04)
    yield b"--frame--\r\n"


@router.get(
    "/stream/annotated.mjpg", response_class=StreamingResponse,
    responses={200: {"content": {"multipart/x-mixed-replace": {}}}},
)
def annotated_stream(request: Request, run_id: Annotated[str | None, Query(alias="run")] = None) -> StreamingResponse:
    frames = request.app.state.video.frames
    frame = frames.get()
    if frame is None or (run_id is not None and frame.run_id != run_id):
        raise ServiceError(503, "frame_unavailable", "No replay frame is available")
    return StreamingResponse(
        replay_jpegs(frames, frame.run_id), media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "Cross-Origin-Resource-Policy": "same-origin"},
    )
