"""jwt_util.py – JWT generation, validation, and role-encoding utilities.

Tasks: 3 (JWT generation/validation) + 6 (RBAC role encoding in JWT).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import jwt

# ---------------------------------------------------------------------------
# Mock role data (Task 6 – role retrieval assumed handled by mock/fixed data)
# ---------------------------------------------------------------------------

_MOCK_USER_ROLES: Dict[str, List[str]] = {
    "admin": ["ROLE_ADMIN", "ROLE_USER"],
    "alice": ["ROLE_USER"],
    "bob": ["ROLE_USER"],
}

_MOCK_USER_PERMISSIONS: Dict[str, List[str]] = {
    "admin": ["read", "write", "delete"],
    "alice": ["read", "write"],
    "bob": ["read"],
}


def get_user_roles(username: str) -> List[str]:
    """Return roles for *username* from mock data.  Returns empty list if unknown."""
    return _MOCK_USER_ROLES.get(username, ["ROLE_USER"])


def get_user_permissions(username: str) -> List[str]:
    """Return permissions for *username* from mock data."""
    return _MOCK_USER_PERMISSIONS.get(username, ["read"])


# ---------------------------------------------------------------------------
# JWT configuration helpers
# ---------------------------------------------------------------------------


def _get_secret() -> str:
    return os.environ.get("JWT_SECRET_KEY", "jwt-secret-change-in-production")


def _get_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256")


def _get_access_expiry_minutes() -> int:
    return int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))


def _get_refresh_expiry_days() -> int:
    return int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "7"))


# ---------------------------------------------------------------------------
# Token generation (Tasks 3 + 6)
# ---------------------------------------------------------------------------


def generate_token(
    user_id: str,
    username: str,
    roles: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    expiry_minutes: Optional[int] = None,
) -> str:
    """Generate a signed JWT containing userId, roles, permissions, and expiry.

    Acceptance criteria satisfied:
    - Task 1/3/6: token includes ``userId``, ``roles``, and ``expiry``.
    - Task 6: roles and permissions are embedded in the payload.

    Parameters
    ----------
    user_id:        Unique identifier for the user.
    username:       Login handle (used to look up roles when not provided).
    roles:          Explicit role list; resolved from mock data when ``None``.
    permissions:    Explicit permission list; resolved from mock data when ``None``.
    expiry_minutes: Override token lifetime in minutes.
    """
    if roles is None:
        roles = get_user_roles(username)
    if permissions is None:
        permissions = get_user_permissions(username)

    now = datetime.now(tz=timezone.utc)
    minutes = expiry_minutes if expiry_minutes is not None else _get_access_expiry_minutes()
    from datetime import timedelta

    expires_at = now + timedelta(minutes=minutes)

    payload: Dict[str, Any] = {
        "userId": user_id,
        "username": username,
        "roles": roles,
        "permissions": permissions,
        "iat": now,
        "exp": expires_at,
        "expiry": expires_at.isoformat(),
        "jti": str(uuid.uuid4()),
        "token_type": "access",
    }

    return jwt.encode(payload, _get_secret(), algorithm=_get_algorithm())


def generate_refresh_token(user_id: str, username: str) -> str:
    """Generate a refresh token with a longer expiry.

    Used by Task 2 (session refresh) and Task 3 (/refresh-token endpoint).
    """
    now = datetime.now(tz=timezone.utc)
    from datetime import timedelta

    expires_at = now + timedelta(days=_get_refresh_expiry_days())

    payload: Dict[str, Any] = {
        "userId": user_id,
        "username": username,
        "iat": now,
        "exp": expires_at,
        "expiry": expires_at.isoformat(),
        "jti": str(uuid.uuid4()),
        "token_type": "refresh",
    }

    return jwt.encode(payload, _get_secret(), algorithm=_get_algorithm())


# ---------------------------------------------------------------------------
# Token validation (Tasks 1 + 3)
# ---------------------------------------------------------------------------


def validate_token(token: str) -> Dict[str, Any]:
    """Decode and validate *token*.

    Returns the decoded payload dict.

    Raises
    ------
    jwt.ExpiredSignatureError  – when the token has expired.
    jwt.InvalidTokenError      – for any other validation failure (wrong format,
                                  bad signature, missing claims, etc.).
    """
    try:
        payload = jwt.decode(
            token,
            _get_secret(),
            algorithms=[_get_algorithm()],
        )
    except jwt.ExpiredSignatureError:
        raise
    except jwt.DecodeError as exc:
        raise jwt.InvalidTokenError(f"Token decode failed: {exc}") from exc
    except jwt.InvalidTokenError:
        raise

    # Reject tokens with incorrect payload formats (Task 1 AC3)
    if "userId" not in payload and "sub" not in payload:
        raise jwt.InvalidTokenError("Token payload missing required userId/sub claim")

    return payload


def renew_token(token: str) -> str:
    """Renew an access token.

    Accepts an expired OR valid token and issues a fresh access token
    preserving the user identity and roles.  Satisfies Task 1 AC2:
    "Expired tokens are successfully renewed."

    Raises
    ------
    jwt.InvalidTokenError – if the token is structurally invalid (cannot be
                            decoded at all, even ignoring expiry).
    """
    try:
        payload = jwt.decode(
            token,
            _get_secret(),
            algorithms=[_get_algorithm()],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError as exc:
        raise jwt.InvalidTokenError(f"Cannot renew invalid token: {exc}") from exc

    user_id = payload.get("userId") or payload.get("sub", "")
    username = payload.get("username", "")
    roles = payload.get("roles")
    permissions = payload.get("permissions")

    return generate_token(user_id, username, roles=roles, permissions=permissions)


# ---------------------------------------------------------------------------
# Role-based access checks (Tasks 5 + 6)
# ---------------------------------------------------------------------------


def has_role(token: str, required_role: str) -> bool:
    """Return True if *token* carries *required_role*.

    Task 6 AC2: "Protected endpoint access respects embedded user roles."
    """
    try:
        payload = validate_token(token)
    except jwt.InvalidTokenError:
        return False
    roles: List[str] = payload.get("roles", [])
    return required_role in roles


def check_roles(payload: Dict[str, Any], required_role: str) -> bool:
    """Return True if decoded *payload* includes *required_role*."""
    return required_role in payload.get("roles", [])
