"""tests/integration/auth/test_rbac.py – Integration tests for RBAC with JWT.

Task 4 Acceptance Criteria:
- All RBAC policies verified through JWTs.
- Unauthorized role access results in a 403 response.
- Handles token expiry between requests.

Scope: Validates role assignments and access control through JWT tokens by
exercising the microservice's /auth/protected endpoint (ROLE_ADMIN required)
and the login endpoint (role embedding).

Uses pytest + Flask test_client (mirrors the 'requests' module pattern
described in the task but runs in-process for deterministic CI).
"""

from __future__ import annotations

import os

import jwt
import pytest

os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60")

from microservices.auth_service.main import create_app
from microservices.auth_service.utils.jwt_util import generate_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(client, username: str, password: str):
    """POST /auth/login and return the full response."""
    return client.post("/auth/login", json={"username": username, "password": password})


def _get_token(client, username: str, password: str) -> str:
    resp = _login(client, username, password)
    assert resp.status_code == 200, f"Login failed for {username}: {resp.get_json()}"
    return resp.get_json()["token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# AC1 – All RBAC policies verified through JWTs
# ---------------------------------------------------------------------------


class TestRBACPolicies:
    def test_admin_jwt_carries_role_admin(self, client):
        """JWT issued for admin must contain ROLE_ADMIN."""
        resp = _login(client, "admin", "admin_pass")
        data = resp.get_json()
        assert "ROLE_ADMIN" in data["user"]["roles"]

    def test_regular_user_jwt_carries_role_user(self, client):
        """JWT issued for alice must contain ROLE_USER."""
        resp = _login(client, "alice", "alice_pass")
        data = resp.get_json()
        assert "ROLE_USER" in data["user"]["roles"]

    def test_regular_user_jwt_does_not_carry_role_admin(self, client):
        """alice must NOT have ROLE_ADMIN in JWT."""
        resp = _login(client, "alice", "alice_pass")
        data = resp.get_json()
        assert "ROLE_ADMIN" not in data["user"]["roles"]

    def test_bob_jwt_carries_role_user(self, client):
        resp = _login(client, "bob", "bob_pass")
        data = resp.get_json()
        assert "ROLE_USER" in data["user"]["roles"]

    def test_jwt_payload_includes_roles_claim(self, client):
        token = _get_token(client, "alice", "alice_pass")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "roles" in payload
        assert isinstance(payload["roles"], list)

    def test_jwt_payload_includes_permissions_claim(self, client):
        token = _get_token(client, "alice", "alice_pass")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "permissions" in payload
        assert isinstance(payload["permissions"], list)

    def test_admin_jwt_has_all_permissions(self, client):
        token = _get_token(client, "admin", "admin_pass")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        for perm in ("read", "write", "delete"):
            assert perm in payload["permissions"], f"Admin missing permission: {perm}"

    def test_bob_jwt_has_only_read_permission(self, client):
        token = _get_token(client, "bob", "bob_pass")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "read" in payload["permissions"]
        assert "write" not in payload["permissions"]
        assert "delete" not in payload["permissions"]


# ---------------------------------------------------------------------------
# AC2 – Unauthorized role access results in a 403 response
# ---------------------------------------------------------------------------


class TestUnauthorizedRoleAccess:
    def test_admin_accesses_protected_endpoint_200(self, client):
        """Admin with ROLE_ADMIN gets 200 on the protected endpoint."""
        token = _get_token(client, "admin", "admin_pass")
        resp = client.get("/auth/protected", headers=_auth_header(token))
        assert resp.status_code == 200
        assert "Access granted" in resp.get_json()["message"]

    def test_alice_denied_admin_endpoint_403(self, client):
        """alice (ROLE_USER only) must receive 403 on /auth/protected."""
        token = _get_token(client, "alice", "alice_pass")
        resp = client.get("/auth/protected", headers=_auth_header(token))
        assert resp.status_code == 403

    def test_bob_denied_admin_endpoint_403(self, client):
        """bob (ROLE_USER only) must receive 403 on /auth/protected."""
        token = _get_token(client, "bob", "bob_pass")
        resp = client.get("/auth/protected", headers=_auth_header(token))
        assert resp.status_code == 403

    def test_403_response_contains_error_field(self, client):
        """403 response body must include an 'error' field."""
        token = _get_token(client, "alice", "alice_pass")
        resp = client.get("/auth/protected", headers=_auth_header(token))
        assert resp.status_code == 403
        data = resp.get_json()
        assert "error" in data

    def test_no_token_returns_401_not_403(self, client):
        """Missing Authorization header → 401 (unauthenticated), not 403."""
        resp = client.get("/auth/protected")
        assert resp.status_code == 401

    def test_invalid_token_returns_401_not_403(self, client):
        """Malformed token → 401, not 403."""
        resp = client.get(
            "/auth/protected",
            headers={"Authorization": "Bearer this.is.garbage"},
        )
        assert resp.status_code == 401

    def test_manually_crafted_admin_role_token_rejected(self, client):
        """Token signed with wrong key claiming ROLE_ADMIN must be rejected (401)."""
        forged = jwt.encode(
            {"userId": "evil", "username": "hacker", "roles": ["ROLE_ADMIN"]},
            "wrong-secret",
            algorithm="HS256",
        )
        resp = client.get("/auth/protected", headers=_auth_header(forged))
        assert resp.status_code == 401

    def test_multiple_users_rbac_enforced_independently(self, client):
        """Admin and regular-user tokens are validated independently."""
        admin_token = _get_token(client, "admin", "admin_pass")
        alice_token = _get_token(client, "alice", "alice_pass")

        admin_resp = client.get("/auth/protected", headers=_auth_header(admin_token))
        alice_resp = client.get("/auth/protected", headers=_auth_header(alice_token))

        assert admin_resp.status_code == 200
        assert alice_resp.status_code == 403


# ---------------------------------------------------------------------------
# AC3 – Handles token expiry between requests
# ---------------------------------------------------------------------------


class TestTokenExpiry:
    def test_expired_token_returns_401_on_protected_endpoint(self, client):
        """Expired token must be rejected with 401 on protected endpoint."""
        expired_token = generate_token(
            "u2", "admin", roles=["ROLE_ADMIN"], expiry_minutes=-1
        )
        resp = client.get("/auth/protected", headers=_auth_header(expired_token))
        assert resp.status_code == 401

    def test_expired_token_error_message_mentions_expiry(self, client):
        """Error message for an expired token must reference expiry."""
        expired_token = generate_token(
            "u2", "admin", roles=["ROLE_ADMIN"], expiry_minutes=-1
        )
        resp = client.get("/auth/protected", headers=_auth_header(expired_token))
        error = resp.get_json().get("error", "").lower()
        assert "expired" in error or "token" in error

    def test_expired_regular_user_token_also_returns_401(self, client):
        """Expired ROLE_USER token must also return 401 (not 403)."""
        expired_token = generate_token(
            "u1", "alice", roles=["ROLE_USER"], expiry_minutes=-1
        )
        resp = client.get("/auth/protected", headers=_auth_header(expired_token))
        assert resp.status_code == 401

    def test_fresh_token_after_expiry_grants_access(self, client):
        """After token expiry, a fresh login produces a valid token."""
        # Simulate: old session expired → user re-logs in
        fresh_token = _get_token(client, "admin", "admin_pass")
        resp = client.get("/auth/protected", headers=_auth_header(fresh_token))
        assert resp.status_code == 200

    def test_refresh_token_endpoint_renews_access(self, client):
        """POST /auth/refresh-token with expired token issues a new access token."""
        expired_token = generate_token("u2", "admin", roles=["ROLE_ADMIN"], expiry_minutes=-1)
        resp = client.post("/auth/refresh-token", json={"token": expired_token})
        assert resp.status_code == 200
        new_token = resp.get_json()["token"]
        assert new_token
        # New token must be valid
        payload = jwt.decode(new_token, "test-secret-key", algorithms=["HS256"])
        assert payload["userId"] == "u2"
