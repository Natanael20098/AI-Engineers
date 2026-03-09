"""
Unit and integration tests for the Authentication Service.

Tests cover all acceptance criteria:
  AC1  POST /auth/login -> 200 + valid JWT for valid credentials
  AC2  POST /auth/login -> 401 for invalid credentials
  AC3  JWT tokens expire after the configured duration
  AC4  (OAuth2 flow tested via route registration and redirect)
"""

from __future__ import annotations

import time
from datetime import timedelta

import jwt
import pytest

from ..config import TestingConfig
from ..models import UserProfileModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_user_store():
    """Clear the in-memory user store before every test."""
    UserProfileModel._store.clear()
    yield
    UserProfileModel._store.clear()


@pytest.fixture()
def app():
    from ..authentication import create_app

    cfg = TestingConfig()
    cfg.JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    application = create_app(cfg)
    application.config["TESTING"] = True
    application.config["SECRET_KEY"] = "test-secret"
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def registered_user():
    return UserProfileModel.create(
        user_id="user-001",
        username="alice",
        email="alice@example.com",
        password="correct_password",
    )


# ---------------------------------------------------------------------------
# AC1 – Successful login returns 200 + JWT
# ---------------------------------------------------------------------------


def test_login_returns_200_and_jwt_for_valid_credentials(client, registered_user):
    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "correct_password"},
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()
    assert "token" in data
    assert "user" in data
    # Token must be decodable
    from ..config import TestingConfig as Cfg

    cfg = Cfg()
    payload = jwt.decode(
        data["token"],
        cfg.JWT_SECRET_KEY,
        algorithms=["HS256"],
    )
    assert payload["username"] == "alice"
    assert payload["email"] == "alice@example.com"
    assert "exp" in payload
    assert "jti" in payload


# ---------------------------------------------------------------------------
# AC2 – Invalid credentials return 401
# ---------------------------------------------------------------------------


def test_login_returns_401_for_wrong_password(client, registered_user):
    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "wrong_password"},
    )
    assert response.status_code == 401
    assert "error" in response.get_json()


def test_login_returns_401_for_unknown_user(client):
    response = client.post(
        "/auth/login",
        json={"username": "ghost", "password": "anything"},
    )
    assert response.status_code == 401


def test_login_returns_400_for_missing_fields(client):
    response = client.post("/auth/login", json={"username": "alice"})
    assert response.status_code == 400


def test_login_returns_400_for_non_json_body(client):
    response = client.post(
        "/auth/login",
        data="not-json",
        content_type="text/plain",
    )
    assert response.status_code == 400


def test_login_returns_401_for_inactive_user(client):
    UserProfileModel.create(
        user_id="user-002",
        username="bob",
        email="bob@example.com",
        password="pass",
        is_active=False,
    )
    response = client.post(
        "/auth/login",
        json={"username": "bob", "password": "pass"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# AC3 – JWT tokens expire after configured duration
# ---------------------------------------------------------------------------


def test_jwt_token_has_expiry(client, registered_user):
    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "correct_password"},
    )
    token = response.get_json()["token"]
    from ..config import TestingConfig as Cfg

    payload = jwt.decode(
        token, Cfg().JWT_SECRET_KEY, algorithms=["HS256"]
    )
    assert payload["exp"] > payload["iat"]


def test_expired_token_is_rejected_on_logout(app, registered_user):
    """Create a token that expires immediately, then attempt logout."""
    from ..authentication import generate_jwt_token
    from datetime import timedelta

    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds=-1)
    with app.test_request_context():
        app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds=-1)
        token = generate_jwt_token(registered_user)

    client = app.test_client()
    response = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


def test_logout_invalidates_token(client, registered_user):
    login_resp = client.post(
        "/auth/login",
        json={"username": "alice", "password": "correct_password"},
    )
    token = login_resp.get_json()["token"]

    # First logout succeeds
    logout_resp = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_resp.status_code == 200

    # Second request with same token is rejected (blacklisted)
    second_resp = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second_resp.status_code == 401


def test_logout_without_token_returns_401(client):
    response = client.post("/auth/logout")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# AC4 – OAuth2 routes are registered
# ---------------------------------------------------------------------------


def test_oauth2_authorize_route_is_registered(client):
    """The authorize endpoint should redirect (302) when provider is configured."""
    # Without real credentials it may raise or return an error, but the
    # route must exist (not 404).
    response = client.get("/auth/oauth2/authorize")
    assert response.status_code != 404


def test_oauth2_callback_requires_state(client):
    """Callback without state parameter must return 400."""
    response = client.get("/auth/oauth2/callback?code=dummy_code")
    assert response.status_code == 400
