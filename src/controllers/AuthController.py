"""AuthController.py – Flask AuthController migrated from the legacy Java monolith.

Provides:
  GET  /health       – service health check (public, no auth required).
  POST /auth/login   – validate credentials and issue a signed JWT.
  POST /auth/logout  – revoke a JWT (in-memory JTI blacklist).

The controller is exposed as a Flask Blueprint (``auth_controller``) and can be
registered on any Flask application.  The companion ``create_app()`` factory
attaches ``TokenMiddleware`` so that the application is fully self-contained.

Acceptance criteria
-------------------
AC1  All critical methods have test coverage > 85%.
AC2  Tests pass for all typical and edge-case scenarios.
AC3  Code coverage report included in CI logs.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

import jwt
from flask import Blueprint, Flask, jsonify, request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory token revocation set (JTI-based blacklist)
# ---------------------------------------------------------------------------

_TOKEN_BLACKLIST: Set[str] = set()

# ---------------------------------------------------------------------------
# Mock credential / role store (no DB dependency in this microservice)
# ---------------------------------------------------------------------------

_MOCK_USERS: Dict[str, Dict[str, str]] = {
    "alice": {
        "user_id": "user-001",
        "password": "alice_pass",
        "email": "alice@example.com",
    },
    "admin": {
        "user_id": "user-002",
        "password": "admin_pass",
        "email": "admin@example.com",
    },
    "bob": {
        "user_id": "user-003",
        "password": "bob_pass",
        "email": "bob@example.com",
    },
}

_MOCK_USER_ROLES: Dict[str, List[str]] = {
    "admin": ["ROLE_ADMIN", "ROLE_USER"],
    "alice": ["ROLE_USER"],
    "bob": ["ROLE_USER"],
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_secret() -> str:
    return os.environ.get("JWT_SECRET_KEY", "security-platform-secret-change-in-prod")


def _get_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256")


def _get_expiry_minutes() -> int:
    return int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))


def _verify_credentials(username: str, password: str) -> Optional[Dict[str, str]]:
    """Return user record if credentials are valid, else ``None``."""
    user = _MOCK_USERS.get(username)
    if user and user["password"] == password:
        return user
    return None


def _get_user_roles(username: str) -> List[str]:
    return _MOCK_USER_ROLES.get(username, ["ROLE_USER"])


def _generate_token(
    user_id: str,
    username: str,
    roles: List[str],
    expiry_minutes: Optional[int] = None,
) -> str:
    """Issue a signed JWT access token."""
    now = datetime.now(tz=timezone.utc)
    minutes = expiry_minutes if expiry_minutes is not None else _get_expiry_minutes()
    payload: Dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_get_algorithm())


def _validate_token(token: str) -> Dict[str, Any]:
    """Decode and validate *token*; raise ``jwt.InvalidTokenError`` on failure."""
    payload = jwt.decode(
        token, _get_secret(), algorithms=[_get_algorithm()]
    )
    if "sub" not in payload and "userId" not in payload:
        raise jwt.InvalidTokenError("Token payload missing required subject claim")
    jti = payload.get("jti", "")
    if jti and jti in _TOKEN_BLACKLIST:
        raise jwt.InvalidTokenError("Token has been revoked")
    return payload


# ---------------------------------------------------------------------------
# Flask Blueprint
# ---------------------------------------------------------------------------

auth_controller = Blueprint("auth_controller", __name__)


@auth_controller.get("/health")
def health() -> tuple:
    """Service health check – always accessible without a token."""
    return jsonify({"status": "ok", "service": "auth-controller"}), 200


@auth_controller.post("/auth/login")
def login() -> tuple:
    """Validate credentials and return a signed JWT.

    Request body (JSON):
        {"username": str, "password": str}

    Returns:
        200  {"token": str, "user": {"user_id", "username", "email", "roles"}}
        400  {"error": "..."} – missing or malformed fields
        401  {"error": "Invalid username or password"}
    """
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    # Reject non-string or excessively long inputs (anti-malicious-input guard).
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "Invalid input type"}), 400
    if len(username) > 256 or len(password) > 256:
        return jsonify({"error": "Input exceeds maximum allowed length"}), 400

    user = _verify_credentials(username, password)
    if user is None:
        logger.warning("auth_controller: invalid credentials for username=%s", username)
        return jsonify({"error": "Invalid username or password"}), 401

    roles = _get_user_roles(username)
    token = _generate_token(user["user_id"], username, roles)
    logger.info(
        "auth_controller: token issued for user_id=%s username=%s",
        user["user_id"],
        username,
    )
    return (
        jsonify(
            {
                "token": token,
                "user": {
                    "user_id": user["user_id"],
                    "username": username,
                    "email": user.get("email", ""),
                    "roles": roles,
                },
            }
        ),
        200,
    )


@auth_controller.post("/auth/logout")
def logout() -> tuple:
    """Revoke the current JWT by adding its JTI to the in-memory blacklist.

    Requires:
        Authorization: Bearer <token>

    Returns:
        200  {"message": "Successfully logged out"}
        401  {"error": "..."} – missing, expired, or invalid token
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authorization token is missing"}), 401

    token = auth_header[len("Bearer "):]
    try:
        payload = _validate_token(token)
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401
    except jwt.InvalidTokenError as exc:
        return jsonify({"error": f"Invalid token: {exc}"}), 401

    jti: str = payload.get("jti", "")
    if jti:
        _TOKEN_BLACKLIST.add(jti)
    username = payload.get("username") or payload.get("sub", "unknown")
    logger.info("auth_controller: token revoked for user=%s jti=%s", username, jti)
    return jsonify({"message": "Successfully logged out"}), 200


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> Flask:
    """Create a Flask application with AuthController wired to TokenMiddleware."""
    from src.middleware.TokenMiddleware import TokenMiddleware  # local import avoids circularity

    app = Flask(__name__)
    app.register_blueprint(auth_controller)
    # Wrap the WSGI app with TokenMiddleware; public paths handled internally.
    app.wsgi_app = TokenMiddleware(app.wsgi_app)  # type: ignore[assignment]
    return app
