"""auth/login.py – Public JWT generation and verification API.

Provides ``generate_jwt()`` and ``verify_jwt()`` as the stable public interface
for the authentication module, delegating to the microservice jwt_util
implementation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import jwt

from microservices.auth_service.utils.jwt_util import (
    generate_token,
    validate_token,
)

__all__ = ["generate_jwt", "verify_jwt"]


def generate_jwt(
    user_id: str,
    username: str,
    roles: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    expiry_minutes: Optional[int] = None,
) -> str:
    """Generate a signed JWT for the given user.

    Parameters
    ----------
    user_id:        Unique identifier for the user.
    username:       Login handle.
    roles:          Role list; resolved from mock data when ``None``.
    permissions:    Permission list; resolved from mock data when ``None``.
    expiry_minutes: Override token lifetime in minutes.

    Returns
    -------
    Signed JWT string.

    Raises
    ------
    ValueError:  if *user_id* or *username* is empty / None.
    """
    if not user_id:
        raise ValueError("user_id must not be empty")
    if not username:
        raise ValueError("username must not be empty")

    return generate_token(
        user_id=user_id,
        username=username,
        roles=roles,
        permissions=permissions,
        expiry_minutes=expiry_minutes,
    )


def verify_jwt(token: str) -> Dict[str, Any]:
    """Validate and decode a JWT token.

    Parameters
    ----------
    token: The JWT string to verify.

    Returns
    -------
    Decoded payload dict.

    Raises
    ------
    ValueError:                  if *token* is empty or ``None``.
    jwt.ExpiredSignatureError:   if the token has expired.
    jwt.InvalidTokenError:       for any other validation failure.
    """
    if not token:
        raise ValueError("token must not be empty")

    return validate_token(token)
