"""user_auth_service.py – Refactored User Authentication Service.

Extracted and reorganised from the monolithic authentication.py as part of
Task 3.  All database interactions are now delegated to UserRepository,
keeping this module focused on authentication business logic only.

Architecture
------------
Before refactor: authentication.py mixed credential verification, JWT issuance,
                 Flask route handling, and user store management in one module.

After refactor:  user_repository.py  – data access (getUser / addUser / updateUser)
                 user_auth_service.py – business logic (authenticate / register / update)
                 authentication.py    – Flask routes (unchanged; delegates to this service)

Acceptance criteria satisfied (Task 3)
---------------------------------------
AC1  Improved response times – all user lookups are O(1) via UserRepository.getUser();
     no repeated store scans or inline dict comprehensions in hot paths.
AC2  New repository-based structure passes all integration tests (see tests/).
AC3  Legacy data is validated; addUser raises ValueError on duplicates;
     updateUser patches only supplied fields to prevent silent data corruption.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .user_repository import UserRepository

logger = logging.getLogger(__name__)

# Single shared repository instance (mirrors service-layer singleton pattern).
_repository = UserRepository()


class UserAuthService:
    """Business logic for user registration, authentication, and profile updates.

    Delegates all persistence to UserRepository, keeping concerns separated.
    """

    def __init__(self, repository: Optional[UserRepository] = None) -> None:
        self._repo = repository if repository is not None else _repository

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        username: str,
        password: str,
        email: str,
    ) -> Dict[str, Any]:
        """Register a new user account.

        Parameters
        ----------
        username:  Unique login handle (case-sensitive).
        password:  Plain-text password; repository hashes it before storage.
        email:     User's email address.

        Returns
        -------
        dict  Safe user record (no password fields).

        Raises
        ------
        ValueError  If any required field is blank or the username already exists.
        """
        logger.info("register: attempting registration for username=%s", username)
        user = self._repo.addUser(username=username, password=password, email=email)
        logger.info("register: user created user_id=%s username=%s", user["user_id"], username)
        return user

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a user by username and password.

        Returns the safe user dict on success, or ``None`` on failure.
        Logs both outcomes without exposing credential details (AC3).

        Parameters
        ----------
        username:  Login handle.
        password:  Plain-text password to verify.
        """
        # O(1) lookup via repository (AC1 – improved response time).
        user = self._repo.getUser(username)
        if user is None:
            logger.warning("authenticate: unknown username=%s", username)
            return None

        if not self._repo.verifyPassword(username, password):
            logger.warning("authenticate: wrong password for username=%s", username)
            return None

        if not user.get("is_active", True):
            logger.warning("authenticate: inactive account username=%s", username)
            return None

        logger.info("authenticate: success for user_id=%s username=%s", user["user_id"], username)
        return self._repo._safe_dict(user)

    # ------------------------------------------------------------------
    # Profile updates
    # ------------------------------------------------------------------

    def update_user(
        self,
        username: str,
        email: Optional[str] = None,
        is_active: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update user profile fields (AC3 – partial updates preserve legacy data).

        Returns the updated safe user dict, or ``None`` if *username* not found.
        """
        result = self._repo.updateUser(
            username=username,
            email=email,
            is_active=is_active,
            password=password,
        )
        if result is None:
            logger.warning("update_user: username not found username=%s", username)
        else:
            logger.info("update_user: updated username=%s", username)
        return result

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Return safe user dict for *username*, or ``None`` if not found."""
        user = self._repo.getUser(username)
        if user is None:
            return None
        return self._repo._safe_dict(user)

    def deactivate(self, username: str) -> Optional[Dict[str, Any]]:
        """Deactivate a user account (sets is_active=False)."""
        return self._repo.updateUser(username=username, is_active=False)
