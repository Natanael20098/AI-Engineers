"""test_login_controller.py – Tests for LoginController endpoints (Tasks 3 + 6)."""

from __future__ import annotations

import os

import jwt
import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60")


@pytest.fixture()
def app():
    from microservices.auth_service.config import TestingConfig
    from microservices.auth_service.main import create_app

    return create_app(TestingConfig())


@pytest.fixture()
def client(app):
    return app.test_client()


class TestLoginEndpoint:
    def test_login_returns_200_with_valid_credentials(self, client):
        resp = client.post(
            "/auth/login",
            json={"username": "alice", "password": "alice_pass"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "token" in data
        assert "refresh_token" in data

    def test_login_token_contains_user_id_roles_expiry(self, client):
        resp = client.post(
            "/auth/login",
            json={"username": "alice", "password": "alice_pass"},
        )
        token = resp.get_json()["token"]
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "userId" in payload
        assert "roles" in payload
        assert "exp" in payload

    def test_login_returns_401_for_wrong_password(self, client):
        resp = client.post(
            "/auth/login",
            json={"username": "alice", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_returns_400_for_missing_fields(self, client):
        resp = client.post("/auth/login", json={"username": "alice"})
        assert resp.status_code == 400

    def test_login_returns_400_for_non_json(self, client):
        resp = client.post(
            "/auth/login", data="not-json", content_type="text/plain"
        )
        assert resp.status_code == 400

    def test_login_admin_token_contains_admin_role(self, client):
        resp = client.post(
            "/auth/login",
            json={"username": "admin", "password": "admin_pass"},
        )
        token = resp.get_json()["token"]
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "ROLE_ADMIN" in payload["roles"]


class TestRefreshTokenEndpoint:
    def test_refresh_returns_new_token(self, client):
        # First login to get tokens
        login_resp = client.post(
            "/auth/login",
            json={"username": "alice", "password": "alice_pass"},
        )
        refresh_token = login_resp.get_json()["refresh_token"]

        resp = client.post(
            "/auth/refresh-token",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        assert "token" in resp.get_json()

    def test_refresh_returns_401_for_invalid_token(self, client):
        resp = client.post(
            "/auth/refresh-token",
            json={"refresh_token": "invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_refresh_returns_400_for_missing_token(self, client):
        resp = client.post("/auth/refresh-token", json={})
        assert resp.status_code == 400


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestRoleProtectedEndpoint:
    def test_admin_can_access_protected(self, client):
        login_resp = client.post(
            "/auth/login",
            json={"username": "admin", "password": "admin_pass"},
        )
        token = login_resp.get_json()["token"]
        resp = client.get(
            "/auth/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_regular_user_cannot_access_protected(self, client):
        login_resp = client.post(
            "/auth/login",
            json={"username": "alice", "password": "alice_pass"},
        )
        token = login_resp.get_json()["token"]
        resp = client.get(
            "/auth/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_no_token_returns_401(self, client):
        resp = client.get("/auth/protected")
        assert resp.status_code == 401
