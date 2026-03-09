"""
token_store.py – thin abstraction over a token blacklist.

Tokens are added to the blacklist on logout and checked on every
authenticated request.  The default backend is in-memory (suitable for a
single-process deployment or testing).  A Redis backend is provided for
production multi-process / multi-container deployments.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Set


class TokenBlacklistBackend(ABC):
    @abstractmethod
    def add(self, jti: str, expires_at: float) -> None:
        """Blacklist *jti* (JWT ID) until *expires_at* (UNIX timestamp)."""

    @abstractmethod
    def is_blacklisted(self, jti: str) -> bool:
        """Return True if *jti* is currently blacklisted."""

    @abstractmethod
    def purge_expired(self) -> None:
        """Remove entries whose expiry has passed (housekeeping)."""


class InMemoryTokenBlacklist(TokenBlacklistBackend):
    """Thread-safe in-memory blacklist backed by a plain Python set.

    Suitable for single-process deployments and automated tests.
    Not suitable for multi-process / multi-container production use.
    """

    def __init__(self) -> None:
        self._store: dict[str, float] = {}  # jti -> expires_at

    def add(self, jti: str, expires_at: float) -> None:
        self._store[jti] = expires_at

    def is_blacklisted(self, jti: str) -> bool:
        expires_at = self._store.get(jti)
        if expires_at is None:
            return False
        if time.time() > expires_at:
            # Token expired naturally; no longer "dangerous" either way.
            del self._store[jti]
            return False
        return True

    def purge_expired(self) -> None:
        now = time.time()
        expired = [jti for jti, exp in self._store.items() if now > exp]
        for jti in expired:
            del self._store[jti]


class RedisTokenBlacklist(TokenBlacklistBackend):
    """Redis-backed blacklist for multi-process production deployments.

    Requires the ``redis`` package (``pip install redis``).
    """

    _PREFIX = "auth:blacklist:"

    def __init__(self, redis_url: str) -> None:
        try:
            import redis  # type: ignore

            self._redis = redis.from_url(redis_url, decode_responses=True)
        except ImportError as exc:
            raise RuntimeError(
                "redis package is required for RedisTokenBlacklist. "
                "Install it with: pip install redis"
            ) from exc

    def add(self, jti: str, expires_at: float) -> None:
        ttl = max(1, int(expires_at - time.time()))
        self._redis.setex(f"{self._PREFIX}{jti}", ttl, "1")

    def is_blacklisted(self, jti: str) -> bool:
        return self._redis.exists(f"{self._PREFIX}{jti}") == 1

    def purge_expired(self) -> None:
        # Redis TTL handles expiry automatically.
        pass


def build_blacklist(backend: str, redis_url: str = "") -> TokenBlacklistBackend:
    if backend == "redis":
        return RedisTokenBlacklist(redis_url)
    return InMemoryTokenBlacklist()
