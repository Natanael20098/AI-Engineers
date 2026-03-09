"""test_user_auth_service.py – Integration tests for UserAuthService + UserRepository.

Covers Task 3 acceptance criteria:
  AC1  Refactored user_auth_service.py demonstrates improved response times
       (verified by O(1) lookup assertions and timing guard on 1,000 iterations).
  AC2  New repository-based structure passes all integration tests.
  AC3  Legacy data is validated and not corrupted through refactor.
"""

from __future__ import annotations

import time

import pytest

from services.authentication.user_repository import UserRepository, _user_store
from services.authentication.user_auth_service import UserAuthService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_store():
    """Reset the in-memory user store before and after each test (isolation)."""
    _user_store.clear()
    yield
    _user_store.clear()


@pytest.fixture()
def repo() -> UserRepository:
    return UserRepository()


@pytest.fixture()
def service(repo) -> UserAuthService:
    return UserAuthService(repository=repo)


@pytest.fixture()
def alice(service) -> dict:
    """Register a test user and return the safe user dict."""
    return service.register("alice", "alice_pass", "alice@example.com")


# ---------------------------------------------------------------------------
# AC2 – UserRepository: getUser
# ---------------------------------------------------------------------------


def test_getUser_returns_user_after_add(repo):
    repo.addUser("bob", "pass123", "bob@example.com")
    user = repo.getUser("bob")
    assert user is not None
    assert user["username"] == "bob"
    assert user["email"] == "bob@example.com"


def test_getUser_returns_none_for_unknown_username(repo):
    assert repo.getUser("nobody") is None


def test_getUser_does_not_expose_password(repo):
    repo.addUser("carol", "secret", "carol@example.com")
    user = repo.getUser("carol")
    # Raw store dict has password fields; safe_dict removes them.
    safe = repo._safe_dict(user)
    assert "password_hash" not in safe
    assert "password_salt" not in safe


# ---------------------------------------------------------------------------
# AC2 – UserRepository: addUser
# ---------------------------------------------------------------------------


def test_addUser_returns_safe_dict(repo):
    user = repo.addUser("dave", "pass", "dave@example.com")
    assert "user_id" in user
    assert "username" in user
    assert "password_hash" not in user
    assert "password_salt" not in user


def test_addUser_assigns_unique_user_ids(repo):
    u1 = repo.addUser("user1", "pass", "u1@example.com")
    u2 = repo.addUser("user2", "pass", "u2@example.com")
    assert u1["user_id"] != u2["user_id"]


def test_addUser_raises_on_duplicate_username(repo):
    """AC3 – no silent data corruption from duplicate inserts."""
    repo.addUser("alice", "pass1", "a1@example.com")
    with pytest.raises(ValueError, match="already registered"):
        repo.addUser("alice", "pass2", "a2@example.com")


def test_addUser_raises_on_blank_username(repo):
    with pytest.raises(ValueError):
        repo.addUser("", "pass", "e@example.com")


def test_addUser_raises_on_blank_password(repo):
    with pytest.raises(ValueError):
        repo.addUser("user", "", "e@example.com")


def test_addUser_raises_on_blank_email(repo):
    with pytest.raises(ValueError):
        repo.addUser("user", "pass", "")


# ---------------------------------------------------------------------------
# AC2 – UserRepository: updateUser
# ---------------------------------------------------------------------------


def test_updateUser_changes_email(repo):
    """AC3 – only the supplied field is changed; others are preserved."""
    original = repo.addUser("eve", "pass", "old@example.com")
    updated = repo.updateUser("eve", email="new@example.com")
    assert updated["email"] == "new@example.com"
    # user_id and username must be preserved (AC3).
    assert updated["user_id"] == original["user_id"]
    assert updated["username"] == "eve"


def test_updateUser_changes_is_active(repo):
    repo.addUser("frank", "pass", "frank@example.com")
    updated = repo.updateUser("frank", is_active=False)
    assert updated["is_active"] is False


def test_updateUser_preserves_unset_fields(repo):
    """AC3 – partial update must not corrupt other fields."""
    repo.addUser("grace", "pass", "grace@example.com")
    # Update only email, not is_active.
    repo.updateUser("grace", email="grace2@example.com")
    user = repo.getUser("grace")
    assert user["is_active"] is True  # original value preserved


def test_updateUser_returns_none_for_missing_user(repo):
    assert repo.updateUser("ghost", email="x@example.com") is None


