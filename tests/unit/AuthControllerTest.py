"""AuthControllerTest.py – Unit tests for AuthController.

Covers all critical methods of the AuthController Flask Blueprint:

  health()   – GET /health
  login()    – POST /auth/login
  logout()   – POST /auth/logout

Acceptance criteria (Task 2)
-----------------------------
AC1  All critical methods have test coverage > 85%.
AC2  Tests pass for all typical and edge-case scenarios.
AC3  Code coverage report generated and included in CI logs
     (enforced via pytest-cov; see pyproject.toml addopts).

Edge cases covered
------------------
- Request payloads with missing, null, empty, and excessively long fields.
- Malicious-input strings (SQL injection fragments, script tags).
- Token expiration and tampered/invalid token handling.
- Re-use of a revoked (blacklisted) JWT after logout.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
import pytest

from src.controllers.AuthController import (
    _TOKEN_BLACKLIST,
    _generate_token,
    _get_algorithm,
    _get_secret,
    _verify_credentials,
    _get_user_roles,
    _validate_token,
    auth_controller,
    create_app,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_blacklist():
    """Reset the in-memory token blacklist before and after every test."""
    _TOKEN_BLACKLIST.clear()
    yield
    _TOKEN_BLACKLIST.clear()


@pytest.fixture(scope="module")
def app():
    """Flask test application with AuthController and TokenMiddleware wired."""
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(client, username: str, password: str):
    return client.post("/auth/login", json={"username": username, "password": password})


def _get_token(client, username: str = "alice", password: str = "alice_pass") -> str:
    resp = _login(client, username, password)
    assert resp.status_code == 200
    return resp.get_json()["token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_expired_token(username: str = "alice") -> str:
    now = datetime.now(tz=timezone.utc)
    payload: Dict[str, Any] = {
        "sub": "user-001",
        "username": username,
        "roles": ["ROLE_USER"],
        "iat": now - timedelta(minutes=120),
        "exp": now - timedelta(minutes=60),
        "jti": "expired-jti-unit",
    }
    return jwt.encode(payload, _get_secret(), algorithm=_get_algorithm())


def _make_tampered_token() -> str:
    payload: Dict[str, Any] = {
        "sub": "user-001",
        "username": "alice",
        "roles": ["ROLE_USER"],
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=60),
        "jti": "tampered-jti-unit",
    }
    return jwt.encode(payload, "completely-wrong-secret", algorithm="HS256")


# ===========================================================================
# GET /health
# ===========================================================================


class TestHealth:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_status_ok(self, client):
        resp = client.get("/health")
        assert resp.get_json()["status"] == "ok"

    def test_returns_correct_service_name(self, client):
        resp = client.get("/health")
        assert resp.get_json()["service"] == "auth-controller"

    def test_accessible_without_token(self, client):
        """Health check must be reachable with no Authorization header."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_json_content_type(self, client):
        resp = client.get("/health")
        assert "application/json" in resp.content_type


# ===========================================================================
# POST /auth/login – typical success paths
# ===========================================================================


