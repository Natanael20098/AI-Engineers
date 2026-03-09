"""
Tests for data_access_layer.py – Refactored SQLAlchemy data access layer.

Uses an in-memory SQLite database so no PostgreSQL instance is required.

Covers all acceptance criteria:
  AC1  Refactored code is operational and passes all tests.
  AC2  Does not compromise data integrity and performance.

Tests verify:
  - CRUD operations function correctly
  - Transaction rollback fires correctly on error
  - Data consistency is maintained across sessions
  - Backward-compatible dict representation is preserved
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from data_access_layer import (
    Base,
    LoanApplicationDAL,
    LoanApplicationORM,
    VALID_STATUSES,
    build_session_factory,
    get_db_session,
    get_engine,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def engine():
    """Fresh in-memory SQLite engine per test function."""
    eng = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return build_session_factory(engine)


@pytest.fixture()
def dal():
    return LoanApplicationDAL()


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# AC1 – CREATE
# ---------------------------------------------------------------------------


def test_create_loan_persists_record(dal, session_factory):
    """AC1: create writes a new LoanApplicationORM to the database."""
    loan_id = _new_id()
    with get_db_session(session_factory) as session:
        loan = dal.create(
            session,
            loan_id=loan_id,
            applicant_id="app-001",
            amount=10000.0,
            term_months=12,
        )
        assert loan.loan_id == loan_id
        assert loan.applicant_id == "app-001"
        assert loan.amount == 10000.0
        assert loan.term_months == 12
        assert loan.status == "pending"


def test_create_loan_with_purpose(dal, session_factory):
    loan_id = _new_id()
    with get_db_session(session_factory) as session:
        loan = dal.create(
            session,
            loan_id=loan_id,
            applicant_id="app-002",
            amount=5000.0,
            term_months=6,
            purpose="Home renovation",
        )
        assert loan.purpose == "Home renovation"


def test_create_loan_invalid_amount_raises_value_error(dal, session_factory):
    with get_db_session(session_factory) as session:
        with pytest.raises(ValueError, match="amount must be a positive number"):
            dal.create(session, _new_id(), "app-003", -1000.0, 12)


def test_create_loan_zero_amount_raises_value_error(dal, session_factory):
    with get_db_session(session_factory) as session:
        with pytest.raises(ValueError):
            dal.create(session, _new_id(), "app-004", 0, 12)


def test_create_loan_invalid_term_raises_value_error(dal, session_factory):
    with get_db_session(session_factory) as session:
        with pytest.raises(ValueError, match="term_months must be a positive integer"):
            dal.create(session, _new_id(), "app-005", 5000.0, 0)


# ---------------------------------------------------------------------------
# AC1 – READ
# ---------------------------------------------------------------------------


def test_find_by_id_returns_existing_loan(dal, session_factory):
    """AC1: find_by_id returns the correct loan after creation."""
    loan_id = _new_id()
    with get_db_session(session_factory) as session:
        dal.create(session, loan_id, "app-010", 8000.0, 24)

    with get_db_session(session_factory) as session:
        found = dal.find_by_id(session, loan_id)
        assert found is not None
        assert found.loan_id == loan_id
        assert found.applicant_id == "app-010"


def test_find_by_id_returns_none_for_missing_record(dal, session_factory):
    with get_db_session(session_factory) as session:
        result = dal.find_by_id(session, "non-existent-id")
        assert result is None


def test_find_all_returns_all_loans(dal, session_factory):
    """AC2: find_all returns every stored loan application."""
    ids = [_new_id() for _ in range(3)]
    with get_db_session(session_factory) as session:
        for i, lid in enumerate(ids):
            dal.create(session, lid, f"app-{i}", (i + 1) * 1000.0, 6)

    with get_db_session(session_factory) as session:
        all_loans = dal.find_all(session)
        assert len(all_loans) == 3
        stored_ids = {loan.loan_id for loan in all_loans}
        assert stored_ids == set(ids)


def test_find_all_returns_empty_list_when_no_loans(dal, session_factory):
    with get_db_session(session_factory) as session:
        assert dal.find_all(session) == []


# ---------------------------------------------------------------------------
# AC1 – UPDATE
# ---------------------------------------------------------------------------


def test_update_status_sets_new_status(dal, session_factory):
    """AC1 + AC2: update_status modifies the record and data is consistent."""
    loan_id = _new_id()
    with get_db_session(session_factory) as session:
        dal.create(session, loan_id, "app-020", 15000.0, 18)

    with get_db_session(session_factory) as session:
        updated = dal.update_status(session, loan_id, "approved")
        assert updated is not None
        assert updated.status == "approved"

    # Verify persistence
    with get_db_session(session_factory) as session:
        loan = dal.find_by_id(session, loan_id)
        assert loan.status == "approved"


def test_update_status_to_all_valid_statuses(dal, session_factory):
    """AC2: all valid status transitions succeed."""
    for status_value in VALID_STATUSES:
        loan_id = _new_id()
        with get_db_session(session_factory) as session:
            dal.create(session, loan_id, "app-021", 1000.0, 1)
        with get_db_session(session_factory) as session:
            result = dal.update_status(session, loan_id, status_value)
            assert result.status == status_value


def test_update_status_invalid_value_raises_value_error(dal, session_factory):
    """AC2: invalid status values are rejected before database write."""
    loan_id = _new_id()
    with get_db_session(session_factory) as session:
        dal.create(session, loan_id, "app-022", 3000.0, 6)

    with get_db_session(session_factory) as session:
        with pytest.raises(ValueError, match="Invalid status"):
            dal.update_status(session, loan_id, "unknown_status")


def test_update_status_returns_none_for_missing_loan(dal, session_factory):
    with get_db_session(session_factory) as session:
        result = dal.update_status(session, "no-such-id", "approved")
        assert result is None


# ---------------------------------------------------------------------------
# AC1 – DELETE
# ---------------------------------------------------------------------------


def test_delete_removes_loan_from_database(dal, session_factory):
    """AC1 + AC2: delete ensures the record is no longer retrievable."""
    loan_id = _new_id()
    with get_db_session(session_factory) as session:
        dal.create(session, loan_id, "app-030", 2000.0, 3)

    with get_db_session(session_factory) as session:
        deleted = dal.delete(session, loan_id)
        assert deleted is True

    with get_db_session(session_factory) as session:
        assert dal.find_by_id(session, loan_id) is None


def test_delete_returns_false_for_missing_loan(dal, session_factory):
    with get_db_session(session_factory) as session:
        assert dal.delete(session, "non-existent") is False


# ---------------------------------------------------------------------------
# AC2 – Transaction rollback (data integrity)
# ---------------------------------------------------------------------------


def test_transaction_rollback_on_error_does_not_persist(dal, session_factory):
    """AC2: SQLAlchemy rollback on error keeps the database consistent."""
    loan_id = _new_id()

    # Simulate an error mid-transaction using a context manager
    try:
        with get_db_session(session_factory) as session:
            dal.create(session, loan_id, "app-040", 5000.0, 12)
            # Force an error to trigger rollback
            raise SQLAlchemyError("simulated database error")
    except SQLAlchemyError:
        pass  # Expected

    # The loan must NOT have been committed
    with get_db_session(session_factory) as session:
        assert dal.find_by_id(session, loan_id) is None


def test_successful_transaction_is_committed(dal, session_factory):
    """AC2: data written in a successful transaction persists."""
    loan_id = _new_id()
    with get_db_session(session_factory) as session:
        dal.create(session, loan_id, "app-041", 7000.0, 9)

    # Verify commit via a separate session
    with get_db_session(session_factory) as session:
        loan = dal.find_by_id(session, loan_id)
        assert loan is not None
        assert loan.amount == 7000.0


# ---------------------------------------------------------------------------
# AC2 – Backward-compatible dict representation
# ---------------------------------------------------------------------------


def test_to_dict_returns_backward_compatible_format(dal, session_factory):
    """AC2: to_dict() mirrors the legacy dict format from LoanRepository."""
    loan_id = _new_id()
    with get_db_session(session_factory) as session:
        loan = dal.create(
            session, loan_id, "app-050", 12000.0, 24, purpose="Education"
        )
        d = loan.to_dict()

    assert d["loan_id"] == loan_id
    assert d["applicant_id"] == "app-050"
    assert d["amount"] == 12000.0
    assert d["term_months"] == 24
    assert d["status"] == "pending"
    assert d["purpose"] == "Education"


def test_to_dict_without_purpose_omits_purpose_key(dal, session_factory):
    loan_id = _new_id()
    with get_db_session(session_factory) as session:
        loan = dal.create(session, loan_id, "app-051", 3000.0, 6)
        d = loan.to_dict()
    assert "purpose" not in d


# ---------------------------------------------------------------------------
# AC2 – Data consistency across multiple operations
# ---------------------------------------------------------------------------


def test_multiple_loans_are_independent(dal, session_factory):
    """AC2: modifying one loan does not affect others."""
    loan_a = _new_id()
    loan_b = _new_id()

    with get_db_session(session_factory) as session:
        dal.create(session, loan_a, "app-a", 1000.0, 1)
        dal.create(session, loan_b, "app-b", 2000.0, 2)

    with get_db_session(session_factory) as session:
        dal.update_status(session, loan_a, "approved")

    with get_db_session(session_factory) as session:
        assert dal.find_by_id(session, loan_a).status == "approved"
        assert dal.find_by_id(session, loan_b).status == "pending"
