"""
data_access_layer.py – Refactored data access layer using SQLAlchemy.

Migrated from legacy tightly-coupled data access patterns to a clean,
session-managed SQLAlchemy layer.  Backward-compatible with the
LoanApplication data format used throughout the microservice ecosystem.

Design decisions
----------------
- ``get_engine()`` reads DATABASE_URL from the environment; falls back to
  an in-memory SQLite database for testing and local development.
- ``SessionLocal`` is a configured ``sessionmaker`` factory; callers obtain
  a session via the ``get_db_session()`` context manager to ensure automatic
  commit/rollback and guaranteed close.
- ``LoanApplicationORM`` mirrors the domain fields defined in
  ``loan_management/repository.py`` (backward-compatible data format).
- ``LoanApplicationDAL`` wraps all CRUD operations with explicit transaction
  management; any ``SQLAlchemyError`` triggers a rollback before re-raising.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from sqlalchemy import Column, Float, Integer, String, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ---------------------------------------------------------------------------
# Valid status values – backward-compatible with repository.py
# ---------------------------------------------------------------------------

VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "approved", "rejected", "disbursed"}
)

# ---------------------------------------------------------------------------
# Database engine
# ---------------------------------------------------------------------------


def get_engine(database_url: Optional[str] = None):
    """Return a SQLAlchemy engine.

    Uses *database_url* when provided; otherwise falls back to the
    ``DATABASE_URL`` environment variable, and finally to an in-memory
    SQLite instance for test/local usage.
    """
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///:memory:")
    connect_args = {}
    if url.startswith("sqlite"):
        # Required for SQLite to allow the same connection across threads
        connect_args = {"check_same_thread": False}
    return create_engine(url, connect_args=connect_args)


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class LoanApplicationORM(Base):
    """SQLAlchemy ORM mapping for a LoanApplication record.

    Field names and types are intentionally kept backward-compatible with
    the in-memory dict format used by ``LoanRepository``.
    """

    __tablename__ = "loan_applications"

    loan_id: str = Column(String(36), primary_key=True, index=True)
    applicant_id: str = Column(String(255), nullable=False)
    amount: float = Column(Float, nullable=False)
    term_months: int = Column(Integer, nullable=False)
    status: str = Column(String(32), nullable=False, default="pending")
    purpose: Optional[str] = Column(String(512), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict mirroring the legacy data format."""
        result: Dict[str, Any] = {
            "loan_id": self.loan_id,
            "applicant_id": self.applicant_id,
            "amount": self.amount,
            "term_months": self.term_months,
            "status": self.status,
        }
        if self.purpose is not None:
            result["purpose"] = self.purpose
        return result


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def build_session_factory(engine) -> sessionmaker:
    """Create and return a ``sessionmaker`` bound to *engine*."""
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_db_session(session_factory: sessionmaker) -> Generator[Session, None, None]:
    """Context manager that yields a database session.

    On success the transaction is committed; on any ``SQLAlchemyError`` the
    transaction is rolled back and the exception is re-raised.  The session
    is always closed on exit.
    """
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Data access layer
# ---------------------------------------------------------------------------


class LoanApplicationDAL:
    """CRUD operations for LoanApplication records via SQLAlchemy sessions.

    Each public method accepts an active ``Session`` as its first argument
    so that callers can compose multiple operations in a single transaction
    if needed, or use the ``get_db_session()`` context manager for automatic
    lifecycle management.
    """

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        session: Session,
        loan_id: str,
        applicant_id: str,
        amount: float,
        term_months: int,
        purpose: Optional[str] = None,
    ) -> LoanApplicationORM:
        """Persist a new LoanApplication and return the ORM instance.

        Raises
        ------
        ValueError
            If *amount* or *term_months* fail validation.
        """
        if not isinstance(amount, (int, float)) or amount <= 0:
            raise ValueError("amount must be a positive number")
        if not isinstance(term_months, int) or term_months <= 0:
            raise ValueError("term_months must be a positive integer")

        loan = LoanApplicationORM(
            loan_id=loan_id,
            applicant_id=applicant_id,
            amount=float(amount),
            term_months=term_months,
            status="pending",
            purpose=purpose,
        )
        session.add(loan)
        session.flush()  # Assign PK without committing so caller controls tx
        return loan

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def find_by_id(
        self, session: Session, loan_id: str
    ) -> Optional[LoanApplicationORM]:
        """Return the ORM instance for *loan_id*, or ``None``."""
        return session.get(LoanApplicationORM, loan_id)

    def find_all(self, session: Session) -> List[LoanApplicationORM]:
        """Return all loan application records."""
        return session.query(LoanApplicationORM).all()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_status(
        self, session: Session, loan_id: str, new_status: str
    ) -> Optional[LoanApplicationORM]:
        """Update the status of a loan application.

        Returns the updated ORM instance, or ``None`` if not found.

        Raises
        ------
        ValueError
            If *new_status* is not a recognised value.
        """
        if new_status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{new_status}'. "
                f"Must be one of: {sorted(VALID_STATUSES)}"
            )
        loan = self.find_by_id(session, loan_id)
        if loan is None:
            return None
        loan.status = new_status
        session.flush()
        return loan

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, session: Session, loan_id: str) -> bool:
        """Delete a loan application record.

        Returns ``True`` if the record existed and was deleted, ``False``
        otherwise.
        """
        loan = self.find_by_id(session, loan_id)
        if loan is None:
            return False
        session.delete(loan)
        session.flush()
        return True