class TestLoginSuccess:
    def test_valid_alice_credentials_return_200(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert resp.status_code == 200

    def test_valid_admin_credentials_return_200(self, client):
        resp = _login(client, "admin", "admin_pass")
        assert resp.status_code == 200

    def test_valid_bob_credentials_return_200(self, client):
        resp = _login(client, "bob", "bob_pass")
        assert resp.status_code == 200

    def test_response_contains_token_field(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert "token" in resp.get_json()

    def test_response_contains_user_field(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert "user" in resp.get_json()

    def test_token_is_a_string(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert isinstance(resp.get_json()["token"], str)

    def test_token_is_decodable_jwt(self, client):
        """Issued token must be a valid, decodable HS256 JWT."""
        resp = _login(client, "alice", "alice_pass")
        token = resp.get_json()["token"]
        payload = jwt.decode(token, _get_secret(), algorithms=[_get_algorithm()])
        assert payload["sub"] == "user-001"
        assert payload["username"] == "alice"

    def test_token_contains_required_claims(self, client):
        resp = _login(client, "alice", "alice_pass")
        payload = jwt.decode(
            resp.get_json()["token"], _get_secret(), algorithms=[_get_algorithm()]
        )
        for claim in ("sub", "username", "roles", "exp", "iat", "jti"):
            assert claim in payload, f"Missing claim: {claim}"

    def test_token_expiry_is_in_the_future(self, client):
        resp = _login(client, "alice", "alice_pass")
        payload = jwt.decode(
            resp.get_json()["token"], _get_secret(), algorithms=[_get_algorithm()]
        )
        assert payload["exp"] > datetime.now(tz=timezone.utc).timestamp()

    def test_user_field_contains_username(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert resp.get_json()["user"]["username"] == "alice"

    def test_user_field_contains_user_id(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert resp.get_json()["user"]["user_id"] == "user-001"

    def test_user_field_contains_email(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert resp.get_json()["user"]["email"] == "alice@example.com"

    def test_alice_has_role_user(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert "ROLE_USER" in resp.get_json()["user"]["roles"]

    def test_alice_does_not_have_role_admin(self, client):
        resp = _login(client, "alice", "alice_pass")
        assert "ROLE_ADMIN" not in resp.get_json()["user"]["roles"]

    def test_admin_has_role_admin(self, client):
        resp = _login(client, "admin", "admin_pass")
        roles = resp.get_json()["user"]["roles"]
        assert "ROLE_ADMIN" in roles

    def test_admin_also_has_role_user(self, client):
        resp = _login(client, "admin", "admin_pass")
        roles = resp.get_json()["user"]["roles"]
        assert "ROLE_USER" in roles

    def test_each_login_produces_unique_token(self, client):
        """Each login call must generate a distinct JTI (unique token)."""
        t1 = _get_token(client)
        t2 = _get_token(client)
        assert t1 != t2


# ===========================================================================
# POST /auth/login – failure and edge cases
# ===========================================================================


class TestLoginFailure:
    def test_wrong_password_returns_401(self, client):
        resp = _login(client, "alice", "wrong_password")
        assert resp.status_code == 401

    def test_wrong_password_error_message(self, client):
        resp = _login(client, "alice", "wrong_password")
        assert "Invalid" in resp.get_json()["error"]

    def test_unknown_user_returns_401(self, client):
        resp = _login(client, "nobody", "any_pass")
        assert resp.status_code == 401

    def test_missing_password_returns_400(self, client):
        resp = client.post("/auth/login", json={"username": "alice"})
        assert resp.status_code == 400

    def test_missing_username_returns_400(self, client):
        resp = client.post("/auth/login", json={"password": "alice_pass"})
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client):
        resp = client.post("/auth/login", json={})
        assert resp.status_code == 400

    def test_empty_username_returns_400(self, client):
        resp = client.post("/auth/login", json={"username": "", "password": "alice_pass"})
        assert resp.status_code == 400

    def test_empty_password_returns_400(self, client):
        resp = client.post("/auth/login", json={"username": "alice", "password": ""})
        assert resp.status_code == 400

    def test_null_username_returns_400(self, client):
        resp = client.post("/auth/login", json={"username": None, "password": "alice_pass"})
        assert resp.status_code == 400

    def test_null_password_returns_400(self, client):
        resp = client.post("/auth/login", json={"username": "alice", "password": None})
        assert resp.status_code == 400

    def test_no_json_body_returns_400(self, client):
        resp = client.post("/auth/login", data="not json", content_type="text/plain")
        assert resp.status_code == 400

    def test_oversized_username_returns_400(self, client):
        """Username longer than 256 chars must be rejected."""
        resp = client.post(
            "/auth/login",
            json={"username": "a" * 257, "password": "alice_pass"},
        )
        assert resp.status_code == 400

    def test_oversized_password_returns_400(self, client):
        """Password longer than 256 chars must be rejected."""
        resp = client.post(
            "/auth/login",
            json={"username": "alice", "password": "p" * 257},
        )
        assert resp.status_code == 400

    def test_sql_injection_in_username_returns_401_or_400(self, client):
        """SQL injection payload must not succeed authentication."""
        resp = client.post(
            "/auth/login",
            json={"username": "' OR '1'='1", "password": "anything"},
        )
        assert resp.status_code in (400, 401)

    def test_script_tag_in_username_is_rejected(self, client):
        """XSS payload in username must not succeed authentication."""
        resp = client.post(
            "/auth/login",
            json={"username": "<script>alert(1)</script>", "password": "pass"},
        )
        assert resp.status_code in (400, 401)

    def test_login_does_not_expose_hashed_password_in_response(self, client):
        """Password material must not appear in the success response."""
        resp = _login(client, "alice", "alice_pass")
        body = resp.get_data(as_text=True)
        assert "alice_pass" not in body
        assert "password" not in body


# ===========================================================================
# POST /auth/logout – typical success paths
# ===========================================================================


class TestLogoutSuccess:
    def test_logout_with_valid_token_returns_200(self, client):
        token = _get_token(client)
        resp = client.post("/auth/logout", headers=_auth_header(token))
        assert resp.status_code == 200

    def test_logout_response_message(self, client):
        token = _get_token(client)
        resp = client.post("/auth/logout", headers=_auth_header(token))
        assert resp.get_json()["message"] == "Successfully logged out"

    def test_revoked_token_rejected_on_subsequent_logout(self, client):
        """A token that has been logged out must be rejected on reuse."""
        token = _get_token(client)
        # First logout succeeds.
        resp1 = client.post("/auth/logout", headers=_auth_header(token))
        assert resp1.status_code == 200
        # Second attempt with the same token must fail (token revoked).
        resp2 = client.post("/auth/logout", headers=_auth_header(token))
        assert resp2.status_code == 401

    def test_admin_can_logout(self, client):
        token = _get_token(client, "admin", "admin_pass")
        resp = client.post("/auth/logout", headers=_auth_header(token))
        assert resp.status_code == 200

    def test_logout_returns_json_content_type(self, client):
        token = _get_token(client)
        resp = client.post("/auth/logout", headers=_auth_header(token))
        assert "application/json" in resp.content_type


# ===========================================================================
# POST /auth/logout – failure and edge cases
# ===========================================================================


class TestLogoutFailure:
    def test_logout_without_token_returns_401(self, client):
        resp = client.post("/auth/logout")
        assert resp.status_code == 401

    def test_logout_without_token_error_message(self, client):
        resp = client.post("/auth/logout")
        assert "Authorization token is missing" in resp.get_json()["error"]

    def test_logout_with_expired_token_returns_401(self, client):
        token = _make_expired_token()
        resp = client.post("/auth/logout", headers=_auth_header(token))
        assert resp.status_code == 401
        assert "expired" in resp.get_json()["error"].lower()

    def test_logout_with_tampered_token_returns_401(self, client):
        token = _make_tampered_token()
        resp = client.post("/auth/logout", headers=_auth_header(token))
        assert resp.status_code == 401

    def test_logout_with_garbage_token_returns_401(self, client):
        resp = client.post(
            "/auth/logout", headers={"Authorization": "Bearer garbage.token.here"}
        )
        assert resp.status_code == 401

    def test_logout_with_basic_auth_returns_401(self, client):
        resp = client.post(
            "/auth/logout", headers={"Authorization": "Basic dXNlcjpwYXNz"}
        )
        assert resp.status_code == 401
        assert "Authorization token is missing" in resp.get_json()["error"]


# ===========================================================================
# Internal helper unit tests (token generation/validation)
# ===========================================================================


class TestInternalHelpers:
    def test_verify_credentials_returns_user_for_valid_creds(self):
        user = _verify_credentials("alice", "alice_pass")
        assert user is not None
        assert user["user_id"] == "user-001"

    def test_verify_credentials_returns_none_for_wrong_password(self):
        assert _verify_credentials("alice", "wrong") is None

    def test_verify_credentials_returns_none_for_unknown_user(self):
        assert _verify_credentials("nobody", "pass") is None

    def test_get_user_roles_returns_roles_for_known_user(self):
        roles = _get_user_roles("admin")
        assert "ROLE_ADMIN" in roles

    def test_get_user_roles_defaults_to_role_user_for_unknown(self):
        roles = _get_user_roles("stranger")
        assert roles == ["ROLE_USER"]

    def test_generate_token_returns_string(self):
        token = _generate_token("u1", "alice", ["ROLE_USER"])
        assert isinstance(token, str)

    def test_generate_token_contains_sub_claim(self):
        token = _generate_token("u1", "alice", ["ROLE_USER"])
        payload = jwt.decode(token, _get_secret(), algorithms=[_get_algorithm()])
        assert payload["sub"] == "u1"

    def test_generate_token_contains_username_claim(self):
        token = _generate_token("u1", "alice", ["ROLE_USER"])
        payload = jwt.decode(token, _get_secret(), algorithms=[_get_algorithm()])
        assert payload["username"] == "alice"

    def test_generate_token_contains_jti_claim(self):
        token = _generate_token("u1", "alice", ["ROLE_USER"])
        payload = jwt.decode(token, _get_secret(), algorithms=[_get_algorithm()])
        assert "jti" in payload

    def test_generate_token_respects_expiry_minutes(self):
        token = _generate_token("u1", "alice", ["ROLE_USER"], expiry_minutes=30)
        payload = jwt.decode(token, _get_secret(), algorithms=[_get_algorithm()])
        now = datetime.now(tz=timezone.utc).timestamp()
        assert 0 < payload["exp"] - now <= 30 * 60 + 5  # within 30 minutes + 5 s slack

    def test_validate_token_accepts_valid_token(self):
        token = _generate_token("u1", "alice", ["ROLE_USER"])
        payload = _validate_token(token)
        assert payload["sub"] == "u1"

    def test_validate_token_raises_on_expired_token(self):
        now = datetime.now(tz=timezone.utc)
        payload: Dict[str, Any] = {
            "sub": "u1",
            "username": "alice",
            "roles": [],
            "iat": now - timedelta(minutes=120),
            "exp": now - timedelta(minutes=60),
            "jti": "test-expired",
        }
        token = jwt.encode(payload, _get_secret(), algorithm=_get_algorithm())
        with pytest.raises(jwt.ExpiredSignatureError):
            _validate_token(token)

    def test_validate_token_raises_on_tampered_token(self):
        payload: Dict[str, Any] = {
            "sub": "u1",
            "username": "alice",
            "roles": [],
            "iat": datetime.now(tz=timezone.utc),
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=60),
            "jti": "test-tampered",
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError):
            _validate_token(token)

    def test_validate_token_raises_on_blacklisted_jti(self):
        token = _generate_token("u1", "alice", ["ROLE_USER"])
        payload = _validate_token(token)
        _TOKEN_BLACKLIST.add(payload["jti"])
        with pytest.raises(jwt.InvalidTokenError, match="revoked"):
            _validate_token(token)


# ===========================================================================
# Full login → logout flow
# ===========================================================================


class TestLoginLogoutFlow:
    def test_full_login_logout_cycle(self, client):
        """Complete cycle: login → logout → rejected re-use."""
        # Step 1: login.
        resp = _login(client, "alice", "alice_pass")
        assert resp.status_code == 200
        token = resp.get_json()["token"]

        # Step 2: logout with valid token.
        resp = client.post("/auth/logout", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Successfully logged out"

        # Step 3: same token is now revoked and must be rejected.
        resp = client.post("/auth/logout", headers=_auth_header(token))
        assert resp.status_code == 401

    def test_two_independent_sessions_dont_interfere(self, client):
        """Logging out one session must not affect another session's token."""
        token_a = _get_token(client, "alice", "alice_pass")
        token_b = _get_token(client, "alice", "alice_pass")

        # Revoke session A.
        resp = client.post("/auth/logout", headers=_auth_header(token_a))
        assert resp.status_code == 200

        # Session B must still be valid.
        resp = client.post("/auth/logout", headers=_auth_header(token_b))
        assert resp.status_code == 200
