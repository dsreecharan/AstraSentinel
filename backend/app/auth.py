from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errors import ServiceError

operator_bearer = HTTPBearer(auto_error=False)


def require_operator(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(operator_bearer)]
) -> str:
    token = request.app.state.operator_token
    if token and credentials and compare_digest(credentials.credentials.encode(), token.encode()):
        return request.app.state.operator_name
    raise ServiceError(401, "unauthorized", "Local operator credentials required")
