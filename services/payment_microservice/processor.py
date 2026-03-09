"""
processor.py – PaymentProcessor: FastAPI microservice for Loan Repayment Processing.

Decoupled from the monolithic system, this service handles payment initiation
and confirmation for loan repayments.  It integrates conceptually with the
LoanApplication microservice for pay-off calculations.

Endpoints
---------
GET  /health                               liveness probe
POST /payments/initiate                    initiate a payment
GET  /payments/{payment_id}               retrieve payment status
POST /payments/{payment_id}/confirm        confirm a pending payment
POST /payments/{payment_id}/cancel         cancel a pending payment

Idempotency
-----------
Clients may supply an ``idempotency_key`` on initiation; duplicate requests
with the same key return the original payment record rather than creating a
duplicate.

Security validations
--------------------
- All monetary amounts must be strictly positive.
- ``loan_id`` and ``payer_id`` are required for every initiation request.
- Confirmation is only permitted for payments in the ``pending`` state.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_payment_store: Dict[str, Dict[str, Any]] = {}
# idempotency_key → payment_id mapping
_idempotency_index: Dict[str, str] = {}

VALID_PAYMENT_STATUSES: frozenset[str] = frozenset(
    {"pending", "confirmed", "failed", "cancelled"}
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PaymentInitiateRequest(BaseModel):
    loan_id: str
    payer_id: str
    amount: float
    currency: str = "USD"
    idempotency_key: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be a positive number")
        return v

    @field_validator("currency")
    @classmethod
    def currency_must_be_non_empty(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("currency must be a non-empty string")
        return v


class PaymentConfirmRequest(BaseModel):
    transaction_reference: Optional[str] = None


# ---------------------------------------------------------------------------
# PaymentProcessor
# ---------------------------------------------------------------------------


class PaymentProcessor:
    """
    Core business logic for payment initiation and confirmation.

    All mutation methods operate on the module-level ``_payment_store``.
    """

    # ------------------------------------------------------------------
    # Initiate
    # ------------------------------------------------------------------

    def initiate(
        self,
        loan_id: str,
        payer_id: str,
        amount: float,
        currency: str = "USD",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new payment record and return it.

        If *idempotency_key* is provided and a payment with that key already
        exists, the existing record is returned unchanged (idempotent).

        Raises
        ------
        ValueError
            If *amount* is not strictly positive.
        """
        if amount <= 0:
            raise ValueError("amount must be a positive number")

        # Idempotency check
        if idempotency_key and idempotency_key in _idempotency_index:
            existing_id = _idempotency_index[idempotency_key]
            if existing_id in _payment_store:
                return _payment_store[existing_id]

        payment_id = str(uuid.uuid4())
        payment: Dict[str, Any] = {
            "payment_id": payment_id,
            "loan_id": loan_id,
            "payer_id": payer_id,
            "amount": float(amount),
            "currency": currency.strip().upper(),
            "status": "pending",
        }
        if idempotency_key:
            payment["idempotency_key"] = idempotency_key
            _idempotency_index[idempotency_key] = payment_id

        _payment_store[payment_id] = payment
        return payment

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def find_by_id(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Return the payment record or ``None`` if not found."""
        return _payment_store.get(payment_id)

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------

    def confirm(
        self,
        payment_id: str,
        transaction_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Confirm a pending payment.

        Raises
        ------
        KeyError
            If *payment_id* is not found.
        ValueError
            If the payment is not in ``pending`` status.
        """
        payment = _payment_store.get(payment_id)
        if payment is None:
            raise KeyError(f"Payment '{payment_id}' not found")
        if payment["status"] != "pending":
            raise ValueError(
                f"Cannot confirm payment in '{payment['status']}' status. "
                "Only pending payments can be confirmed."
            )
        payment["status"] = "confirmed"
        if transaction_reference:
            payment["transaction_reference"] = transaction_reference
        return payment

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel(self, payment_id: str) -> Dict[str, Any]:
        """Cancel a pending payment.

        Raises
        ------
        KeyError
            If *payment_id* is not found.
        ValueError
            If the payment is not in ``pending`` status.
        """
        payment = _payment_store.get(payment_id)
        if payment is None:
            raise KeyError(f"Payment '{payment_id}' not found")
        if payment["status"] != "pending":
            raise ValueError(
                f"Cannot cancel payment in '{payment['status']}' status."
            )
        payment["status"] = "cancelled"
        return payment


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_payment_app() -> FastAPI:
    """Application factory for the FastAPI payment processing service."""
    app = FastAPI(
        title="Payment Processing Service",
        description="Microservice for loan repayment processing",
        version="1.0.0",
    )

    processor = PaymentProcessor()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "healthy", "service": "payment_processor"}

    # ------------------------------------------------------------------
    # Initiate payment
    # ------------------------------------------------------------------

    @app.post("/payments/initiate", status_code=status.HTTP_201_CREATED)
    def initiate_payment(payload: PaymentInitiateRequest) -> Dict[str, Any]:
        try:
            payment = processor.initiate(
                loan_id=payload.loan_id,
                payer_id=payload.payer_id,
                amount=payload.amount,
                currency=payload.currency,
                idempotency_key=payload.idempotency_key,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        return payment

    # ------------------------------------------------------------------
    # Get payment status
    # ------------------------------------------------------------------

    @app.get("/payments/{payment_id}")
    def get_payment(payment_id: str) -> Dict[str, Any]:
        payment = processor.find_by_id(payment_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment '{payment_id}' not found",
            )
        return payment

    # ------------------------------------------------------------------
    # Confirm payment
    # ------------------------------------------------------------------

    @app.post("/payments/{payment_id}/confirm")
    def confirm_payment(
        payment_id: str, payload: PaymentConfirmRequest
    ) -> Dict[str, Any]:
        try:
            payment = processor.confirm(
                payment_id,
                transaction_reference=payload.transaction_reference,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            )
        return payment

    # ------------------------------------------------------------------
    # Cancel payment
    # ------------------------------------------------------------------

    @app.post("/payments/{payment_id}/cancel")
    def cancel_payment(payment_id: str) -> Dict[str, Any]:
        try:
            payment = processor.cancel(payment_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            )
        return payment

    return app


# ---------------------------------------------------------------------------
# ASGI entry point
# ---------------------------------------------------------------------------

payment_app = create_payment_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(payment_app, host="0.0.0.0", port=8001)
