"""
main.py – LoanController: FastAPI application for the Loan Management microservice.

Migrated from the legacy Java LoanController.  Exposes a RESTful API for
full CRUD management of LoanApplication entities.

Endpoints
---------
GET  /health                         liveness probe
POST /loans                          create a loan application
GET  /loans/{loan_id}                retrieve a loan application
GET  /loans                          list all loan applications
PUT  /loans/{loan_id}/status         update loan application status
DELETE /loans/{loan_id}              delete a loan application
POST /loans/{loan_id}/approve        approve a pending loan
POST /loans/{loan_id}/reject         reject a pending loan
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, field_validator

from .repository import LoanRepository, VALID_STATUSES, _loan_store

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class LoanCreateRequest(BaseModel):
    applicant_id: str
    amount: float
    term_months: int
    purpose: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be a positive number")
        return v

    @field_validator("term_months")
    @classmethod
    def term_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("term_months must be a positive integer")
        return v


class LoanStatusUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}"
            )
        return v


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_fastapi_app() -> FastAPI:
    """Application factory for the FastAPI loan management service."""
    app = FastAPI(
        title="Loan Management Service",
        description="Microservice for managing loan applications",
        version="1.0.0",
    )

    repo = LoanRepository()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "healthy", "service": "loan_management"}

    # ------------------------------------------------------------------
    # Create loan
    # ------------------------------------------------------------------

    @app.post("/loans", status_code=status.HTTP_201_CREATED)
    def create_loan(payload: LoanCreateRequest) -> Dict[str, Any]:
        try:
            loan = repo.create(
                applicant_id=payload.applicant_id,
                amount=payload.amount,
                term_months=payload.term_months,
                purpose=payload.purpose,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        return loan

    # ------------------------------------------------------------------
    # List all loans
    # ------------------------------------------------------------------

    @app.get("/loans")
    def list_loans() -> list[Dict[str, Any]]:
        return repo.find_all()

    # ------------------------------------------------------------------
    # Get loan by ID
    # ------------------------------------------------------------------

    @app.get("/loans/{loan_id}")
    def get_loan(loan_id: str) -> Dict[str, Any]:
        loan = repo.find_by_id(loan_id)
        if loan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Loan '{loan_id}' not found",
            )
        return loan

    # ------------------------------------------------------------------
    # Update loan status
    # ------------------------------------------------------------------

    @app.put("/loans/{loan_id}/status")
    def update_loan_status(
        loan_id: str, payload: LoanStatusUpdateRequest
    ) -> Dict[str, Any]:
        loan = repo.find_by_id(loan_id)
        if loan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Loan '{loan_id}' not found",
            )
        try:
            updated = repo.update_status(loan_id, payload.status)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        return updated  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Approve loan
    # ------------------------------------------------------------------

    @app.post("/loans/{loan_id}/approve")
    def approve_loan(loan_id: str) -> Dict[str, Any]:
        loan = repo.find_by_id(loan_id)
        if loan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Loan '{loan_id}' not found",
            )
        if loan["status"] != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only pending loans can be approved",
            )
        return repo.update_status(loan_id, "approved")  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Reject loan
    # ------------------------------------------------------------------

    @app.post("/loans/{loan_id}/reject")
    def reject_loan(loan_id: str) -> Dict[str, Any]:
        loan = repo.find_by_id(loan_id)
        if loan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Loan '{loan_id}' not found",
            )
        if loan["status"] != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only pending loans can be rejected",
            )
        return repo.update_status(loan_id, "rejected")  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Delete loan
    # ------------------------------------------------------------------

    @app.delete("/loans/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_loan(loan_id: str) -> None:
        deleted = repo.delete(loan_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Loan '{loan_id}' not found",
            )

    return app


# ---------------------------------------------------------------------------
# WSGI/ASGI entry point
# ---------------------------------------------------------------------------

loan_fastapi_app = create_fastapi_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(loan_fastapi_app, host="0.0.0.0", port=8000)
