"""HTTP and WebSocket endpoints for the local API."""

from app.contracts.events import ErrorEnvelope


def errors(*statuses: int) -> dict:
    return {status: {"model": ErrorEnvelope} for status in statuses}
