"""api_gateway.py – Session management endpoints.

Task 2: Session Management API Gateway.

Follows the pattern in api_gateway_core.py for session routes.
Endpoints:
  POST /sessions/create    – create a new session
  POST /sessions/refresh   – refresh an existing session
  POST /sessions/terminate – terminate a session
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from flask import Blueprint, jsonify, request

# Allow importing jwt_util from sibling microservices directory
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from microservices.auth_service.utils.jwt_util import (
    generate_refresh_token,
    generate_token,
    renew_token,
    validate_token,
)

from .user_sessions import UserSession

sessions_bp = Blueprint("sessions", __name__, url_prefix="/sessions")

# ---------------------------------------------------------------------------
# Consistent response helpers (Task 2 AC2)
# ---------------------------------------------------------------------------


def _success(data: dict, status: int = 200):
    return jsonify({"status": "success", "data": data}), status


def _error(message: str, status: int = 400):
    return jsonify({"status": "error", "message": message}), status


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@sessions_bp.route("/create", methods=["POST"])
def create_session():
    """POST /sessions/create

    Create a new session for an authenticated user.

    Request body (JSON)
    -------------------
    {
        "user_id": "user-001",
        "username": "alice",
        "roles": ["ROLE_USER"],          # optional
        "permissions": ["read", "write"] # optional
    }

    Task 2 AC2: Consistent response structure.
    """
    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be valid JSON")

    user_id = data.get("user_id", "").strip()
    username = data.get("username", "").strip()
    if not user_id or not username:
        return _error("user_id and username are required")

    roles = data.get("roles")
    permissions = data.get("permissions")

    access_token = generate_token(
        user_id=user_id,
        username=username,
        roles=roles,
        permissions=permissions,
    )
    refresh_token = generate_refresh_token(user_id, username)

    # Session expires when the refresh token expires (7 days by default)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=7)
    session = UserSession.create(
        user_id=user_id,
        username=username,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )

    return _success(
        {
            "session_id": session.session_id,
            "token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at.isoformat(),
        },
        201,
    )


@sessions_bp.route("/refresh", methods=["POST"])
def refresh_session():
    """POST /sessions/refresh

    Refresh an existing session by exchanging a refresh token for a new
    access token.

    Task 2 AC1: Users can refresh session tokens without authorization errors.
    Task 2 AC3: Token expiration is correctly validated during refresh requests.
    """
    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be valid JSON")

    refresh_token = data.get("refresh_token", "").strip()
    if not refresh_token:
        return _error("refresh_token is required")

    # Validate the refresh token (checks expiry)
    try:
        payload = validate_token(refresh_token)
    except jwt.ExpiredSignatureError:
        return _error("Refresh token has expired", 401)
    except jwt.InvalidTokenError as exc:
        return _error(f"Invalid refresh token: {exc}", 401)

    # Look up the session
    session = UserSession.get_by_refresh_token(refresh_token)
    if session is None:
        return _error("Session not found", 404)

    if not session.is_active or session.is_expired():
        return _error("Session has expired or been terminated", 401)

    # Issue new tokens
    user_id = payload.get("userId") or payload.get("sub", "")
    username = payload.get("username", "")
    new_access_token = renew_token(refresh_token)
    new_refresh_token = generate_refresh_token(user_id, username)

    session.update_tokens(new_access_token, new_refresh_token)

    return _success(
        {
            "token": new_access_token,
            "refresh_token": new_refresh_token,
            "session_id": session.session_id,
        }
    )


@sessions_bp.route("/terminate", methods=["POST"])
def terminate_session():
    """POST /sessions/terminate

    Terminate an active session.

    Task 2 AC2: Consistent response structure.
    """
    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be valid JSON")

    session_id = data.get("session_id", "").strip()
    if not session_id:
        return _error("session_id is required")

    session = UserSession.get_by_id(session_id)
    if session is None:
        return _error("Session not found", 404)

    session.terminate()
    return _success({"message": "Session terminated", "session_id": session_id})
