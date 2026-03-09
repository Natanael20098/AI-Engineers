"""LoginController.py – /login and /refresh-token endpoints.

Tasks: 3 (JWT endpoints) + 6 (RBAC role encoding).
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

import jwt
from flask import Blueprint, current_app, jsonify, request

from ..utils.jwt_util import (
    generate_refresh_token,
    generate_token,
    get_user_permissions,
    get_user_roles,
    has_role,
    renew_token,
    validate_token,
)

login_bp = Blueprint("login", __name__, url_prefix="/auth")

# ---------------------------------------------------------------------------
# Mock credential store (simple; no DB as per Task 6 scope)
# ---------------------------------------------------------------------------

_MOCK_USERS: dict[str, dict[str, str]] = {
    "alice": {"user_id": "user-001", "password": "alice_pass"},
    "admin": {"user_id": "user-002", "password": "admin_pass"},
    "bob": {"user_id": "user-003", "password": "bob_pass"},
}


def _verify_credentials(username: str, password: str) -> dict | None:
    """Return user record if credentials are valid, else None."""
    user = _MOCK_USERS.get(username)
    if user and user["password"] == password:
        return user
    return None


# ---------------------------------------------------------------------------
# Auth decorator for role-protected routes (Task 6)
# ---------------------------------------------------------------------------


def jwt_required(f: Callable) -> Callable:
    """Decorator: enforces a valid JWT on the route."""

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization token is missing"}), 401
        token = auth_header[len("Bearer "):]
        try:
            payload = validate_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError as exc:
            return jsonify({"error": f"Invalid token: {exc}"}), 401
        request.current_user = payload  # type: ignore[attr-defined]
        return f(*args, **kwargs)

    return decorated


def role_required(role: str) -> Callable:
    """Decorator factory: enforces a minimum role on the route (Task 6 AC2)."""

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        @jwt_required
        def decorated(*args: Any, **kwargs: Any) -> Any:
            payload = request.current_user  # type: ignore[attr-defined]
            if role not in payload.get("roles", []):
                return jsonify({"error": f"Forbidden: role '{role}' required"}), 403
            return f(*args, **kwargs)

        return decorated

    return decorator


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@login_bp.route("/login", methods=["POST"])
def login():
    """POST /auth/login

    Validate credentials and return a signed JWT containing userId, roles,
    permissions, and expiry.

    Task 3 AC2: /login issues JWT tokens.
    Task 6 AC1: JWTs contain accurate user roles and permissions.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = _verify_credentials(username, password)
    if user is None:
        return jsonify({"error": "Invalid username or password"}), 401

    roles = get_user_roles(username)
    permissions = get_user_permissions(username)

    access_token = generate_token(
        user_id=user["user_id"],
        username=username,
        roles=roles,
        permissions=permissions,
    )
    refresh_token = generate_refresh_token(user["user_id"], username)

    return jsonify(
        {
            "token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "user_id": user["user_id"],
                "username": username,
                "roles": roles,
                "permissions": permissions,
            },
        }
    ), 200


@login_bp.route("/refresh-token", methods=["POST"])
def refresh_token_endpoint():
    """POST /auth/refresh-token

    Exchange a refresh token (or any valid token) for a new access token.

    Task 3 AC2: /refresh-token issues JWT tokens.
    Task 1 AC2: expired tokens are successfully renewed.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    token = data.get("refresh_token") or data.get("token", "")
    if not token:
        return jsonify({"error": "refresh_token is required"}), 400

    try:
        new_token = renew_token(token)
    except jwt.InvalidTokenError as exc:
        return jsonify({"error": f"Invalid token: {exc}"}), 401

    return jsonify({"token": new_token}), 200


@login_bp.route("/protected", methods=["GET"])
@role_required("ROLE_ADMIN")
def admin_only():
    """GET /auth/protected – example role-protected endpoint (Task 6 AC2)."""
    payload = request.current_user  # type: ignore[attr-defined]
    return jsonify({"message": "Access granted", "user": payload.get("username")}), 200
