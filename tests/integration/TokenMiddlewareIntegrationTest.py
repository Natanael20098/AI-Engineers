"""TokenMiddlewareIntegrationTest.py – Integration tests for TokenMiddleware.

Tests the middleware's behaviour when integrated across three simulated
microservice interaction patterns:

  Service A – Authentication service:  /auth/login is public (no token required).
  Service B – User service:            /api/users/* is protected (token required).
  Service C – Payment service:         /api/payments/* is protected (token required).

Acceptance criteria (Task 1)
-----------------------------
AC1  Middleware behaves as expected across valid and invalid token scenarios.
AC2  Maintains security integrity with proper JSON error messaging.
AC3  Integration tests pass in at least three different expected service interactions.

Edge cases covered
------------------
- Security headers are validated (Content-Type: application/json on 401 responses).
- JSON Web Token errors (missing, expired, tampered) are handled gracefully.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
import pytest
from flask import Flask, jsonify, request

from src.middleware.TokenMiddleware import TokenMiddleware, _get_secret, _get_algorithm

# ---------------------------------------------------------------------------
# Shared helpers
# Helpers call _get_secret()/_get_algorithm() at call time so that any
# env-var changes made by other test modules during pytest collection do
# not silently corrupt the secret used here.
# ---------------------------------------------------------------------------


def _make_valid_token(
    user_id: str = "user-001",
    username: str = "alice",
    roles: list | None = None,
    expiry_minutes: int = 60,
) -> str:
    """Issue a signed JWT for integration testing."""
    if roles is None:
        roles = ["ROLE_USER"]
    now = datetime.now(tz=timezone.utc)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(minutes=expiry_minutes),
        "jti": f"jti-{username}-{expiry_minutes}",
    }
    return jwt.encode(payload, _get_secret(), algorithm=_get_algorithm())


def _make_expired_token() -> str:
    now = datetime.now(tz=timezone.utc)
    payload: Dict[str, Any] = {
        "sub": "user-001",
        "username": "alice",
        "roles": ["ROLE_USER"],
        "iat": now - timedelta(minutes=120),
        "exp": now - timedelta(minutes=60),
        "jti": "expired-jti-integration",
    }
    return jwt.encode(payload, _get_secret(), algorithm=_get_algorithm())


def _make_tampered_token() -> str:
    payload: Dict[str, Any] = {
        "sub": "user-001",
        "username": "alice",
        "roles": ["ROLE_USER"],
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=60),
        "jti": "tampered-jti-integration",
    }
    return jwt.encode(payload, "wrong-secret-key", algorithm=_get_algorithm())


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Service A – Authentication service fixture
#   Public paths: /health, /auth/login
#   Protected paths: /auth/profile
# ---------------------------------------------------------------------------


def _build_auth_service() -> Flask:
    """Simulate the Authentication microservice."""
    app = Flask("auth_service")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "auth"}), 200

    @app.post("/auth/login")
    def login():
        return jsonify({"token": "mock-token", "user": {"username": "alice"}}), 200

    @app.get("/auth/profile")
    def profile():
        payload = request.environ.get("jwt.payload", {})
        return jsonify({"username": payload.get("username")}), 200

    app.wsgi_app = TokenMiddleware(app.wsgi_app)  # type: ignore[assignment]
    return app


@pytest.fixture(scope="module")
def auth_service_client():
    app = _build_auth_service()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Service B – User service fixture
#   Protected: all routes require a valid JWT.
#   Public paths override: only /health is public.
# ---------------------------------------------------------------------------


def _build_user_service() -> Flask:
    """Simulate the User microservice."""
    app = Flask("user_service")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "user"}), 200

    @app.get("/api/users/me")
    def get_me():
        payload = request.environ.get("jwt.payload", {})
        return jsonify({"user_id": payload.get("sub"), "username": payload.get("username")}), 200

    @app.get("/api/users/<user_id>")
    def get_user(user_id: str):
        payload = request.environ.get("jwt.payload", {})
        return jsonify({"requested_by": payload.get("username"), "user_id": user_id}), 200

    # Only /health is public; all /api/users/* routes require auth.
    app.wsgi_app = TokenMiddleware(  # type: ignore[assignment]
        app.wsgi_app,
        public_paths=["/health"],
    )
    return app


@pytest.fixture(scope="module")
def user_service_client():
    app = _build_user_service()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Service C – Payment service fixture
#   Protected: all routes require a valid JWT.
#   Public paths override: only /health is public.
# ---------------------------------------------------------------------------


def _build_payment_service() -> Flask:
    """Simulate the Payment microservice."""
    app = Flask("payment_service")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "payment"}), 200

    @app.post("/api/payments")
    def create_payment():
        payload = request.environ.get("jwt.payload", {})
        data = request.get_json(silent=True) or {}
        return (
            jsonify(
                {
                    "payment_id": "pay-001",
                    "amount": data.get("amount"),
                    "initiated_by": payload.get("username"),
                }
            ),
            201,
        )

    @app.get("/api/payments/<payment_id>")
    def get_payment(payment_id: str):
        payload = request.environ.get("jwt.payload", {})
        return jsonify({"payment_id": payment_id, "requested_by": payload.get("username")}), 200

    app.wsgi_app = TokenMiddleware(  # type: ignore[assignment]
        app.wsgi_app,
        public_paths=["/health"],
    )
    return app


@pytest.fixture(scope="module")
def payment_service_client():
    app = _build_payment_service()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ===========================================================================
# Service A – Authentication service integration tests
# AC3 service interaction #1
# ===========================================================================


class TestAuthServiceInteraction:
    """Integration tests for the Authentication service."""

    def test_health_endpoint_is_public(self, auth_service_client):
        """GET /health does not require a token."""
        resp = auth_service_client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["service"] == "auth"

    def test_login_endpoint_is_public(self, auth_service_client):
        """POST /auth/login does not require a token (public path)."""
        resp = auth_service_client.post("/auth/login", json={"username": "alice", "password": "pass"})
        assert resp.status_code == 200

    def test_profile_endpoint_requires_valid_token(self, auth_service_client):
        """GET /auth/profile returns 401 without a token."""
        resp = auth_service_client.get("/auth/profile")
        assert resp.status_code == 401
        data = resp.get_json()
        assert "Authorization token is missing" in data["error"]

    def test_profile_endpoint_grants_access_with_valid_token(self, auth_service_client):
        """GET /auth/profile returns 200 and the decoded username."""
        token = _make_valid_token()
        resp = auth_service_client.get("/auth/profile", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.get_json()["username"] == "alice"

    def test_profile_endpoint_rejects_expired_token(self, auth_service_client):
        """Expired JWT returns 401 with a clear error message."""
        token = _make_expired_token()
        resp = auth_service_client.get("/auth/profile", headers=_auth_header(token))
        assert resp.status_code == 401
        assert "expired" in resp.get_json()["error"].lower()

    def test_profile_endpoint_rejects_tampered_token(self, auth_service_client):
        """Tampered JWT (wrong signature) returns 401."""
        token = _make_tampered_token()
        resp = auth_service_client.get("/auth/profile", headers=_auth_header(token))
        assert resp.status_code == 401
        assert "Invalid token" in resp.get_json()["error"]

    def test_401_responses_have_json_content_type(self, auth_service_client):
        """Security integrity: 401 error responses must carry JSON content-type."""
        resp = auth_service_client.get("/auth/profile")
        assert resp.status_code == 401
        assert "application/json" in resp.content_type

    def test_wrong_auth_scheme_returns_401(self, auth_service_client):
        """Basic auth scheme (not Bearer) is rejected."""
        resp = auth_service_client.get(
            "/auth/profile", headers={"Authorization": "Basic dXNlcjpwYXNz"}
        )
        assert resp.status_code == 401
        assert "Authorization token is missing" in resp.get_json()["error"]


# ===========================================================================
# Service B – User service integration tests
# AC3 service interaction #2
# ===========================================================================


class TestUserServiceInteraction:
    """Integration tests for the User microservice."""

    def test_health_endpoint_is_public(self, user_service_client):
        resp = user_service_client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["service"] == "user"

    def test_get_me_returns_user_info_with_valid_token(self, user_service_client):
        """GET /api/users/me returns decoded user info from JWT payload."""
        token = _make_valid_token(user_id="user-001", username="alice")
        resp = user_service_client.get("/api/users/me", headers=_auth_header(token))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_id"] == "user-001"
        assert data["username"] == "alice"

    def test_get_user_by_id_with_valid_token(self, user_service_client):
        """GET /api/users/<id> is accessible with a valid token."""
        token = _make_valid_token(username="alice")
        resp = user_service_client.get("/api/users/user-999", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.get_json()["user_id"] == "user-999"
        assert resp.get_json()["requested_by"] == "alice"

    def test_get_me_rejects_missing_token(self, user_service_client):
        """GET /api/users/me without token returns 401."""
        resp = user_service_client.get("/api/users/me")
        assert resp.status_code == 401
        assert "Authorization token is missing" in resp.get_json()["error"]

    def test_get_me_rejects_expired_token(self, user_service_client):
        """Expired token is rejected with 401."""
        token = _make_expired_token()
        resp = user_service_client.get("/api/users/me", headers=_auth_header(token))
        assert resp.status_code == 401
        assert "expired" in resp.get_json()["error"].lower()

    def test_admin_token_carries_admin_role(self, user_service_client):
        """JWT with ROLE_ADMIN is accepted and payload is accessible downstream."""
        token = _make_valid_token(
            user_id="user-002", username="admin", roles=["ROLE_ADMIN", "ROLE_USER"]
        )
        resp = user_service_client.get("/api/users/me", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.get_json()["username"] == "admin"

    def test_garbage_token_returns_401(self, user_service_client):
        """Completely malformed token returns 401."""
        resp = user_service_client.get(
            "/api/users/me", headers={"Authorization": "Bearer not.a.valid.jwt.here"}
        )
        assert resp.status_code == 401

    def test_401_error_body_is_valid_json(self, user_service_client):
        """Security integrity: 401 body must be valid JSON with an 'error' key."""
        resp = user_service_client.get("/api/users/me")
        assert resp.status_code == 401
        body = resp.get_json()
        assert body is not None
        assert "error" in body


# ===========================================================================
# Service C – Payment service integration tests
# AC3 service interaction #3
# ===========================================================================


class TestPaymentServiceInteraction:
    """Integration tests for the Payment microservice."""

    def test_health_endpoint_is_public(self, payment_service_client):
        resp = payment_service_client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["service"] == "payment"

    def test_create_payment_with_valid_token(self, payment_service_client):
        """POST /api/payments with a valid token succeeds."""
        token = _make_valid_token(username="alice")
        resp = payment_service_client.post(
            "/api/payments",
            json={"amount": 100.00},
            headers=_auth_header(token),
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["payment_id"] == "pay-001"
        assert data["initiated_by"] == "alice"

    def test_create_payment_without_token_returns_401(self, payment_service_client):
        """POST /api/payments without a token returns 401."""
        resp = payment_service_client.post(
            "/api/payments", json={"amount": 100.00}
        )
        assert resp.status_code == 401

    def test_create_payment_with_expired_token_returns_401(self, payment_service_client):
        """Expired token is rejected for payment creation."""
        token = _make_expired_token()
        resp = payment_service_client.post(
            "/api/payments",
            json={"amount": 50.00},
            headers=_auth_header(token),
        )
        assert resp.status_code == 401
        assert "expired" in resp.get_json()["error"].lower()

    def test_get_payment_with_valid_token(self, payment_service_client):
        """GET /api/payments/<id> is accessible with a valid token."""
        token = _make_valid_token(username="bob")
        resp = payment_service_client.get(
            "/api/payments/pay-123", headers=_auth_header(token)
        )
        assert resp.status_code == 200
        assert resp.get_json()["payment_id"] == "pay-123"
        assert resp.get_json()["requested_by"] == "bob"

    def test_get_payment_with_tampered_token_returns_401(self, payment_service_client):
        """Tampered token is rejected for payment retrieval."""
        token = _make_tampered_token()
        resp = payment_service_client.get(
            "/api/payments/pay-999", headers=_auth_header(token)
        )
        assert resp.status_code == 401
        assert "Invalid token" in resp.get_json()["error"]

    def test_401_responses_have_json_content_type(self, payment_service_client):
        """Security integrity: 401 responses carry Content-Type: application/json."""
        resp = payment_service_client.post("/api/payments", json={})
        assert resp.status_code == 401
        assert "application/json" in resp.content_type


# ===========================================================================
# Cross-service: middleware logging behaviour
# ===========================================================================


class TestMiddlewareLogging:
    """Verify that the middleware emits appropriate log records."""

    def test_successful_auth_is_logged_at_info(self, auth_service_client, caplog):
        token = _make_valid_token()
        with caplog.at_level(logging.INFO, logger="src.middleware.TokenMiddleware"):
            auth_service_client.get("/auth/profile", headers=_auth_header(token))
        assert any("authenticated" in record.message for record in caplog.records)

    def test_missing_token_is_logged_at_warning(self, auth_service_client, caplog):
        with caplog.at_level(logging.WARNING, logger="src.middleware.TokenMiddleware"):
            auth_service_client.get("/auth/profile")
        assert any("missing token" in record.message for record in caplog.records)

    def test_expired_token_is_logged_at_warning(self, auth_service_client, caplog):
        token = _make_expired_token()
        with caplog.at_level(logging.WARNING, logger="src.middleware.TokenMiddleware"):
            auth_service_client.get("/auth/profile", headers=_auth_header(token))
        assert any("expired token" in record.message for record in caplog.records)

    def test_invalid_token_is_logged_at_warning(self, auth_service_client, caplog):
        token = _make_tampered_token()
        with caplog.at_level(logging.WARNING, logger="src.middleware.TokenMiddleware"):
            auth_service_client.get("/auth/profile", headers=_auth_header(token))
        assert any("invalid token" in record.message for record in caplog.records)
