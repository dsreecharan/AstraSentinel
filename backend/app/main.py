import os
import re
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from anyio import to_thread
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .api import runs, storage, websocket
from .analysis.config import AnalysisSettings
from .config import database_path, local_path, media_directory
from .contracts.events import ErrorDetail, ErrorEnvelope, Health
from .db.runs import RunStore
from .db.session import sqlite_engine
from .errors import ServiceError, StartupError
from .runtime import exclusive_worker
from .services.events import EventBroker
from .services.incidents import IncidentService
from .vision.engine import VisionEngine
from .vision.ultralytics_adapter import UltralyticsAdapter
from .vision.worker import VideoWorker

VERSION = "0.1.0"
DEFAULT_FRONTEND_ORIGIN = "http://localhost:5173"


def error_response(status: int, code: str, message: str) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    payload = ErrorEnvelope(error=ErrorDetail(code=code, message=message))
    return JSONResponse(payload.model_dump(), status_code=status, headers=headers)


def create_app(
    db_path: Path | None = None, *, vision_factory: Callable[[], VisionEngine] | None = None,
) -> FastAPI:
    origin = os.getenv("ASTRA_FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN)
    if not re.fullmatch(r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?", origin):
        raise ValueError("ASTRA_FRONTEND_ORIGIN must be an explicit loopback origin")
    if urlsplit(origin).port == 0:
        raise ValueError("ASTRA_FRONTEND_ORIGIN must specify a usable port")

    path = db_path if db_path is not None else database_path()
    engine = sqlite_engine(path)
    sessions = sessionmaker(engine)
    broker = EventBroker()
    try:
        analysis = (
            AnalysisSettings.read(local_path("ASTRA_ANALYSIS_CONFIG", ""))
            if os.getenv("ASTRA_ANALYSIS_CONFIG") else AnalysisSettings()
        )
    except (OSError, ValueError):
        raise StartupError(
            "analysis_config_invalid", "Check that the rules and fixed-scene calibration file is readable and valid"
        ) from None
    incidents = IncidentService(sessions, broker)
    weights_path = local_path("ASTRA_MODEL_WEIGHTS", "data/weights/yolo26n.pt")
    video = VideoWorker(
        RunStore(sessions), broker, media_directory(),
        vision_factory if vision_factory is not None else lambda: UltralyticsAdapter(weights_path),
        analysis, incidents,
    )

    def recover() -> None:
        try:
            video.startup(path.exists() and inspect(engine).has_table("runs"))
        except SQLAlchemyError:
            raise StartupError("storage_unavailable", "Check the SQLite database and run the migrations") from None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        with exclusive_worker(path):
            broker.start()
            try:
                await to_thread.run_sync(recover)
                yield
            finally:
                try:
                    await to_thread.run_sync(video.shutdown)
                finally:
                    broker.stop()
                    engine.dispose()

    app = FastAPI(title="Astra Fly API", version=VERSION, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.frontend_origin = origin
    app.state.operator_token = os.getenv("ASTRA_OPERATOR_TOKEN", "")
    app.state.operator_name = os.getenv("ASTRA_OPERATOR_NAME", "local-operator").strip() or "local-operator"
    app.state.sessions = sessions
    app.state.broker = broker
    app.state.incidents = incidents
    app.state.analysis = analysis
    app.state.video = video
    app.add_middleware(
        CORSMiddleware, allow_origins=[origin], allow_methods=["GET", "POST"], allow_headers=["Authorization"]
    )
    app.include_router(storage.router)
    app.include_router(runs.router)
    app.include_router(websocket.router)

    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, error: ServiceError) -> JSONResponse:
        return error_response(error.status, error.code, error.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError) -> JSONResponse:
        return error_response(422, "validation_error", "Invalid request")

    @app.exception_handler(SQLAlchemyError)
    async def storage_error(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
        return error_response(503, "storage_unavailable", "Storage could not complete the request")

    @app.get("/api/v1/health")
    def get_health() -> Health:
        return Health(status="ok", version=VERSION, inference_status=video.inference_status)

    return app


app = create_app()
