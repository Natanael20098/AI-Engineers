"""jwt_util.py – JWT generation and validation for the Security Platform microservice.

Provides token issuance, validation, and claim inspection used by both the
AuthController (main.py) and the auth_middleware.py component.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _get_secret() -> str:
    return os.environ.get("JWT_SECRET_KEY", "security-platform-secret-change-in-prod")


def _get_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256")


def _get_access_expiry_minutes() -> int:
    return int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))


# ---------------------------------------------------------------------------
# Mock credential and role store (no DB dependency for this microservice)
# ---------------------------------------------------------------------------

_MOCK_USERS: Dict[str, Dict[str, str]] = {
    "alice": {"user_id": "user-001", "password": "alice_pass", "email": "alice@example.com"},
    "admin": {"user_id": "user-002", "password": "admin_pass", "email": "admin@example.com"},
    "bob": {"user_id": "user-003", "password": "bob_pass", "email": "bob@example.com"},
}

_MOCK_USER_ROLES: Dict[str, List[str]] = {
    "admin": ["ROLE_ADMIN", "ROLE_USER"],
    "alice": ["ROLE_USER"],
    "bob": ["ROLE_USER"],
}


def verify_credentials(username: str, password: str) -> Optional[Dict[str, str]]:
    """Return user record dict if credentials are valid, else None."""
    user = _MOCK_USERS.get(username)
    if user and user["password"] == password:
        return user
    return None


def get_user_roles(username: str) -> List[str]:
    """Return roles list for *username*."""
    return _MOCK_USER_ROLES.get(username, ["ROLE_USER"])


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------


def generate_token(
    user_id: str,
    username: str,
    roles: Optional[List[str]] = None,
    expiry_minutes: Optional[int] = None,
) -> str:
    """Generate a signed JWT access token.

    Parameters
    ----------
    user_id:        Unique user identifier.
    username:       Login handle (used to look up roles when not provided).
    roles:          Explicit role list; resolved from mock data when ``None``.
    expiry_minutes: Override token lifetime (minutes).

    Returns
    -------
    str
        Encoded JWT string.
    """
    if roles is None:
        roles = get_user_roles(username)

    now = datetime.now(tz=timezone.utc)
    minutes = expiry_minutes if expiry_minutes is not None else _get_access_expiry_minutes()
    expires_at = now + timedelta(minutes=minutes)

    payload: Dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "roles": roles,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }

    token: str = jwt.encode(payload, _get_secret(), algorithm=_get_algorithm())
    logger.debug("Token issued for user_id=%s username=%s", user_id, username)
    return token


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


def validate_token(token: str) -> Dict[str, Any]:
    """Decode and validate *token*, returning the payload.

    Raises
    ------
    jwt.ExpiredSignatureError  – token has expired.
    jwt.InvalidTokenError      – signature invalid, malformed, or missing claims.
    """
    payload = jwt.decode(
        token,
        _get_secret(),
        algorithms=[_get_algorithm()],
    )

    # Require at least one of the standard subject claims.
    if "sub" not in payload and "userId" not in payload:
        raise jwt.InvalidTokenError("Token payload missing required subject claim")

    return payload
