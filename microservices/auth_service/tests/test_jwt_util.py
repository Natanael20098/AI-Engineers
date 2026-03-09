"""test_jwt_util.py – Unit tests for jwt_util (Tasks 3 + 6).

Covers:
- AC1 Task 3: JWT generation and validation functions operate accurately.
- AC3 Task 3: JWTs expire and reject unauthorised access attempts.
- AC1 Task 6: JWTs contain accurate user roles and permissions.
- AC3 Task 6: Secure error handling for unauthorised role access attempts.
- Task 1 AC1: Token includes userId, roles, expiry.
- Task 1 AC2: Expired tokens are successfully renewed.
- Task 1 AC3: Tokens with incorrect payloads return error.
"""

from __future__ import annotations

import os
import time

import jwt
import pytest

# Ensure test environment uses short expiry
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60")
os.environ.setdefault("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "7")

from microservices.auth_service.utils.jwt_util import (
    check_roles,
    generate_refresh_token,
    generate_token,
    get_user_permissions,
    get_user_roles,
    has_role,
    renew_token,
    validate_token,
)


class TestGenerateToken:
    def test_token_contains_user_id(self):
        token = generate_token("u1", "alice")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["userId"] == "u1"

    def test_token_contains_roles(self):
        token = generate_token("u1", "alice")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "roles" in payload
        assert isinstance(payload["roles"], list)

    def test_token_contains_expiry(self):
        token = generate_token("u1", "alice")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "exp" in payload
        assert "expiry" in payload

    def test_token_contains_explicit_roles(self):
        token = generate_token("u1", "alice", roles=["ROLE_ADMIN"])
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "ROLE_ADMIN" in payload["roles"]

    def test_token_contains_permissions(self):
        token = generate_token("u1", "alice", permissions=["read", "write"])
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["permissions"] == ["read", "write"]

    def test_roles_resolved_from_mock_for_admin(self):
        token = generate_token("u2", "admin")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "ROLE_ADMIN" in payload["roles"]


class TestValidateToken:
    def test_valid_token_returns_payload(self):
        token = generate_token("u1", "alice")
        payload = validate_token(token)
        assert payload["userId"] == "u1"

    def test_expired_token_raises(self):
        token = generate_token("u1", "alice", expiry_minutes=-1)
        with pytest.raises(jwt.ExpiredSignatureError):
            validate_token(token)

    def test_invalid_signature_raises(self):
        token = generate_token("u1", "alice")
        # Tamper with token
        bad_token = token[:-5] + "XXXXX"
        with pytest.raises(jwt.InvalidTokenError):
            validate_token(bad_token)

    def test_garbage_token_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            validate_token("not.a.valid.jwt")


class TestRenewToken:
    def test_renew_valid_token_returns_new_token(self):
        token = generate_token("u1", "alice")
        new_token = renew_token(token)
        assert new_token != token
        payload = validate_token(new_token)
        assert payload["userId"] == "u1"

    def test_renew_expired_token_succeeds(self):
        token = generate_token("u1", "alice", expiry_minutes=-1)
        # Should NOT raise even though expired
        new_token = renew_token(token)
        payload = validate_token(new_token)
        assert payload["userId"] == "u1"

    def test_renew_invalid_token_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            renew_token("totally.invalid.token")


class TestRoleChecks:
    def test_has_role_true_for_matching_role(self):
        token = generate_token("u2", "admin", roles=["ROLE_ADMIN", "ROLE_USER"])
        assert has_role(token, "ROLE_ADMIN") is True

    def test_has_role_false_for_missing_role(self):
        token = generate_token("u1", "alice", roles=["ROLE_USER"])
        assert has_role(token, "ROLE_ADMIN") is False

    def test_has_role_false_for_invalid_token(self):
        assert has_role("bad.token", "ROLE_ADMIN") is False

    def test_check_roles_true_for_authorized(self):
        payload = {"roles": ["ROLE_ADMIN", "ROLE_USER"]}
        assert check_roles(payload, "ROLE_ADMIN") is True

    def test_check_roles_false_for_unauthorized(self):
        payload = {"roles": ["ROLE_USER"]}
        assert check_roles(payload, "ROLE_ADMIN") is False


class TestMockData:
    def test_get_user_roles_known_user(self):
        assert "ROLE_USER" in get_user_roles("alice")

    def test_get_user_roles_admin_has_admin_role(self):
        assert "ROLE_ADMIN" in get_user_roles("admin")

    def test_get_user_roles_unknown_returns_default(self):
        roles = get_user_roles("unknown_user")
        assert roles == ["ROLE_USER"]

    def test_get_user_permissions_known_user(self):
        perms = get_user_permissions("alice")
        assert "read" in perms

    def test_get_user_permissions_unknown_returns_default(self):
        perms = get_user_permissions("unknown_user")
        assert perms == ["read"]
