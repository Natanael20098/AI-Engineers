"""TokenMiddleware.py – WSGI middleware for JWT Bearer token authentication.

Wraps any WSGI application (Flask, Django, etc.) and enforces JWT authentication
on all routes except a configurable set of public paths.

Public paths (bypass authentication by default):
  /health, /auth/login, /docs, /openapi.json, /redoc

Behaviour:
  - Extracts the Bearer token from the Authorization header.
  - Decodes and validates the JWT (signature, expiry, required claims).
  - Returns HTTP 401 JSON for missing, expired, or invalid tokens.
  - Attaches the decoded payload to ``environ["jwt.payload"]`` for downstream
    request handlers.
  - Logs success at INFO level; failure at WARNING level.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Callable, Sequence

import jwt

logger = logging.getLogger(__name__)

_PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/auth/login",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


def _extract_bearer_token(auth_header: str) -> str | None:
    """Return the token string from a ``Bearer <token>`` header, or ``None``."""
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):]
    return None


def _get_secret() -> str:
    return os.environ.get("JWT_SECRET_KEY", "security-platform-secret-change-in-prod")


def _get_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256")


def _json_401(message: str) -> bytes:
    return json.dumps({"error": message}).encode("utf-8")


class TokenMiddleware:
    """WSGI middleware that enforces JWT Bearer token authentication.

    Acceptance criteria
    -------------------
    AC1  Behaves correctly for valid and invalid token scenarios.
    AC2  Proper error messaging with consistent JSON error responses.
    AC3  Integration tests verify at least three service interaction patterns.

    Parameters
    ----------
    wsgi_app:     The downstream WSGI application to wrap.
    public_paths: Optional override of the default public (unauthenticated) paths.
    """

    def __init__(
        self,
        wsgi_app: Callable,
        public_paths: Sequence[str] | None = None,
    ) -> None:
        self.wsgi_app = wsgi_app
        self._public_paths: frozenset[str] = (
            frozenset(public_paths) if public_paths is not None else _PUBLIC_PATHS
        )

    def __call__(self, environ: dict, start_response: Callable) -> list[bytes]:
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "")

        # Public paths bypass authentication entirely.
        if path in self._public_paths:
            return self.wsgi_app(environ, start_response)

        auth_header = environ.get("HTTP_AUTHORIZATION", "")
        token = _extract_bearer_token(auth_header)

        if not token:
            logger.warning(
                "token_middleware: missing token | path=%s method=%s",
                path,
                method,
            )
            body = _json_401("Authorization token is missing")
            start_response(
                "401 Unauthorized",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        secret = _get_secret()
        algorithm = _get_algorithm()

        try:
            payload = jwt.decode(token, secret, algorithms=[algorithm])
            # Require a standard subject claim.
            if "sub" not in payload and "userId" not in payload:
                raise jwt.InvalidTokenError(
                    "Token payload missing required subject claim"
                )
        except jwt.ExpiredSignatureError:
            logger.warning(
                "token_middleware: expired token | path=%s method=%s",
                path,
                method,
            )
            body = _json_401("Token has expired")
            start_response(
                "401 Unauthorized",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]
        except jwt.InvalidTokenError as exc:
            logger.warning(
                "token_middleware: invalid token | path=%s method=%s error=%s",
                path,
                method,
                str(exc),
            )
            body = _json_401(f"Invalid token: {exc}")
            start_response(
                "401 Unauthorized",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        # Authentication passed – attach decoded payload for downstream handlers.
        environ["jwt.payload"] = payload
        logger.info(
            "token_middleware: authenticated | user=%s path=%s method=%s",
            payload.get("username") or payload.get("sub"),
            path,
            method,
        )
        return self.wsgi_app(environ, start_response)
