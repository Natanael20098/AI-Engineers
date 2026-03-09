"""tests/unit/test_loan_application_service.py – Unit tests for LoanRepository.

Task 1 Acceptance Criteria:
- All methods in LoanApplicationService have >80% coverage.
- Tests fail for invalid inputs and edge cases.
- Test suite runs without errors in all environments.

Covers:
- LoanRepository.create() with valid, invalid, and boundary inputs.
- LoanRepository.find_by_id() for existing and missing loans.
- LoanRepository.find_all() with empty and populated store.
- LoanRepository.update_status() with valid and invalid statuses.
- LoanRepository.delete() for existing and missing loans.
- ValueError raised for all constraint violations.
- No sensitive data appears in raised error messages or logs.
"""

from __future__ import annotations

import uuid

import pytest

import loan_management.repository as repo_module
from loan_management.repository import LoanRepository, VALID_STATUSES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_store():
    """Reset in-memory loan store before and after every test."""
    repo_module._loan_store.clear()
    yield
    repo_module._loan_store.clear()


@pytest.fixture()
def repo() -> LoanRepository:
    return LoanRepository()


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


class TestCreate:
    def test_returns_loan_dict(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        assert isinstance(loan, dict)

    def test_loan_has_required_fields(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        for field in ("loan_id", "applicant_id", "amount", "term_months", "status"):
            assert field in loan, f"Missing required field: '{field}'"

    def test_initial_status_is_pending(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        assert loan["status"] == "pending"

    def test_loan_id_is_valid_uuid(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        assert isinstance(loan["loan_id"], str)
        uuid.UUID(loan["loan_id"])  # raises ValueError if not a valid UUID

    def test_unique_ids_for_multiple_loans(self, repo):
        l1 = repo.create("app-1", 1000.0, 6)
        l2 = repo.create("app-2", 2000.0, 12)
        assert l1["loan_id"] != l2["loan_id"]

    def test_applicant_id_stored_correctly(self, repo):
        loan = repo.create("app-XYZ-999", 5000.0, 24)
        assert loan["applicant_id"] == "app-XYZ-999"

    def test_amount_stored_as_float(self, repo):
        loan = repo.create("app-1", 7500, 12)
        assert isinstance(loan["amount"], float)
        assert loan["amount"] == 7500.0

    def test_term_months_stored_correctly(self, repo):
        loan = repo.create("app-1", 10000.0, 36)
        assert loan["term_months"] == 36

    def test_purpose_stored_when_provided(self, repo):
        loan = repo.create("app-1", 10000.0, 12, purpose="Home renovation")
        assert loan["purpose"] == "Home renovation"

    def test_purpose_absent_when_not_provided(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        assert "purpose" not in loan

    def test_loan_persisted_in_store(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        assert repo.find_by_id(loan["loan_id"]) is not None

    def test_multiple_loans_all_persisted(self, repo):
        l1 = repo.create("app-1", 1000.0, 6)
        l2 = repo.create("app-2", 2000.0, 12)
        l3 = repo.create("app-3", 3000.0, 24)
        assert len(repo_module._loan_store) == 3
        for loan in (l1, l2, l3):
            assert loan["loan_id"] in repo_module._loan_store

    def test_integer_amount_accepted(self, repo):
        loan = repo.create("app-1", 5000, 12)
        assert loan["amount"] == 5000.0

    # --- Negative / edge cases ---

    def test_zero_amount_raises_value_error(self, repo):
        with pytest.raises(ValueError, match="amount"):
            repo.create("app-1", 0, 12)

    def test_negative_amount_raises_value_error(self, repo):
        with pytest.raises(ValueError, match="amount"):
            repo.create("app-1", -100.0, 12)

    def test_very_small_negative_amount_raises_value_error(self, repo):
        with pytest.raises(ValueError, match="amount"):
            repo.create("app-1", -0.01, 12)

    def test_zero_term_months_raises_value_error(self, repo):
        with pytest.raises(ValueError, match="term_months"):
            repo.create("app-1", 10000.0, 0)

    def test_negative_term_months_raises_value_error(self, repo):
        with pytest.raises(ValueError, match="term_months"):
            repo.create("app-1", 10000.0, -6)

    def test_float_term_months_raises_value_error(self, repo):
        with pytest.raises(ValueError, match="term_months"):
            repo.create("app-1", 10000.0, 12.5)  # type: ignore[arg-type]

    def test_invalid_inputs_do_not_persist_to_store(self, repo):
        """A failed create must not leave a partial record in the store."""
        try:
            repo.create("app-1", -999.0, 12)
        except ValueError:
            pass
        assert len(repo_module._loan_store) == 0

    def test_error_message_does_not_expose_applicant_id(self, repo):
        """ValueError for invalid amount must not reveal the applicant ID."""
        try:
            repo.create("secret-applicant-99", -999.99, 12)
        except ValueError as exc:
            assert "secret-applicant-99" not in str(exc)

    def test_error_message_does_not_expose_amount(self, repo):
        """ValueError message must not expose the rejected numeric value."""
        try:
            repo.create("app-1", -999.99, 12)
        except ValueError as exc:
            assert "-999.99" not in str(exc)


# ---------------------------------------------------------------------------
# find_by_id()
# ---------------------------------------------------------------------------


class TestFindById:
    def test_returns_existing_loan(self, repo):
        loan = repo.create("app-1", 5000.0, 6)
        found = repo.find_by_id(loan["loan_id"])
        assert found is not None
        assert found["loan_id"] == loan["loan_id"]

    def test_returned_loan_has_correct_applicant(self, repo):
        loan = repo.create("specific-applicant", 5000.0, 6)
        found = repo.find_by_id(loan["loan_id"])
        assert found["applicant_id"] == "specific-applicant"

    def test_returns_none_for_missing_id(self, repo):
        result = repo.find_by_id("non-existent-id")
        assert result is None

    def test_returns_correct_loan_when_multiple_exist(self, repo):
        l1 = repo.create("app-1", 1000.0, 6)
        l2 = repo.create("app-2", 2000.0, 12)
        assert repo.find_by_id(l1["loan_id"])["applicant_id"] == "app-1"
        assert repo.find_by_id(l2["loan_id"])["applicant_id"] == "app-2"

    def test_returns_none_for_empty_string_id(self, repo):
        result = repo.find_by_id("")
        assert result is None

    def test_returns_none_on_empty_store(self, repo):
        result = repo.find_by_id("any-id")
        assert result is None


# ---------------------------------------------------------------------------
# find_all()
# ---------------------------------------------------------------------------


class TestFindAll:
    def test_returns_empty_list_when_no_loans(self, repo):
        result = repo.find_all()
        assert result == []

    def test_returns_list_type(self, repo):
        assert isinstance(repo.find_all(), list)

    def test_returns_all_created_loans(self, repo):
        repo.create("app-1", 1000.0, 6)
        repo.create("app-2", 2000.0, 12)
        repo.create("app-3", 3000.0, 24)
        assert len(repo.find_all()) == 3

    def test_each_item_is_loan_dict_with_loan_id(self, repo):
        repo.create("app-1", 5000.0, 12)
        loans = repo.find_all()
        assert all("loan_id" in loan for loan in loans)

    def test_count_increases_after_each_create(self, repo):
        assert len(repo.find_all()) == 0
        repo.create("app-1", 1000.0, 6)
        assert len(repo.find_all()) == 1
        repo.create("app-2", 2000.0, 12)
        assert len(repo.find_all()) == 2

    def test_all_loans_have_pending_initial_status(self, repo):
        repo.create("app-1", 1000.0, 6)
        repo.create("app-2", 2000.0, 12)
        for loan in repo.find_all():
            assert loan["status"] == "pending"

    def test_all_applicant_ids_present(self, repo):
        ids = ["app-a", "app-b", "app-c"]
        for aid in ids:
            repo.create(aid, 1000.0, 6)
        applicant_ids = {loan["applicant_id"] for loan in repo.find_all()}
        assert set(ids) == applicant_ids


# ---------------------------------------------------------------------------
# update_status()
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    def test_updates_status_to_approved(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        updated = repo.update_status(loan["loan_id"], "approved")
        assert updated["status"] == "approved"

    def test_updates_status_to_rejected(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        updated = repo.update_status(loan["loan_id"], "rejected")
        assert updated["status"] == "rejected"

    def test_updates_status_to_disbursed(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        updated = repo.update_status(loan["loan_id"], "disbursed")
        assert updated["status"] == "disbursed"

    def test_updates_status_back_to_pending(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        repo.update_status(loan["loan_id"], "approved")
        updated = repo.update_status(loan["loan_id"], "pending")
        assert updated["status"] == "pending"

    def test_returns_updated_loan_dict(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        result = repo.update_status(loan["loan_id"], "approved")
        assert isinstance(result, dict)
        assert result["loan_id"] == loan["loan_id"]

    def test_returns_none_for_missing_loan(self, repo):
        result = repo.update_status("non-existent", "approved")
        assert result is None

    def test_all_valid_statuses_accepted(self, repo):
        for status_value in VALID_STATUSES:
            loan = repo.create("app-1", 1000.0, 6)
            result = repo.update_status(loan["loan_id"], status_value)
            assert result is not None
            assert result["status"] == status_value

    def test_updated_status_persists_in_store(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        repo.update_status(loan["loan_id"], "approved")
        assert repo.find_by_id(loan["loan_id"])["status"] == "approved"

    def test_other_fields_unchanged_after_update(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        updated = repo.update_status(loan["loan_id"], "approved")
        assert updated["applicant_id"] == "app-1"
        assert updated["amount"] == 10000.0
        assert updated["term_months"] == 12

    # --- Negative cases ---

    def test_invalid_status_raises_value_error(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        with pytest.raises(ValueError, match="Invalid status"):
            repo.update_status(loan["loan_id"], "unknown")

    def test_empty_status_raises_value_error(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        with pytest.raises(ValueError):
            repo.update_status(loan["loan_id"], "")

    def test_uppercase_status_raises_value_error(self, repo):
        loan = repo.create("app-1", 10000.0, 12)
        with pytest.raises(ValueError):
            repo.update_status(loan["loan_id"], "APPROVED")

    def test_error_message_does_not_expose_loan_id(self, repo):
        """ValueError for invalid status must not reveal the loan's ID."""
        loan = repo.create("app-secret-99", 10000.0, 12)
        try:
            repo.update_status(loan["loan_id"], "bad_status")
        except ValueError as exc:
            assert loan["loan_id"] not in str(exc)

    def test_invalid_status_does_not_mutate_existing_status(self, repo):
        """Failing update_status must leave original status intact."""
        loan = repo.create("app-1", 10000.0, 12)
        try:
            repo.update_status(loan["loan_id"], "invalid_status")
        except ValueError:
            pass
        assert repo.find_by_id(loan["loan_id"])["status"] == "pending"


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


class TestDelete:
    def test_returns_true_for_existing_loan(self, repo):
        loan = repo.create("app-1", 5000.0, 12)
        assert repo.delete(loan["loan_id"]) is True

    def test_returns_false_for_missing_loan(self, repo):
        assert repo.delete("non-existent") is False

    def test_deleted_loan_not_findable(self, repo):
        loan = repo.create("app-1", 5000.0, 12)
        repo.delete(loan["loan_id"])
        assert repo.find_by_id(loan["loan_id"]) is None

    def test_deleting_one_loan_leaves_others(self, repo):
        l1 = repo.create("app-1", 1000.0, 6)
        l2 = repo.create("app-2", 2000.0, 12)
        repo.delete(l1["loan_id"])
        assert repo.find_by_id(l1["loan_id"]) is None
        assert repo.find_by_id(l2["loan_id"]) is not None

    def test_delete_reduces_count(self, repo):
        loan = repo.create("app-1", 5000.0, 12)
        assert len(repo.find_all()) == 1
        repo.delete(loan["loan_id"])
        assert len(repo.find_all()) == 0

    def test_double_delete_returns_false(self, repo):
        loan = repo.create("app-1", 5000.0, 12)
        repo.delete(loan["loan_id"])
        assert repo.delete(loan["loan_id"]) is False

    def test_delete_empty_store_returns_false(self, repo):
        assert repo.delete("any-id") is False

    def test_delete_all_loans_empties_store(self, repo):
        l1 = repo.create("app-1", 1000.0, 6)
        l2 = repo.create("app-2", 2000.0, 12)
        repo.delete(l1["loan_id"])
        repo.delete(l2["loan_id"])
        assert repo.find_all() == []


# ---------------------------------------------------------------------------
# VALID_STATUSES constant
# ---------------------------------------------------------------------------


class TestValidStatuses:
    def test_contains_pending(self):
        assert "pending" in VALID_STATUSES

    def test_contains_approved(self):
        assert "approved" in VALID_STATUSES

    def test_contains_rejected(self):
        assert "rejected" in VALID_STATUSES

    def test_contains_disbursed(self):
        assert "disbursed" in VALID_STATUSES

    def test_exactly_four_statuses(self):
        assert len(VALID_STATUSES) == 4

    def test_is_frozenset(self):
        assert isinstance(VALID_STATUSES, frozenset)


# ---------------------------------------------------------------------------
# Integration between create / update_status / delete
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_create_approve_disburse_delete(self, repo):
        """Full lifecycle: create → approve → disburse → delete."""
        loan = repo.create("lifecycle-app", 30000.0, 48)
        loan_id = loan["loan_id"]

        updated = repo.update_status(loan_id, "approved")
        assert updated["status"] == "approved"

        disbursed = repo.update_status(loan_id, "disbursed")
        assert disbursed["status"] == "disbursed"

        deleted = repo.delete(loan_id)
        assert deleted is True
        assert repo.find_by_id(loan_id) is None

    def test_create_reject_then_no_longer_findable_after_delete(self, repo):
        loan = repo.create("rejected-app", 5000.0, 6)
        loan_id = loan["loan_id"]
        repo.update_status(loan_id, "rejected")
        repo.delete(loan_id)
        assert repo.find_by_id(loan_id) is None

    def test_independent_loans_do_not_interfere(self, repo):
        """Status changes to one loan must not affect another."""
        l1 = repo.create("app-1", 10000.0, 12)
        l2 = repo.create("app-2", 20000.0, 24)

        repo.update_status(l1["loan_id"], "approved")

        assert repo.find_by_id(l1["loan_id"])["status"] == "approved"
        assert repo.find_by_id(l2["loan_id"])["status"] == "pending"
