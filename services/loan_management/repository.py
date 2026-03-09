"""
repository.py – LoanRepository for the Loan Management microservice.

Migrated from the legacy Java LoanRepository.  This implementation keeps
loans in an in-memory dict so the service is self-contained for testing;
a production deployment would swap this for a SQLAlchemy-backed store
driven by DATABASE_URL.

Supported loan statuses
-----------------------
pending    – initial state after creation
approved   – loan has been approved by an underwriter
rejected   – loan has been rejected
disbursed  – funds have been disbursed to the applicant
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Module-level in-memory store (shared via import, clearable in tests)
# ---------------------------------------------------------------------------

_loan_store: Dict[str, Dict[str, Any]] = {}

VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "approved", "rejected", "disbursed"}
)


class LoanRepository:
    """CRUD operations for LoanApplication entities."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        applicant_id: str,
        amount: float,
        term_months: int,
        purpose: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist a new LoanApplication and return it.

        Parameters
        ----------
        applicant_id:
            Unique identifier of the loan applicant.
        amount:
            Requested loan amount (must be > 0).
        term_months:
            Repayment term in months (must be > 0).
        purpose:
            Optional free-text description of the loan purpose.

        Raises
        ------
        ValueError
            If *amount* or *term_months* are invalid.
        """
        if not isinstance(amount, (int, float)) or amount <= 0:
            raise ValueError("amount must be a positive number")
        if not isinstance(term_months, int) or term_months <= 0:
            raise ValueError("term_months must be a positive integer")

        loan_id = str(uuid.uuid4())
        loan: Dict[str, Any] = {
            "loan_id": loan_id,
            "applicant_id": applicant_id,
            "amount": float(amount),
            "term_months": term_months,
            "status": "pending",
        }
        if purpose is not None:
            loan["purpose"] = purpose

        _loan_store[loan_id] = loan
        return loan

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def find_by_id(self, loan_id: str) -> Optional[Dict[str, Any]]:
        """Return the loan dict for *loan_id*, or ``None`` if not found."""
        return _loan_store.get(loan_id)

    def find_all(self) -> list[Dict[str, Any]]:
        """Return all stored loan applications."""
        return list(_loan_store.values())

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_status(
        self, loan_id: str, new_status: str
    ) -> Optional[Dict[str, Any]]:
        """Update the status of a loan application.

        Returns the updated loan dict, or ``None`` if *loan_id* is unknown.

        Raises
        ------
        ValueError
            If *new_status* is not a recognised status value.
        """
        if new_status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{new_status}'. "
                f"Must be one of: {sorted(VALID_STATUSES)}"
            )
        loan = _loan_store.get(loan_id)
        if loan is None:
            return None
        loan["status"] = new_status
        return loan

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, loan_id: str) -> bool:
        """Remove a loan application.

        Returns ``True`` if the record existed and was deleted, ``False``
        if *loan_id* was not found.
        """
        if loan_id in _loan_store:
            del _loan_store[loan_id]
            return True
        return False
