"""
authentication.py – Flask application entry point for the Authentication Service.

Exposed endpoints
-----------------
POST /auth/login    Validate credentials and return a signed JWT.
POST /auth/logout   Invalidate the current JWT (add to blacklist).

JWT handling
------------
Tokens are signed with HS256 using the JWT_SECRET_KEY configuration value.
Every token carries a ``jti`` (JWT ID) claim used to support revocation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

import jwt
from flask import Flask, current_app, jsonify, request

from .config import get_config
from .models import UserProfileModel
from .oauth import oauth_bp
from .token_store import build_blacklist

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(config=None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load configuration
    cfg = config or get_config()
    app.config.from_object(cfg)

    # Token blacklist (shared across requests via app context)
    app.config["TOKEN_BLACKLIST"] = build_blacklist(
        app.config.get("TOKEN_BLACKLIST_BACKEND", "memory"),
        app.config.get("REDIS_URL", ""),
    )

    # Register blueprints
    app.register_blueprint(oauth_bp)

    # Register auth routes on the app directly
    app.add_url_rule(
        "/auth/login", view_func=login, methods=["POST"]
    )
    app.add_url_rule(
        "/auth/logout", view_func=logout, methods=["POST"]
    )

    return app


# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------


def generate_jwt_token(user: UserProfileModel) -> str:
    """Issue a signed JWT for *user*.

    The token payload includes:
    - ``sub``  (subject)  – the user's unique identifier
    - ``username``        – the user's display name
    - ``email``           – the user's email address
    - ``iat``  (issued-at) – current UTC timestamp
    - ``exp``  (expiry)    – current time + JWT_ACCESS_TOKEN_EXPIRES
    - ``jti``  (JWT ID)    – random UUID for revocation support

    Returns
    -------
    str
        Encoded JWT string.
    """
    cfg = current_app.config
    now = datetime.now(tz=timezone.utc)
    expires_at = now + cfg["JWT_ACCESS_TOKEN_EXPIRES"]

    payload: dict[str, Any] = {
        "sub": user.user_id,
        "username": user.username,
        "email": user.email,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }

    token: str = jwt.encode(
        payload,
        cfg["JWT_SECRET_KEY"],
        algorithm=cfg.get("JWT_ALGORITHM", "HS256"),
    )
    return token


def _decode_jwt_token(token: str) -> dict:
    """Decode and verify *token*.

    Raises
    ------
    jwt.ExpiredSignatureError  if the token has expired.
    jwt.InvalidTokenError      for any other validation failure.
    """
    cfg = current_app.config
    return jwt.decode(
        token,
        cfg["JWT_SECRET_KEY"],
        algorithms=[cfg.get("JWT_ALGORITHM", "HS256")],
    )


def _extract_bearer_token() -> str | None:
    """Pull the Bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):]
    return None


# ---------------------------------------------------------------------------
# Authentication decorator
# ---------------------------------------------------------------------------


def jwt_required(f: Callable) -> Callable:
    """Decorator that enforces a valid, non-revoked JWT on a route."""

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        token = _extract_bearer_token()
        if not token:
            return jsonify({"error": "Authorization token is missing"}), 401

        try:
            payload = _decode_jwt_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError as exc:
            return jsonify({"error": f"Invalid token: {exc}"}), 401

        # Check revocation list
        jti = payload.get("jti", "")
        blacklist = current_app.config["TOKEN_BLACKLIST"]
        if blacklist.is_blacklisted(jti):
            return jsonify({"error": "Token has been revoked"}), 401

        # Attach decoded payload to request context for downstream use
        request.current_user = payload  # type: ignore[attr-defined]
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


def login():
    """POST /auth/login

    Validate user credentials and return a signed JWT.

    Request body (JSON)
    -------------------
    {
        "username": "alice",
        "password": "s3cr3t"
    }

    Responses
    ---------
    200  {"token": "<jwt>", "user": {...}}
    400  {"error": "..."}  – missing or malformed body
    401  {"error": "..."}  – invalid credentials or inactive account
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = UserProfileModel.get_by_username(username)

    if user is None or not user.verify_password(password):
        # Identical message for both "not found" and "wrong password" to
        # prevent username enumeration.
        return jsonify({"error": "Invalid username or password"}), 401

    if not user.is_active:
        return jsonify({"error": "Account is disabled"}), 401

    token = generate_jwt_token(user)
    return jsonify({"token": token, "user": user.to_dict()}), 200


@jwt_required
def logout():
    """POST /auth/logout

    Revoke the current JWT by adding its ``jti`` to the blacklist.

    Requires
    --------
    Authorization: Bearer <token>

    Responses
    ---------
    200  {"message": "Successfully logged out"}
    401  (handled by @jwt_required)
    """
    payload = request.current_user  # type: ignore[attr-defined]
    jti = payload.get("jti", "")
    exp = payload.get("exp", 0)

    blacklist = current_app.config["TOKEN_BLACKLIST"]
    blacklist.add(jti, float(exp))

    return jsonify({"message": "Successfully logged out"}), 200


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