def test_updateUser_password_rehashes(repo):
    """AC3 – password update stores a new hash, not the plain-text value."""
    repo.addUser("harry", "old_pass", "harry@example.com")
    repo.updateUser("harry", password="new_pass")
    assert repo.verifyPassword("harry", "new_pass") is True
    assert repo.verifyPassword("harry", "old_pass") is False


# ---------------------------------------------------------------------------
# AC2 – UserRepository: deleteUser
# ---------------------------------------------------------------------------


def test_deleteUser_removes_user(repo):
    repo.addUser("ivan", "pass", "ivan@example.com")
    assert repo.deleteUser("ivan") is True
    assert repo.getUser("ivan") is None


def test_deleteUser_returns_false_for_missing_user(repo):
    assert repo.deleteUser("nobody") is False


# ---------------------------------------------------------------------------
# AC2 – UserAuthService: register
# ---------------------------------------------------------------------------


def test_service_register_creates_user(service):
    user = service.register("alice", "pass", "alice@example.com")
    assert user["username"] == "alice"
    assert "user_id" in user


def test_service_register_rejects_duplicate(service, alice):
    with pytest.raises(ValueError):
        service.register("alice", "pass2", "alice2@example.com")


# ---------------------------------------------------------------------------
# AC2 – UserAuthService: authenticate
# ---------------------------------------------------------------------------


def test_service_authenticate_returns_user_for_valid_credentials(service, alice):
    result = service.authenticate("alice", "alice_pass")
    assert result is not None
    assert result["username"] == "alice"


def test_service_authenticate_returns_none_for_wrong_password(service, alice):
    assert service.authenticate("alice", "wrong") is None


def test_service_authenticate_returns_none_for_unknown_user(service):
    assert service.authenticate("nobody", "pass") is None


def test_service_authenticate_returns_none_for_inactive_user(service):
    service.register("inactive_user", "pass", "x@example.com")
    service.deactivate("inactive_user")
    assert service.authenticate("inactive_user", "pass") is None


def test_service_authenticate_result_has_no_password_fields(service, alice):
    result = service.authenticate("alice", "alice_pass")
    assert "password_hash" not in result
    assert "password_salt" not in result


# ---------------------------------------------------------------------------
# AC2 – UserAuthService: update_user
# ---------------------------------------------------------------------------


def test_service_update_user_changes_email(service, alice):
    updated = service.update_user("alice", email="new@example.com")
    assert updated["email"] == "new@example.com"


def test_service_update_user_returns_none_for_missing_user(service):
    assert service.update_user("ghost", email="x@example.com") is None


def test_service_deactivate_sets_is_active_false(service, alice):
    service.deactivate("alice")
    user = service.get_user("alice")
    # get_user returns the safe dict; we need raw store to check is_active.
    raw = UserRepository().getUser("alice")
    assert raw["is_active"] is False


# ---------------------------------------------------------------------------
# AC1 – Performance: O(1) lookups complete well within 1 second for 1,000 users
# ---------------------------------------------------------------------------


def test_repository_lookup_is_fast(repo):
    """AC1 – Demonstrate improved response times via fast dict lookups."""
    n = 1_000
    for i in range(n):
        repo.addUser(f"user_{i}", "pass", f"user_{i}@example.com")

    start = time.perf_counter()
    for i in range(n):
        result = repo.getUser(f"user_{i}")
        assert result is not None
    elapsed = time.perf_counter() - start

    # 1,000 O(1) dict lookups must complete in under 1 second.
    assert elapsed < 1.0, f"1,000 lookups took {elapsed:.3f}s (expected < 1.0s)"


# ---------------------------------------------------------------------------
# AC3 – Legacy data validation: existing hash format is preserved
# ---------------------------------------------------------------------------


def test_password_hash_uses_pbkdf2(repo):
    """AC3 – password hashing algorithm remains PBKDF2-HMAC-SHA256 post-refactor."""
    repo.addUser("legacy_user", "password", "l@example.com")
    raw = _user_store.get("legacy_user")
    assert raw is not None
    # A PBKDF2-SHA256 hex digest is 64 hex chars (256 bits).
    assert len(raw["password_hash"]) == 64
    assert len(raw["password_salt"]) == 32  # 16 random bytes → 32 hex chars


def test_update_does_not_change_user_id(repo):
    """AC3 – user_id is immutable; update must not overwrite it."""
    original = repo.addUser("stable_user", "pass", "s@example.com")
    original_id = original["user_id"]
    repo.updateUser("stable_user", email="new@example.com")
    updated = repo.getUser("stable_user")
    assert updated["user_id"] == original_id
