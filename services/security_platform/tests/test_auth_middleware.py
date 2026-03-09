"""test_auth_middleware.py – Unit tests for AuthMiddleware.

Covers Task 1 acceptance criteria:
  AC1  Middleware passes unit tests covering success and failure scenarios.
  AC2  Token verification logs both success and failure appropriately.
  AC3  Expired tokens and incorrect tokens return correct HTTP error codes (401).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from services.security_platform.auth_middleware import AuthMiddleware, _extract_bearer_token
from services.security_platform.utils.jwt_util import _get_algorithm, _get_secret, generate_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET = _get_secret()
_ALGO = _get_algorithm()


def _make_token(
    user_id: str = "user-001",
    username: str = "alice",
    expiry_minutes: int = 60,
) -> str:
    return generate_token(user_id=user_id, username=username, expiry_minutes=expiry_minutes)


def _make_expired_token() -> str:
    """Return a token that is already expired."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": "user-001",
        "username": "alice",
        "roles": ["ROLE_USER"],
        "iat": now - timedelta(minutes=120),
        "exp": now - timedelta(minutes=60),
        "jti": "expired-jti",
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGO)


def _make_tampered_token() -> str:
    """Return a token signed with a wrong secret (tampered)."""
    payload = {
        "sub": "user-001",
        "username": "alice",
        "roles": ["ROLE_USER"],
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=60),
        "jti": "tampered-jti",
    }
    return jwt.encode(payload, "wrong-secret", algorithm=_ALGO)


# ---------------------------------------------------------------------------
# Minimal FastAPI app for testing middleware
# ---------------------------------------------------------------------------


def _build_test_app(public_paths=None) -> FastAPI:
    test_app = FastAPI()
    kwargs = {}
    if public_paths is not None:
        kwargs["public_paths"] = public_paths
    test_app.add_middleware(AuthMiddleware, **kwargs)

    @test_app.get("/health")
    def health():
        return {"status": "ok"}

    @test_app.get("/auth/login")
    def login_get():
        return {"message": "login page"}

    @test_app.get("/protected")
    def protected(request: Request):
        user = request.state.current_user
        return {"user": user.get("username")}

    return test_app


@pytest.fixture()
def client():
    return TestClient(_build_test_app(), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# AC1 – Success scenario: valid token grants access
# ---------------------------------------------------------------------------


def test_valid_token_grants_access(client):
    token = _make_token()
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"] == "alice"


def test_public_path_health_bypasses_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_public_path_login_bypasses_auth(client):
    response = client.get("/auth/login")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# AC1 – Failure scenario: missing token
# ---------------------------------------------------------------------------


def test_missing_token_returns_401(client):
    response = client.get("/protected")
    assert response.status_code == 401
    assert "Authorization token is missing" in response.json()["error"]


def test_wrong_auth_scheme_returns_401(client):
    response = client.get("/protected", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401
    assert "Authorization token is missing" in response.json()["error"]


# ---------------------------------------------------------------------------
# AC3 – Expired tokens return 401
# ---------------------------------------------------------------------------


def test_expired_token_returns_401(client):
    token = _make_expired_token()
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["error"].lower()


# ---------------------------------------------------------------------------
# AC3 – Invalid / tampered tokens return 401
# ---------------------------------------------------------------------------


def test_tampered_token_returns_401(client):
    token = _make_tampered_token()
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "Invalid token" in response.json()["error"]


def test_garbage_token_returns_401(client):
    response = client.get("/protected", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# AC2 – Logging: success and failure are logged
# ---------------------------------------------------------------------------


def test_successful_auth_is_logged(client, caplog):
    token = _make_token()
    with caplog.at_level(logging.INFO, logger="services.security_platform.auth_middleware"):
        client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert any("authenticated" in record.message for record in caplog.records)


def test_missing_token_failure_is_logged(client, caplog):
    with caplog.at_level(logging.WARNING, logger="services.security_platform.auth_middleware"):
        client.get("/protected")
    assert any("missing token" in record.message for record in caplog.records)


def test_expired_token_failure_is_logged(client, caplog):
    token = _make_expired_token()
    with caplog.at_level(logging.WARNING, logger="services.security_platform.auth_middleware"):
        client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert any("expired token" in record.message for record in caplog.records)


def test_invalid_token_failure_is_logged(client, caplog):
    token = _make_tampered_token()
    with caplog.at_level(logging.WARNING, logger="services.security_platform.auth_middleware"):
        client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert any("invalid token" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# _extract_bearer_token helper unit tests
# ---------------------------------------------------------------------------


def test_extract_bearer_token_present():
    from starlette.datastructures import Headers
    from starlette.testclient import TestClient
    from fastapi import FastAPI

    dummy = FastAPI()
    extracted: list = []

    @dummy.get("/x")
    def route(request: Request):
        from services.security_platform.auth_middleware import _extract_bearer_token
        extracted.append(_extract_bearer_token(request))
        return {}

    tc = TestClient(dummy)
    tc.get("/x", headers={"Authorization": "Bearer mytoken123"})
    assert extracted[0] == "mytoken123"


def test_extract_bearer_token_absent():
    from fastapi import FastAPI

    dummy = FastAPI()
    extracted: list = []

    @dummy.get("/x")
    def route(request: Request):
        from services.security_platform.auth_middleware import _extract_bearer_token
        extracted.append(_extract_bearer_token(request))
        return {}

    tc = TestClient(dummy)
    tc.get("/x")
    assert extracted[0] is None
