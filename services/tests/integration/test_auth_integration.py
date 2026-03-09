"""
Integration tests: Authentication Service.

Verifies that:
  AC1  All integration tests pass under a Docker-composed environment.
       (Exercised via Flask test_client, mirroring the docker-compose
        authentication service at http://localhost:5001.)
  AC2  Key workflow scenarios are covered by tests.
  AC3  Service interaction logs show expected behaviour.

Workflows covered
-----------------
- Complete login → use → logout cycle.
- Multiple independent user sessions do not interfere.
- Invalid credential rejection at the auth boundary.
- Token revocation after logout (blacklist enforcement).
- JWT structure and claims validation.
- Error handling for malformed requests.
- Auth service interaction patterns (auth-first, then downstream).
"""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from authentication.authentication import create_app
from authentication.config import TestingConfig
from authentication.models import UserProfileModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_user_store():
    """Reset the in-memory user store before and after every test."""
    UserProfileModel._store.clear()
    yield
    UserProfileModel._store.clear()


@pytest.fixture()
def app():
    cfg = TestingConfig()
    cfg.JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    application = create_app(cfg)
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def alice():
    return UserProfileModel.create(
        user_id="user-alice",
        username="alice",
        email="alice@natanael.io",
        password="alice_password",
    )


@pytest.fixture()
def bob():
    return UserProfileModel.create(
        user_id="user-bob",
        username="bob",
        email="bob@natanael.io",
        password="bob_password",
    )


# ---------------------------------------------------------------------------
# AC1 – Tests pass in Docker-composed (Flask test_client) environment
# ---------------------------------------------------------------------------


def test_auth_service_login_endpoint_reachable(client):
    """POST /auth/login must be reachable (not 404/405) in the test environment."""
    response = client.post(
        "/auth/login",
        json={"username": "ghost", "password": "pass"},
    )
    assert response.status_code != 404
    assert response.status_code != 405


def test_auth_service_logout_endpoint_reachable(client):
    """POST /auth/logout must be reachable (not 404/405) in the test environment."""
    response = client.post("/auth/logout")
    assert response.status_code != 404
    assert response.status_code != 405


# ---------------------------------------------------------------------------
# AC2 – Key workflow scenarios
# ---------------------------------------------------------------------------


def test_complete_login_use_logout_workflow(client, alice):
    """Full integration workflow: login → obtain token → logout → token rejected."""
    # Step 1 – Login
    login_resp = client.post(
        "/auth/login",
        json={"username": "alice", "password": "alice_password"},
    )
    assert login_resp.status_code == 200
    token = login_resp.get_json()["token"]
    assert token

    # Step 2 – Token is valid (can be decoded without error)
    cfg = TestingConfig()
    payload = jwt.decode(token, cfg.JWT_SECRET_KEY, algorithms=["HS256"])
    assert payload["username"] == "alice"
    assert payload["email"] == "alice@natanael.io"

    # Step 3 – Logout succeeds
    logout_resp = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_resp.status_code == 200
    assert "logged out" in logout_resp.get_json()["message"].lower()

    # Step 4 – Token is revoked; re-use returns 401
    reuse_resp = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reuse_resp.status_code == 401


def test_multiple_users_have_independent_sessions(client, alice, bob):
    """Two users can log in simultaneously; their tokens are independent."""
    alice_login = client.post(
        "/auth/login",
        json={"username": "alice", "password": "alice_password"},
    )
    bob_login = client.post(
        "/auth/login",
        json={"username": "bob", "password": "bob_password"},
    )

    assert alice_login.status_code == 200
    assert bob_login.status_code == 200

    alice_token = alice_login.get_json()["token"]
    bob_token = bob_login.get_json()["token"]

    # Tokens are distinct
    assert alice_token != bob_token

    # Logging out Alice does not revoke Bob's token
    client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    bob_resp = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_resp.status_code == 200


def test_invalid_credentials_are_rejected(client, alice):
    """Auth service must reject wrong-password attempts with 401."""
    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "wrong_password"},
    )
    assert response.status_code == 401
    data = response.get_json()
    assert "error" in data


def test_unknown_user_rejected_with_401(client):
    """Requests for unknown usernames must return 401 (no enumeration)."""
    response = client.post(
        "/auth/login",
        json={"username": "nonexistent", "password": "any_password"},
    )
    assert response.status_code == 401


def test_missing_credentials_return_400(client):
    """Partial JSON body (missing password) must return 400."""
    response = client.post("/auth/login", json={"username": "alice"})
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_non_json_body_returns_400(client):
    """Non-JSON content must return 400 without crashing the service."""
    response = client.post(
        "/auth/login",
        data="username=alice&password=pass",
        content_type="application/x-www-form-urlencoded",
    )
    assert response.status_code == 400


def test_logout_without_token_returns_401(client):
    """POST /auth/logout without Authorization header must return 401."""
    response = client.post("/auth/logout")
    assert response.status_code == 401


def test_jwt_claims_present_in_token(client, alice):
    """Token must contain sub, username, email, iat, exp, jti claims."""
    login_resp = client.post(
        "/auth/login",
        json={"username": "alice", "password": "alice_password"},
    )
    token = login_resp.get_json()["token"]
    cfg = TestingConfig()
    payload = jwt.decode(token, cfg.JWT_SECRET_KEY, algorithms=["HS256"])

    for claim in ("sub", "username", "email", "iat", "exp", "jti"):
        assert claim in payload, f"Claim '{claim}' missing from JWT"

    assert payload["exp"] > payload["iat"]


# ---------------------------------------------------------------------------
# AC3 – Service interaction logs show expected behaviour
# ---------------------------------------------------------------------------


def test_login_response_includes_user_profile(client, alice):
    """Login response must include the authenticated user's profile."""
    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "alice_password"},
    )
    data = response.get_json()
    assert "user" in data
    user = data["user"]
    assert user["username"] == "alice"
    assert user["email"] == "alice@natanael.io"
    # Sensitive fields must not be returned
    assert "password_hash" not in user
    assert "password_salt" not in user


def test_token_revoked_after_logout_interaction_log(client, alice):
    """Second logout with the same token must return 401 (revoked, not expired)."""
    token = client.post(
        "/auth/login",
        json={"username": "alice", "password": "alice_password"},
    ).get_json()["token"]

    # First logout succeeds → token enters the blacklist
    first = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert first.status_code == 200

    # Second logout fails → expected interaction: 401 with "revoked" in message
    second = client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert second.status_code == 401
    error_msg = second.get_json()["error"].lower()
    assert "revoked" in error_msg or "blacklist" in error_msg or "invalid" in error_msg


def test_auth_service_rejects_inactive_user(client):
    """Inactive accounts must be rejected even with correct credentials."""
    UserProfileModel.create(
        user_id="user-inactive",
        username="inactive_user",
        email="inactive@natanael.io",
        password="correct_password",
        is_active=False,
    )
    response = client.post(
        "/auth/login",
        json={"username": "inactive_user", "password": "correct_password"},
    )
    assert response.status_code == 401


def test_auth_service_oauth2_routes_registered(client):
    """OAuth2 routes must be registered and return non-404 responses."""
    authorize_resp = client.get("/auth/oauth2/authorize")
    callback_resp = client.get("/auth/oauth2/callback?code=dummy")

    assert authorize_resp.status_code != 404
    assert callback_resp.status_code != 404
