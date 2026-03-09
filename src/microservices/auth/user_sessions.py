"""user_sessions.py – Session model for temporary token storage.

Task 2: Session Management API Gateway.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Dict, Optional


@dataclass
class UserSession:
    """Represents an active user session with associated tokens.

    Attributes
    ----------
    session_id:    Unique session identifier.
    user_id:       Owner's user identifier.
    username:      Owner's login handle.
    access_token:  Current access JWT.
    refresh_token: Refresh JWT for renewing the access token.
    created_at:    UTC timestamp when the session was created.
    expires_at:    UTC timestamp when the session expires.
    is_active:     Whether the session is still active.
    """

    # In-memory store (keyed by session_id)
    _store: ClassVar[Dict[str, "UserSession"]] = {}

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    username: str = ""
    access_token: str = ""
    refresh_token: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    expires_at: Optional[datetime] = None
    is_active: bool = True

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        user_id: str,
        username: str,
        access_token: str,
        refresh_token: str,
        expires_at: Optional[datetime] = None,
    ) -> "UserSession":
        """Create and persist a new session."""
        session = cls(
            user_id=user_id,
            username=username,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
        cls._store[session.session_id] = session
        return session

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_by_id(cls, session_id: str) -> Optional["UserSession"]:
        return cls._store.get(session_id)

    @classmethod
    def get_by_refresh_token(cls, refresh_token: str) -> Optional["UserSession"]:
        for session in cls._store.values():
            if session.refresh_token == refresh_token and session.is_active:
                return session
        return None

    # ------------------------------------------------------------------
    # Instance methods
    # ------------------------------------------------------------------

    def is_expired(self) -> bool:
        """Return True if this session has passed its expiry time."""
        if self.expires_at is None:
            return False
        return datetime.now(tz=timezone.utc) > self.expires_at

    def terminate(self) -> None:
        """Mark this session as inactive."""
        self.is_active = False

    def update_tokens(self, access_token: str, refresh_token: str) -> None:
        """Replace the stored tokens (called on session refresh)."""
        self.access_token = access_token
        self.refresh_token = refresh_token

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "username": self.username,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
        }
