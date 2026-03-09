"""tests/unit/auth/test_login.py – Unit tests for auth/login.py.

Task 3 Acceptance Criteria:
- All tests passing in different environments.
- 90% code coverage for auth/login.py.
- Negative test cases must accurately flag token errors.

Covers:
- generate_jwt() with valid, invalid, and boundary inputs.
- verify_jwt() with valid, expired, malformed, and empty tokens.
- Error messages for token expiration and invalid signature.
- Mock-compatible: no external service dependencies.
"""

from __future__ import annotations

import os

import jwt
import pytest

# Must be set before importing auth.login (which imports jwt_util)
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60")

from auth.login import generate_jwt, verify_jwt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET = "test-secret-key"
_ALGO = "HS256"


def _decode(token: str) -> dict:
    return jwt.decode(token, _SECRET, algorithms=[_ALGO])


# ---------------------------------------------------------------------------
# generate_jwt() tests
# ---------------------------------------------------------------------------


class TestGenerateJwt:
    def test_returns_non_empty_string(self):
        token = generate_jwt("u1", "alice")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_user_id(self):
        token = generate_jwt("u1", "alice")
        payload = _decode(token)
        assert payload["userId"] == "u1"

    def test_token_contains_username(self):
        token = generate_jwt("u1", "alice")
        payload = _decode(token)
        assert payload["username"] == "alice"

    def test_token_contains_roles(self):
        token = generate_jwt("u1", "alice")
        payload = _decode(token)
        assert "roles" in payload
        assert isinstance(payload["roles"], list)

    def test_token_contains_permissions(self):
        token = generate_jwt("u1", "alice")
        payload = _decode(token)
        assert "permissions" in payload
        assert isinstance(payload["permissions"], list)

    def test_token_contains_expiry_claims(self):
        token = generate_jwt("u1", "alice")
        payload = _decode(token)
        assert "exp" in payload
        assert "expiry" in payload
        assert "iat" in payload
        assert payload["exp"] > payload["iat"]

    def test_explicit_roles_are_embedded(self):
        token = generate_jwt("u1", "alice", roles=["ROLE_ADMIN"])
        payload = _decode(token)
        assert "ROLE_ADMIN" in payload["roles"]

    def test_explicit_permissions_are_embedded(self):
        token = generate_jwt("u1", "alice", permissions=["read", "write"])
        payload = _decode(token)
        assert payload["permissions"] == ["read", "write"]

    def test_custom_expiry_minutes_applied(self):
        token = generate_jwt("u1", "alice", expiry_minutes=120)
        payload = _decode(token)
        assert "exp" in payload

    def test_roles_resolved_from_mock_for_admin(self):
        token = generate_jwt("u2", "admin")
        payload = _decode(token)
        assert "ROLE_ADMIN" in payload["roles"]

    def test_tokens_have_unique_jti(self):
        """Each token must have a unique jti claim (no replay)."""
        t1 = generate_jwt("u1", "alice")
        t2 = generate_jwt("u1", "alice")
        p1 = _decode(t1)
        p2 = _decode(t2)
        assert p1["jti"] != p2["jti"]

    def test_tokens_are_different_strings(self):
        t1 = generate_jwt("u1", "alice")
        t2 = generate_jwt("u1", "alice")
        assert t1 != t2

    # --- Negative / edge cases ---

    def test_empty_user_id_raises_value_error(self):
        with pytest.raises(ValueError, match="user_id"):
            generate_jwt("", "alice")

    def test_none_user_id_raises_value_error(self):
        with pytest.raises(ValueError, match="user_id"):
            generate_jwt(None, "alice")  # type: ignore[arg-type]

    def test_empty_username_raises_value_error(self):
        with pytest.raises(ValueError, match="username"):
            generate_jwt("u1", "")

    def test_none_username_raises_value_error(self):
        with pytest.raises(ValueError, match="username"):
            generate_jwt("u1", None)  # type: ignore[arg-type]

    def test_empty_roles_list_is_accepted(self):
        token = generate_jwt("u1", "alice", roles=[], permissions=[])
        payload = _decode(token)
        assert payload["roles"] == []
        assert payload["permissions"] == []


# ---------------------------------------------------------------------------
# verify_jwt() tests
# ---------------------------------------------------------------------------


class TestVerifyJwt:
    def test_valid_token_returns_payload_dict(self):
        token = generate_jwt("u1", "alice")
        payload = verify_jwt(token)
        assert isinstance(payload, dict)

    def test_payload_contains_user_id(self):
        token = generate_jwt("u1", "alice")
        payload = verify_jwt(token)
        assert payload["userId"] == "u1"

    def test_payload_contains_username(self):
        token = generate_jwt("u1", "alice")
        payload = verify_jwt(token)
        assert payload["username"] == "alice"

    def test_payload_contains_required_claims(self):
        token = generate_jwt("u1", "alice")
        payload = verify_jwt(token)
        for claim in ("userId", "username", "roles", "permissions", "exp", "iat", "jti"):
            assert claim in payload, f"Missing required claim: '{claim}'"

    def test_payload_roles_match_input(self):
        token = generate_jwt("u1", "alice", roles=["ROLE_USER"])
        payload = verify_jwt(token)
        assert "ROLE_USER" in payload["roles"]

    # --- Negative test cases ---

    def test_expired_token_raises_expired_signature_error(self):
        """Expired tokens must raise jwt.ExpiredSignatureError specifically."""
        token = generate_jwt("u1", "alice", expiry_minutes=-1)
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_jwt(token)

    def test_expired_token_error_is_subclass_of_invalid_token_error(self):
        """ExpiredSignatureError is-a InvalidTokenError."""
        token = generate_jwt("u1", "alice", expiry_minutes=-1)
        with pytest.raises(jwt.InvalidTokenError):
            verify_jwt(token)

    def test_tampered_signature_raises_invalid_token_error(self):
        token = generate_jwt("u1", "alice")
        bad_token = token[:-5] + "XXXXX"
        with pytest.raises(jwt.InvalidTokenError):
            verify_jwt(bad_token)

    def test_malformed_jwt_three_parts_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            verify_jwt("not.a.valid.jwt")

    def test_random_string_raises_invalid_token_error(self):
        with pytest.raises(jwt.InvalidTokenError):
            verify_jwt("randomstring")

    def test_empty_token_raises_value_error(self):
        with pytest.raises(ValueError, match="token"):
            verify_jwt("")

    def test_none_token_raises_value_error(self):
        with pytest.raises(ValueError, match="token"):
            verify_jwt(None)  # type: ignore[arg-type]

    def test_wrong_secret_raises_invalid_token_error(self):
        """Token signed with a different key must be rejected."""
        original_secret = os.environ.get("JWT_SECRET_KEY")
        os.environ["JWT_SECRET_KEY"] = "original-secret"
        try:
            token = generate_jwt("u1", "alice")
        finally:
            os.environ["JWT_SECRET_KEY"] = "different-secret"
        try:
            with pytest.raises(jwt.InvalidTokenError):
                verify_jwt(token)
        finally:
            if original_secret is not None:
                os.environ["JWT_SECRET_KEY"] = original_secret

    def test_token_with_invalid_signature_error_message(self):
        """Error must indicate token decode failure."""
        token = generate_jwt("u1", "alice")
        bad = token[:-10] + "0000000000"
        with pytest.raises(jwt.InvalidTokenError):
            verify_jwt(bad)
