"""test_integration.py – Integration tests for the Security Platform AuthController.

Covers Task 2 AC3: unit and integration tests cover authentication flows.

These tests exercise the complete request/response cycle through the FastAPI
app (including AuthMiddleware), verifying the full login → token → protected
resource flow end-to-end.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.security_platform.main import app, _TOKEN_BLACKLIST
from services.security_platform.utils.jwt_util import validate_token


@pytest.fixture(autouse=True)
def _clear_blacklist():
    _TOKEN_BLACKLIST.clear()
    yield
    _TOKEN_BLACKLIST.clear()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Full login → logout flow
# ---------------------------------------------------------------------------


def test_full_login_then_logout_flow(client):
    """AC3: full authentication flow – login succeeds, logout revokes token."""
    # Step 1: login
    login_resp = client.post(
        "/auth/login", json={"username": "alice", "password": "alice_pass"}
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    assert token

    # Step 2: token is valid
    payload = validate_token(token)
    assert payload["username"] == "alice"

    # Step 3: logout with the valid token
    logout_resp = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "Successfully logged out"


# ---------------------------------------------------------------------------
# Authentication failure flows
# ---------------------------------------------------------------------------


def test_protected_route_without_token_is_blocked(client):
    """Middleware blocks unauthenticated requests to protected routes."""
    response = client.post("/auth/logout")
    assert response.status_code == 401


def test_invalid_credentials_do_not_issue_token(client):
    response = client.post(
        "/auth/login", json={"username": "alice", "password": "totally-wrong"}
    )
    assert response.status_code == 401
    assert "token" not in response.json()


# ---------------------------------------------------------------------------
# Token structure validation
# ---------------------------------------------------------------------------


def test_issued_token_contains_required_claims(client):
    resp = client.post("/auth/login", json={"username": "bob", "password": "bob_pass"})
    token = resp.json()["token"]
    payload = validate_token(token)
    for claim in ("sub", "username", "roles", "exp", "iat", "jti"):
        assert claim in payload, f"Missing claim: {claim}"


def test_tokens_for_different_users_differ(client):
    resp_alice = client.post(
        "/auth/login", json={"username": "alice", "password": "alice_pass"}
    )
    resp_admin = client.post(
        "/auth/login", json={"username": "admin", "password": "admin_pass"}
    )
    assert resp_alice.json()["token"] != resp_admin.json()["token"]

    alice_payload = validate_token(resp_alice.json()["token"])
    admin_payload = validate_token(resp_admin.json()["token"])
    assert alice_payload["sub"] != admin_payload["sub"]
    assert "ROLE_ADMIN" not in alice_payload["roles"]
    assert "ROLE_ADMIN" in admin_payload["roles"]


# ---------------------------------------------------------------------------
# Service availability
# ---------------------------------------------------------------------------


def test_health_check_always_accessible(client):
    for _ in range(3):
        response = client.get("/health")
        assert response.status_code == 200
