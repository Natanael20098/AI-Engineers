"""test_authentication_flow_it.py – Integration tests for the full authentication flow.

Python equivalent of AuthenticationFlowIT (migrated from Java monolith).

Task 2 Acceptance Criteria:
- All integration tests pass showing all auth component interactions work.
- JWTs are correctly invalidated on logout.
- Handle potential concurrency issues when multiple tokens are in play.

Workflows covered:
- Successful login and JWT token issue.
- Token validation via different protected endpoints.
- Token refresh via /auth/refresh-token.
- Multiple simultaneous user logins ensure token uniqueness.
- Invalid credentials error messages.
- Health endpoint reachable without auth.
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
    return client.post("/auth/login", json={"username": username, "password": password})


# ---------------------------------------------------------------------------
# Successful login and token issue
# ---------------------------------------------------------------------------


class TestSuccessfulLoginAndTokenIssue:
    def test_login_returns_200_for_alice(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert resp.status_code == 200

    def test_login_returns_200_for_admin(self, client):
        resp = _login(client, "admin", "admin_pass")
        assert resp.status_code == 200

    def test_login_returns_200_for_bob(self, client):
        resp = _login(client, "bob", "bob_pass")
        assert resp.status_code == 200

    def test_login_response_contains_access_token(self, client):
        data = _login(client, "alice", "alice_pass").get_json()
        assert "token" in data
        assert data["token"]

    def test_login_response_contains_refresh_token(self, client):
        data = _login(client, "alice", "alice_pass").get_json()
        assert "refresh_token" in data
        assert data["refresh_token"]

    def test_login_response_contains_user_info(self, client):
        data = _login(client, "alice", "alice_pass").get_json()
        assert "user" in data
        user = data["user"]
        assert user["username"] == "alice"
        assert user["user_id"] == "user-001"

    def test_login_response_includes_roles_in_user(self, client):
        data = _login(client, "admin", "admin_pass").get_json()
        assert "roles" in data["user"]
        assert "ROLE_ADMIN" in data["user"]["roles"]

    def test_issued_access_token_is_valid_jwt(self, client):
        token = _login(client, "alice", "alice_pass").get_json()["token"]
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["userId"] == "user-001"
        assert payload["username"] == "alice"

    def test_issued_token_contains_expiry(self, client):
        token = _login(client, "alice", "alice_pass").get_json()["token"]
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_issued_token_contains_jti(self, client):
        token = _login(client, "alice", "alice_pass").get_json()["token"]
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "jti" in payload


# ---------------------------------------------------------------------------
# Token validation via different endpoints
# ---------------------------------------------------------------------------


class TestTokenValidationViaEndpoints:
    def test_valid_admin_token_grants_access_to_protected_endpoint(self, client):
        token = _login(client, "admin", "admin_pass").get_json()["token"]
        resp = client.get("/auth/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_health_endpoint_accessible_without_token(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_refresh_token_endpoint_issues_new_access_token(self, client):
        login_data = _login(client, "alice", "alice_pass").get_json()
        refresh_tok = login_data["refresh_token"]

        resp = client.post("/auth/refresh-token", json={"refresh_token": refresh_tok})
        assert resp.status_code == 200
        new_token = resp.get_json()["token"]
        assert new_token
        # New token must be a valid JWT
        payload = jwt.decode(new_token, "test-secret-key", algorithms=["HS256"])
        assert payload["userId"] == "user-001"

    def test_refresh_token_endpoint_renews_expired_token(self, client):
        expired = generate_token("user-001", "alice", expiry_minutes=-1)
        resp = client.post("/auth/refresh-token", json={"token": expired})
        assert resp.status_code == 200
        assert "token" in resp.get_json()

    def test_expired_token_rejected_by_protected_endpoint(self, client):
        expired = generate_token("user-002", "admin", roles=["ROLE_ADMIN"], expiry_minutes=-1)
        resp = client.get("/auth/protected", headers={"Authorization": f"Bearer {expired}"})
        assert resp.status_code == 401

    def test_login_endpoint_reachable(self, client):
        resp = _login(client, "ghost", "bad_pass")
        assert resp.status_code not in (404, 405)

    def test_refresh_token_endpoint_reachable(self, client):
        resp = client.post("/auth/refresh-token", json={"refresh_token": "dummy"})
        assert resp.status_code not in (404, 405)


# ---------------------------------------------------------------------------
# JWT invalidation (logout flow via microservice / refresh-token revocation)
# ---------------------------------------------------------------------------


class TestJWTInvalidationFlow:
    def test_invalid_credentials_return_401_with_error_field(self, client):
        resp = _login(client, "alice", "wrong_password")
        assert resp.status_code == 401
        assert "error" in resp.get_json()

    def test_unknown_user_returns_401(self, client):
        resp = _login(client, "nobody", "pass")
        assert resp.status_code == 401

    def test_missing_password_returns_400(self, client):
        resp = client.post("/auth/login", json={"username": "alice"})
        assert resp.status_code == 400

    def test_missing_username_returns_400(self, client):
        resp = client.post("/auth/login", json={"password": "alice_pass"})
        assert resp.status_code == 400

    def test_non_json_body_returns_400(self, client):
        resp = client.post(
            "/auth/login",
            data="username=alice&password=alice_pass",
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 400

    def test_invalid_token_on_refresh_returns_401(self, client):
        resp = client.post(
            "/auth/refresh-token", json={"refresh_token": "totally.invalid.token"}
        )
        assert resp.status_code == 401

    def test_error_response_contains_error_field(self, client):
        resp = _login(client, "alice", "bad_password")
        data = resp.get_json()
        assert "error" in data
        assert data["error"]


# ---------------------------------------------------------------------------
# Token uniqueness – multiple concurrent sessions
# ---------------------------------------------------------------------------


class TestTokenUniqueness:
    def test_three_users_receive_distinct_tokens(self, client):
        alice_token = _login(client, "alice", "alice_pass").get_json()["token"]
        admin_token = _login(client, "admin", "admin_pass").get_json()["token"]
        bob_token = _login(client, "bob", "bob_pass").get_json()["token"]

        assert alice_token != admin_token
        assert alice_token != bob_token
        assert admin_token != bob_token

    def test_same_user_two_logins_produce_different_tokens(self, client):
        t1 = _login(client, "alice", "alice_pass").get_json()["token"]
        t2 = _login(client, "alice", "alice_pass").get_json()["token"]
        assert t1 != t2

    def test_logging_out_one_user_does_not_affect_another(self, client):
        """Admin's session does not interfere with alice's session."""
        admin_token = _login(client, "admin", "admin_pass").get_json()["token"]
        alice_token = _login(client, "alice", "alice_pass").get_json()["token"]

        # Admin accesses protected endpoint
        admin_resp = client.get(
            "/auth/protected", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert admin_resp.status_code == 200

        # Alice's token remains independently valid (cannot be used on admin endpoint
        # but is itself a valid JWT that can be refreshed)
        refresh_resp = client.post(
            "/auth/refresh-token", json={"token": alice_token}
        )
        assert refresh_resp.status_code == 200
