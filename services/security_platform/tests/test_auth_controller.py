"""test_auth_controller.py – Unit tests for the Security Platform AuthController.

Covers Task 2 acceptance criteria:
  AC1  AuthController is implemented in FastAPI.
  AC2  JWT tokens are issued and validated correctly.
  AC3  Unit and integration tests cover authentication flows.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.security_platform.main import app, _TOKEN_BLACKLIST
from services.security_platform.utils.jwt_util import validate_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_blacklist():
    """Reset token blacklist before each test."""
    _TOKEN_BLACKLIST.clear()
    yield
    _TOKEN_BLACKLIST.clear()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health check (AC1 – FastAPI app initialises correctly)
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "security-platform"


# ---------------------------------------------------------------------------
# AC2 – Login issues valid JWT tokens
# ---------------------------------------------------------------------------


def test_login_returns_200_and_token_for_valid_credentials(client):
    response = client.post("/auth/login", json={"username": "alice", "password": "alice_pass"})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "user" in data
    assert data["user"]["username"] == "alice"
    assert "ROLE_USER" in data["user"]["roles"]


def test_login_token_is_valid_jwt(client):
    response = client.post("/auth/login", json={"username": "alice", "password": "alice_pass"})
    token = response.json()["token"]
    payload = validate_token(token)
    assert payload["username"] == "alice"
    assert payload["sub"] == "user-001"
    assert "exp" in payload
    assert "jti" in payload


def test_login_admin_has_admin_role(client):
    response = client.post("/auth/login", json={"username": "admin", "password": "admin_pass"})
    assert response.status_code == 200
    data = response.json()
    assert "ROLE_ADMIN" in data["user"]["roles"]
    assert "ROLE_USER" in data["user"]["roles"]


def test_login_returns_401_for_wrong_password(client):
    response = client.post("/auth/login", json={"username": "alice", "password": "wrong"})
    assert response.status_code == 401
    assert "Invalid" in response.json()["detail"]


def test_login_returns_401_for_unknown_user(client):
    response = client.post("/auth/login", json={"username": "nobody", "password": "pass"})
    assert response.status_code == 401


def test_login_returns_422_for_missing_fields(client):
    response = client.post("/auth/login", json={"username": "alice"})
    assert response.status_code == 422


def test_login_returns_422_for_empty_body(client):
    response = client.post("/auth/login", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# AC2 – Token validation: middleware enforces auth on protected routes
# ---------------------------------------------------------------------------


def test_logout_requires_valid_token(client):
    response = client.post("/auth/logout")
    assert response.status_code == 401


def test_logout_with_expired_token_returns_401(client):
    from datetime import datetime, timedelta, timezone
    import jwt
    from services.security_platform.utils.jwt_util import _get_secret, _get_algorithm

    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": "user-001",
        "username": "alice",
        "roles": ["ROLE_USER"],
        "iat": now - timedelta(minutes=120),
        "exp": now - timedelta(minutes=60),
        "jti": "old-jti",
    }
    expired_token = jwt.encode(payload, _get_secret(), algorithm=_get_algorithm())
    response = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401
    assert "expired" in response.json()["error"].lower()


def test_logout_with_tampered_token_returns_401(client):
    import jwt
    from datetime import datetime, timedelta, timezone

    payload = {
        "sub": "user-001",
        "username": "alice",
        "roles": ["ROLE_USER"],
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=60),
        "jti": "bad-jti",
    }
    bad_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
    response = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {bad_token}"}
    )
    assert response.status_code == 401


def test_logout_succeeds_with_valid_token(client):
    # First, login to get a token.
    login_resp = client.post(
        "/auth/login", json={"username": "alice", "password": "alice_pass"}
    )
    token = login_resp.json()["token"]

    response = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Successfully logged out"


# ---------------------------------------------------------------------------
# AC3 – Token uniqueness (each login produces a distinct token)
# ---------------------------------------------------------------------------


def test_each_login_produces_unique_token(client):
    r1 = client.post("/auth/login", json={"username": "alice", "password": "alice_pass"})
    r2 = client.post("/auth/login", json={"username": "alice", "password": "alice_pass"})
    assert r1.json()["token"] != r2.json()["token"]
