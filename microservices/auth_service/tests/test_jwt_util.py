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


# ---------------------------------------------------------------------------
# Task 1 additions – generate_refresh_token (uncovered branch)
# ---------------------------------------------------------------------------


class TestGenerateRefreshToken:
    def test_returns_non_empty_string(self):
        token = generate_refresh_token("u1", "alice")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_type_is_refresh(self):
        token = generate_refresh_token("u1", "alice")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload.get("token_type") == "refresh"

    def test_contains_user_id(self):
        token = generate_refresh_token("u1", "alice")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["userId"] == "u1"

    def test_contains_username(self):
        token = generate_refresh_token("u1", "alice")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["username"] == "alice"

    def test_has_expiry_claims(self):
        token = generate_refresh_token("u1", "alice")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert "exp" in payload
        assert "iat" in payload
        assert payload["exp"] > payload["iat"]

    def test_has_longer_expiry_than_access_token(self):
        """Refresh token must expire later than a standard access token."""
        access = generate_token("u1", "alice")
        refresh = generate_refresh_token("u1", "alice")
        access_payload = jwt.decode(access, "test-secret-key", algorithms=["HS256"])
        refresh_payload = jwt.decode(refresh, "test-secret-key", algorithms=["HS256"])
        assert refresh_payload["exp"] > access_payload["exp"]

    def test_has_unique_jti(self):
        t1 = generate_refresh_token("u1", "alice")
        t2 = generate_refresh_token("u1", "alice")
        p1 = jwt.decode(t1, "test-secret-key", algorithms=["HS256"])
        p2 = jwt.decode(t2, "test-secret-key", algorithms=["HS256"])
        assert p1["jti"] != p2["jti"]

    def test_tokens_are_distinct_strings(self):
        t1 = generate_refresh_token("u1", "alice")
        t2 = generate_refresh_token("u1", "alice")
        assert t1 != t2


# ---------------------------------------------------------------------------
# Task 1 additions – extractUsername (username extraction from decoded payload)
# ---------------------------------------------------------------------------


class TestExtractUsername:
    """Verify username is correctly extracted from generated tokens."""

    def test_extract_username_alice(self):
        token = generate_token("u1", "alice")
        payload = validate_token(token)
        assert payload["username"] == "alice"

    def test_extract_username_admin(self):
        token = generate_token("u2", "admin")
        payload = validate_token(token)
        assert payload["username"] == "admin"

    def test_extract_username_bob(self):
        token = generate_token("u3", "bob")
        payload = validate_token(token)
        assert payload["username"] == "bob"

    def test_extract_username_from_refresh_token(self):
        token = generate_refresh_token("u1", "alice")
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["username"] == "alice"

    def test_extract_username_preserved_through_renew(self):
        token = generate_token("u1", "alice", expiry_minutes=-1)
        new_token = renew_token(token)
        payload = validate_token(new_token)
        assert payload["username"] == "alice"


# ---------------------------------------------------------------------------
# Task 1 additions – edge cases for null/empty inputs and missing claims
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_validate_token_with_sub_claim_instead_of_user_id(self):
        """Token with 'sub' instead of 'userId' passes validation (AC3)."""
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": "u1",
            "username": "alice",
            "iat": datetime.now(tz=timezone.utc),
            "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, "test-secret-key", algorithm="HS256")
        result = validate_token(token)
        assert result["sub"] == "u1"

    def test_validate_token_missing_both_user_id_and_sub_raises(self):
        """Token missing both 'userId' and 'sub' raises InvalidTokenError."""
        from datetime import datetime, timedelta, timezone

        payload = {
            "username": "alice",
            "iat": datetime.now(tz=timezone.utc),
            "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, "test-secret-key", algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError):
            validate_token(token)

    def test_generate_token_with_empty_roles_list(self):
        """Explicit empty roles/permissions list are embedded as-is."""
        token = generate_token("u1", "alice", roles=[], permissions=[])
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["roles"] == []
        assert payload["permissions"] == []

    def test_renew_token_preserves_roles(self):
        """renew_token carries over roles from the original token."""
        token = generate_token("u1", "alice", roles=["ROLE_ADMIN"])
        new_token = renew_token(token)
        new_payload = validate_token(new_token)
        assert "ROLE_ADMIN" in new_payload["roles"]

    def test_has_role_returns_false_for_expired_token(self):
        """has_role catches ExpiredSignatureError and returns False."""
        expired = generate_token("u1", "admin", roles=["ROLE_ADMIN"], expiry_minutes=-1)
        result = has_role(expired, "ROLE_ADMIN")
        assert result is False

    def test_generate_token_uses_env_secret(self):
        """Token must be signed with the env-configured secret."""
        token = generate_token("u1", "alice")
        # Decoding with correct key succeeds
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["userId"] == "u1"

    def test_validate_token_empty_string_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            validate_token("")

    def test_validate_token_whitespace_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            validate_token("   ")

    def test_validate_token_immature_token_raises(self):
        """Token with future 'nbf' triggers the InvalidTokenError branch (lines 164-165)."""
        from datetime import datetime, timedelta, timezone

        future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        payload = {
            "userId": "u1",
            "username": "alice",
            "iat": datetime.now(tz=timezone.utc),
            "exp": datetime.now(tz=timezone.utc) + timedelta(hours=2),
            "nbf": future,  # ImmatureSignatureError – subclass of InvalidTokenError
        }
        token = jwt.encode(payload, "test-secret-key", algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError):
            validate_token(token)
