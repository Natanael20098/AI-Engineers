"""
Tests for PaymentProcessor (processor.py) – Loan Repayment Processing microservice.

Covers all acceptance criteria:
  AC1  PaymentProcessor API endpoints are operational and accessible.
  AC2  Proper validation and error handling are in place for all endpoints.
  AC3  Successfully process a simulated payment through the new microservice.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from payment_microservice.processor import (
    create_payment_app,
    _payment_store,
    _idempotency_index,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_stores():
    """Reset in-memory stores before and after every test."""
    _payment_store.clear()
    _idempotency_index.clear()
    yield
    _payment_store.clear()
    _idempotency_index.clear()


@pytest.fixture()
def client() -> TestClient:
    app = create_payment_app()
    return TestClient(app)


def _initiate_payment(
    client: TestClient,
    loan_id: str = "loan-001",
    payer_id: str = "payer-001",
    amount: float = 500.0,
    currency: str = "USD",
    idempotency_key: str | None = None,
):
    """Helper: POST /payments/initiate and return the response."""
    body = {
        "loan_id": loan_id,
        "payer_id": payer_id,
        "amount": amount,
        "currency": currency,
    }
    if idempotency_key is not None:
        body["idempotency_key"] = idempotency_key
    return client.post("/payments/initiate", json=body)


# ---------------------------------------------------------------------------
# AC1 – Endpoints are operational and accessible
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_healthy(client: TestClient):
    """GET /health must return 200 with healthy status."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "payment_processor"


def test_initiate_endpoint_is_accessible(client: TestClient):
    """POST /payments/initiate must be reachable (not 404/405)."""
    resp = client.post("/payments/initiate", json={})
    assert resp.status_code not in (404, 405)


def test_get_payment_endpoint_is_accessible(client: TestClient):
    """GET /payments/{id} returns 404 for unknown IDs (not 405)."""
    resp = client.get("/payments/no-such-id")
    assert resp.status_code == 404


def test_confirm_endpoint_is_accessible(client: TestClient):
    """POST /payments/{id}/confirm returns 404 for unknown IDs (not 405)."""
    resp = client.post("/payments/no-such-id/confirm", json={})
    assert resp.status_code == 404


def test_cancel_endpoint_is_accessible(client: TestClient):
    """POST /payments/{id}/cancel returns 404 for unknown IDs (not 405)."""
    resp = client.post("/payments/no-such-id/cancel")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC2 – Validation and error handling
# ---------------------------------------------------------------------------


def test_initiate_missing_loan_id_returns_422(client: TestClient):
    resp = client.post(
        "/payments/initiate",
        json={"payer_id": "p-001", "amount": 100},
    )
    assert resp.status_code == 422


def test_initiate_missing_payer_id_returns_422(client: TestClient):
    resp = client.post(
        "/payments/initiate",
        json={"loan_id": "l-001", "amount": 100},
    )
    assert resp.status_code == 422


def test_initiate_missing_amount_returns_422(client: TestClient):
    resp = client.post(
        "/payments/initiate",
        json={"loan_id": "l-001", "payer_id": "p-001"},
    )
    assert resp.status_code == 422


def test_initiate_negative_amount_returns_422(client: TestClient):
    resp = _initiate_payment(client, amount=-100.0)
    assert resp.status_code == 422


def test_initiate_zero_amount_returns_422(client: TestClient):
    resp = _initiate_payment(client, amount=0.0)
    assert resp.status_code == 422


def test_confirm_already_confirmed_payment_returns_409(client: TestClient):
    payment_id = _initiate_payment(client).json()["payment_id"]
    client.post(f"/payments/{payment_id}/confirm", json={})
    resp = client.post(f"/payments/{payment_id}/confirm", json={})
    assert resp.status_code == 409


def test_cancel_already_cancelled_payment_returns_409(client: TestClient):
    payment_id = _initiate_payment(client).json()["payment_id"]
    client.post(f"/payments/{payment_id}/cancel")
    resp = client.post(f"/payments/{payment_id}/cancel")
    assert resp.status_code == 409


def test_confirm_cancelled_payment_returns_409(client: TestClient):
    payment_id = _initiate_payment(client).json()["payment_id"]
    client.post(f"/payments/{payment_id}/cancel")
    resp = client.post(f"/payments/{payment_id}/confirm", json={})
    assert resp.status_code == 409


def test_cancel_confirmed_payment_returns_409(client: TestClient):
    payment_id = _initiate_payment(client).json()["payment_id"]
    client.post(f"/payments/{payment_id}/confirm", json={})
    resp = client.post(f"/payments/{payment_id}/cancel")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# AC3 – Successfully process a simulated payment
# ---------------------------------------------------------------------------


def test_simulated_full_payment_flow(client: TestClient):
    """
    AC3: End-to-end simulated payment:
      1. Initiate payment (pending)
      2. Retrieve payment (verify pending)
      3. Confirm payment with transaction reference
      4. Retrieve payment (verify confirmed)
    """
    # Step 1 – Initiate
    init_resp = _initiate_payment(
        client, loan_id="loan-sim-001", payer_id="payer-sim-001", amount=1200.0
    )
    assert init_resp.status_code == 201
    body = init_resp.json()
    assert "payment_id" in body
    assert body["status"] == "pending"
    assert body["amount"] == 1200.0
    assert body["loan_id"] == "loan-sim-001"
    payment_id = body["payment_id"]

    # Step 2 – Retrieve and verify pending
    get_resp = client.get(f"/payments/{payment_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "pending"

    # Step 3 – Confirm with transaction reference
    confirm_resp = client.post(
        f"/payments/{payment_id}/confirm",
        json={"transaction_reference": "TXN-ABC-123"},
    )
    assert confirm_resp.status_code == 200
    confirmed = confirm_resp.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["transaction_reference"] == "TXN-ABC-123"

    # Step 4 – Retrieve and verify confirmed state persists
    get_after = client.get(f"/payments/{payment_id}")
    assert get_after.status_code == 200
    assert get_after.json()["status"] == "confirmed"


def test_initiate_payment_returns_201_with_all_fields(client: TestClient):
    resp = _initiate_payment(
        client,
        loan_id="loan-999",
        payer_id="payer-999",
        amount=750.0,
        currency="EUR",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["loan_id"] == "loan-999"
    assert body["payer_id"] == "payer-999"
    assert body["amount"] == 750.0
    assert body["currency"] == "EUR"
    assert body["status"] == "pending"
    assert "payment_id" in body


def test_cancel_payment_returns_200(client: TestClient):
    payment_id = _initiate_payment(client).json()["payment_id"]
    resp = client.post(f"/payments/{payment_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_initiation_returns_same_payment(client: TestClient):
    """Duplicate requests with the same idempotency_key return the same payment."""
    key = "idem-key-001"
    resp1 = _initiate_payment(client, amount=500.0, idempotency_key=key)
    resp2 = _initiate_payment(client, amount=500.0, idempotency_key=key)
    assert resp1.json()["payment_id"] == resp2.json()["payment_id"]


def test_different_idempotency_keys_create_different_payments(
    client: TestClient,
):
    resp1 = _initiate_payment(client, idempotency_key="key-A")
    resp2 = _initiate_payment(client, idempotency_key="key-B")
    assert resp1.json()["payment_id"] != resp2.json()["payment_id"]


def test_payment_ids_are_unique(client: TestClient):
    ids = {_initiate_payment(client).json()["payment_id"] for _ in range(3)}
    assert len(ids) == 3
