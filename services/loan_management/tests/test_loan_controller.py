"""
Tests for LoanController (main.py) – FastAPI-based loan management API.

Covers:
  - LoanController and LoanRepository CRUD operations (Task 1 AC1)
  - Functional CRUD endpoints with data integrity checks (Task 1 AC2 / AC3)
  - Validation and error handling
  - Full loan lifecycle workflow
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from loan_management.main import create_fastapi_app
from loan_management.repository import _loan_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_store():
    """Reset in-memory loan store before and after every test."""
    _loan_store.clear()
    yield
    _loan_store.clear()


@pytest.fixture()
def client() -> TestClient:
    app = create_fastapi_app()
    return TestClient(app)


def _create_loan(
    client: TestClient,
    applicant_id: str = "applicant-001",
    amount: float = 10000.0,
    term_months: int = 12,
) -> dict:
    """Helper: POST /loans and return the parsed JSON response."""
    resp = client.post(
        "/loans",
        json={
            "applicant_id": applicant_id,
            "amount": amount,
            "term_months": term_months,
        },
    )
    return resp


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_healthy(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "loan_management"


# ---------------------------------------------------------------------------
# CREATE – POST /loans
# ---------------------------------------------------------------------------


def test_create_loan_returns_201_with_loan_data(client: TestClient):
    """AC1 + AC2: POST /loans creates a loan application and returns it."""
    resp = _create_loan(client)
    assert resp.status_code == 201
    body = resp.json()
    assert "loan_id" in body
    assert body["applicant_id"] == "applicant-001"
    assert body["amount"] == 10000.0
    assert body["term_months"] == 12
    assert body["status"] == "pending"


def test_create_loan_assigns_unique_ids(client: TestClient):
    """Each loan gets a distinct UUID (data integrity)."""
    ids = {_create_loan(client).json()["loan_id"] for _ in range(3)}
    assert len(ids) == 3


def test_create_loan_missing_applicant_id_returns_422(client: TestClient):
    resp = client.post("/loans", json={"amount": 5000, "term_months": 6})
    assert resp.status_code == 422


def test_create_loan_missing_amount_returns_422(client: TestClient):
    resp = client.post(
        "/loans", json={"applicant_id": "app-001", "term_months": 6}
    )
    assert resp.status_code == 422


def test_create_loan_missing_term_months_returns_422(client: TestClient):
    resp = client.post(
        "/loans", json={"applicant_id": "app-001", "amount": 5000}
    )
    assert resp.status_code == 422


def test_create_loan_negative_amount_returns_422(client: TestClient):
    resp = client.post(
        "/loans",
        json={"applicant_id": "app-001", "amount": -1000, "term_months": 12},
    )
    assert resp.status_code == 422


def test_create_loan_zero_amount_returns_422(client: TestClient):
    resp = client.post(
        "/loans",
        json={"applicant_id": "app-001", "amount": 0, "term_months": 12},
    )
    assert resp.status_code == 422


def test_create_loan_zero_term_returns_422(client: TestClient):
    resp = client.post(
        "/loans",
        json={"applicant_id": "app-001", "amount": 5000, "term_months": 0},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# READ – GET /loans/{loan_id}
# ---------------------------------------------------------------------------


def test_get_loan_returns_200(client: TestClient):
    """AC2: retrieve a loan by ID returns correct data."""
    loan_id = _create_loan(client).json()["loan_id"]
    resp = client.get(f"/loans/{loan_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["loan_id"] == loan_id
    assert body["status"] == "pending"


def test_get_loan_not_found_returns_404(client: TestClient):
    resp = client.get("/loans/non-existent-id")
    assert resp.status_code == 404
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# READ – GET /loans (list)
# ---------------------------------------------------------------------------


def test_list_loans_returns_empty_list(client: TestClient):
    resp = client.get("/loans")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_loans_returns_all_created_loans(client: TestClient):
    for i in range(3):
        _create_loan(client, applicant_id=f"app-{i}", amount=(i + 1) * 1000)
    resp = client.get("/loans")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ---------------------------------------------------------------------------
# UPDATE – PUT /loans/{loan_id}/status
# ---------------------------------------------------------------------------


def test_update_status_returns_200_with_updated_loan(client: TestClient):
    """AC2 + AC3: status update reflects in the returned loan."""
    loan_id = _create_loan(client).json()["loan_id"]
    resp = client.put(f"/loans/{loan_id}/status", json={"status": "approved"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["loan_id"] == loan_id


def test_update_status_to_disbursed(client: TestClient):
    loan_id = _create_loan(client).json()["loan_id"]
    resp = client.put(f"/loans/{loan_id}/status", json={"status": "disbursed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "disbursed"


def test_update_status_invalid_value_returns_422(client: TestClient):
    loan_id = _create_loan(client).json()["loan_id"]
    resp = client.put(
        f"/loans/{loan_id}/status", json={"status": "unknown_status"}
    )
    assert resp.status_code == 422


def test_update_status_missing_field_returns_422(client: TestClient):
    loan_id = _create_loan(client).json()["loan_id"]
    resp = client.put(f"/loans/{loan_id}/status", json={})
    assert resp.status_code == 422


def test_update_status_not_found_returns_404(client: TestClient):
    resp = client.put(
        "/loans/no-such-id/status", json={"status": "approved"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# APPROVE – POST /loans/{loan_id}/approve
# ---------------------------------------------------------------------------


def test_approve_pending_loan_sets_status_approved(client: TestClient):
    """AC2: approving a pending loan sets status to 'approved'."""
    loan_id = _create_loan(client).json()["loan_id"]
    resp = client.post(f"/loans/{loan_id}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_approve_non_pending_loan_returns_409(client: TestClient):
    loan_id = _create_loan(client).json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")  # first approval
    resp = client.post(f"/loans/{loan_id}/approve")  # second attempt
    assert resp.status_code == 409


def test_approve_not_found_returns_404(client: TestClient):
    resp = client.post("/loans/no-such-id/approve")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# REJECT – POST /loans/{loan_id}/reject
# ---------------------------------------------------------------------------


def test_reject_pending_loan_sets_status_rejected(client: TestClient):
    """AC2: rejecting a pending loan sets status to 'rejected'."""
    loan_id = _create_loan(client).json()["loan_id"]
    resp = client.post(f"/loans/{loan_id}/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_reject_non_pending_loan_returns_409(client: TestClient):
    loan_id = _create_loan(client).json()["loan_id"]
    client.post(f"/loans/{loan_id}/reject")  # first rejection
    resp = client.post(f"/loans/{loan_id}/reject")  # second attempt
    assert resp.status_code == 409


def test_reject_not_found_returns_404(client: TestClient):
    resp = client.post("/loans/no-such-id/reject")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE – DELETE /loans/{loan_id}
# ---------------------------------------------------------------------------


def test_delete_loan_returns_204(client: TestClient):
    loan_id = _create_loan(client).json()["loan_id"]
    resp = client.delete(f"/loans/{loan_id}")
    assert resp.status_code == 204


def test_delete_removes_loan_from_store(client: TestClient):
    """AC3: data integrity – loan is no longer retrievable after deletion."""
    loan_id = _create_loan(client).json()["loan_id"]
    client.delete(f"/loans/{loan_id}")
    resp = client.get(f"/loans/{loan_id}")
    assert resp.status_code == 404


def test_delete_not_found_returns_404(client: TestClient):
    resp = client.delete("/loans/no-such-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Full lifecycle workflow (AC3 – data integrity)
# ---------------------------------------------------------------------------


def test_full_loan_lifecycle(client: TestClient):
    """
    AC3: Complete lifecycle:
    create (pending) → approve → verify approved → attempt second approve (409).
    """
    loan_id = _create_loan(
        client, applicant_id="lifecycle-client", amount=50000
    ).json()["loan_id"]

    # Verify initial state
    assert client.get(f"/loans/{loan_id}").json()["status"] == "pending"

    # Approve
    approve_resp = client.post(f"/loans/{loan_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    # Re-read confirms approved state persists
    assert client.get(f"/loans/{loan_id}").json()["status"] == "approved"

    # Second approval must conflict
    assert client.post(f"/loans/{loan_id}/approve").status_code == 409


def test_multiple_loans_are_independent(client: TestClient):
    """AC3: Each loan's state is independent of others."""
    loan_a = _create_loan(client, applicant_id="a").json()["loan_id"]
    loan_b = _create_loan(client, applicant_id="b").json()["loan_id"]

    client.post(f"/loans/{loan_a}/approve")

    assert client.get(f"/loans/{loan_a}").json()["status"] == "approved"
    assert client.get(f"/loans/{loan_b}").json()["status"] == "pending"
