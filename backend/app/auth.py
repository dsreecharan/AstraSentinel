from ipaddress import ip_address
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errors import ServiceError

operator_bearer = HTTPBearer(auto_error=False)


def judge_request(request: Request) -> bool:
    if not request.app.state.judge_mode or request.headers.get("origin") != request.app.state.frontend_origin:
        return False
    if request.url.hostname not in {"localhost", "127.0.0.1", "::1"} or not request.client:
        return False
    try:
        return ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def require_operator(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(operator_bearer)]
) -> str:
    if judge_request(request):
        return "local-judge"
    token = request.app.state.operator_token
    if token and credentials and compare_digest(credentials.credentials.encode(), token.encode()):
        return request.app.state.operator_name
    raise ServiceError(401, "unauthorized", "Local operator credentials required")
