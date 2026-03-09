"""
UserProfileModel – represents user data stored in the database.

In a production environment this would be backed by SQLAlchemy + PostgreSQL.
The lightweight dataclass implementation here avoids hard dependencies during
unit-testing while keeping the public interface identical.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Dict, Optional


def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Return (hashed_password, salt) using PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=260_000,
    ).hex()
    return hashed, salt


@dataclass
class BaseModel:
    """Common attributes shared by all data models."""

    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class UserProfileModel(BaseModel):
    """Represents a user account with hashed credentials.

    Attributes
    ----------
    user_id:       Unique identifier (UUID string or integer).
    username:      Unique login handle.
    email:         User's email address.
    password_hash: PBKDF2 hex digest of the user's password.
    password_salt: Random salt used when hashing the password.
    is_active:     Whether the account is enabled.
    oauth_provider:  Name of OAuth2 provider (``None`` for local accounts).
    oauth_subject:   Provider-issued subject identifier.
    """

    # In-memory store used when no real DB is configured.
    _store: ClassVar[Dict[str, "UserProfileModel"]] = {}

    user_id: str = ""
    username: str = ""
    email: str = ""
    password_hash: str = ""
    password_salt: str = ""
    is_active: bool = True
    oauth_provider: Optional[str] = None
    oauth_subject: Optional[str] = None

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        user_id: str,
        username: str,
        email: str,
        password: str,
        is_active: bool = True,
    ) -> "UserProfileModel":
        """Create and persist a new local user with a hashed password."""
        hashed, salt = _hash_password(password)
        user = cls(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=hashed,
            password_salt=salt,
            is_active=is_active,
        )
        cls._store[username] = user
        return user

    @classmethod
    def create_oauth_user(
        cls,
        user_id: str,
        username: str,
        email: str,
        oauth_provider: str,
        oauth_subject: str,
    ) -> "UserProfileModel":
        """Create and persist a user authenticated via an OAuth2 provider."""
        user = cls(
            user_id=user_id,
            username=username,
            email=email,
            oauth_provider=oauth_provider,
            oauth_subject=oauth_subject,
        )
        cls._store[username] = user
        return user

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_by_username(cls, username: str) -> Optional["UserProfileModel"]:
        return cls._store.get(username)

    @classmethod
    def get_by_oauth(
        cls, provider: str, subject: str
    ) -> Optional["UserProfileModel"]:
        for user in cls._store.values():
            if user.oauth_provider == provider and user.oauth_subject == subject:
                return user
        return None

    # ------------------------------------------------------------------
    # Instance methods
    # ------------------------------------------------------------------

    def verify_password(self, password: str) -> bool:
        """Return True if *password* matches the stored hash."""
        if not self.password_hash:
            return False
        candidate, _ = _hash_password(password, self.password_salt)
        return candidate == self.password_hash

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "user_id": self.user_id,
                "username": self.username,
                "email": self.email,
                "is_active": self.is_active,
                "oauth_provider": self.oauth_provider,
            }
        )
        return base
