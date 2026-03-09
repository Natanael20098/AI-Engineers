"""auth_middleware.py – Token-based authentication middleware for the Security Platform.

Implements a Starlette/FastAPI BaseHTTPMiddleware that:
  - Extracts the Bearer token from the Authorization header.
  - Validates token signature and expiration using jwt_util.validate_token().
  - Logs both successful and failed authentication attempts.
  - Returns HTTP 401 for missing, expired, or invalid tokens.
  - Calls next() (the downstream handler) only when authentication passes.

Public paths (health check, login) bypass the token requirement.

Usage
-----
    from fastapi import FastAPI
    from services.security_platform.auth_middleware import AuthMiddleware

    app = FastAPI()
    app.add_middleware(AuthMiddleware)
"""

from __future__ import annotations

import logging
from typing import Sequence

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .utils.jwt_util import validate_token

logger = logging.getLogger(__name__)

# Routes that do not require a valid token.
_PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/auth/login",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


def _extract_bearer_token(request: Request) -> str | None:
    """Pull the Bearer token value from the Authorization header, or return None."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):]
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware that enforces JWT authentication.

    Acceptance criteria satisfied
    ------------------------------
    AC1  Unit tests cover success and failure scenarios (see tests/test_auth_middleware.py).
    AC2  Token verification logs both success and failure with appropriate level/message.
    AC3  Expired tokens → 401; invalid/tampered tokens → 401; missing token → 401.
    """

    def __init__(self, app, public_paths: Sequence[str] | None = None) -> None:
        super().__init__(app)
        self._public_paths: frozenset[str] = (
            frozenset(public_paths) if public_paths is not None else _PUBLIC_PATHS
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip auth for public endpoints.
        if request.url.path in self._public_paths:
            return await call_next(request)

        token = _extract_bearer_token(request)

        if not token:
            logger.warning(
                "auth_middleware: missing token | path=%s method=%s",
                request.url.path,
                request.method,
            )
            return JSONResponse(
                status_code=401,
                content={"error": "Authorization token is missing"},
            )

        try:
            payload = validate_token(token)
        except jwt.ExpiredSignatureError:
            logger.warning(
                "auth_middleware: expired token | path=%s method=%s",
                request.url.path,
                request.method,
            )
            return JSONResponse(
                status_code=401,
                content={"error": "Token has expired"},
            )
        except jwt.InvalidTokenError as exc:
            logger.warning(
                "auth_middleware: invalid token | path=%s method=%s error=%s",
                request.url.path,
                request.method,
                str(exc),
            )
            return JSONResponse(
                status_code=401,
                content={"error": f"Invalid token: {exc}"},
            )

        # Attach decoded payload for downstream route handlers.
        request.state.current_user = payload
        logger.info(
            "auth_middleware: authenticated | user=%s path=%s method=%s",
            payload.get("username") or payload.get("sub"),
            request.url.path,
            request.method,
        )

        # Authentication passed – call the next handler.
        return await call_next(request)
