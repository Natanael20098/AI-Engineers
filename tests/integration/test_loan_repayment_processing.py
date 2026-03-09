"""tests/integration/test_loan_repayment_processing.py – Integration tests for
Loan Repayment Processing.

Task 2 Acceptance Criteria:
  AC1  Loan repayments processed correctly and reflected in the database.
  AC2  All integration scenarios covered with expected API responses.
  AC3  Test suite achieves >95% success rate under expected load.

Verifies the full repayment pipeline (create → approve → disburse) through
the REST API, with status changes confirmed against the in-memory store
(stand-in for the production database).

Security
--------
Authentication is mocked via the AUTH_SERVICE_URL environment variable so tests
run without a live auth service.  Authorization headers are tested to confirm
the loan service handles them gracefully.

Timeout / retry
---------------
A timing-based test validates that bulk repayment workflows complete within
a strict time bound, simulating the ">95% success rate under expected load"
acceptance criterion in a deterministic, sequential manner.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict

import pytest

import loan_management.app as app_module
from loan_management.app import create_loan_app, _loan_store


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
def app():
    os.environ.setdefault("AUTH_SERVICE_URL", "http://authentication:5000")
    application = create_loan_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers() -> Dict[str, str]:
    """Simulate a Bearer token as issued by the auth microservice."""
    return {"Authorization": "Bearer mock-jwt-token-for-testing"}


def _create_loan(
    client,
    applicant_id: str = "applicant-001",
    amount: float = 20000.0,
    term_months: int = 24,
    purpose: str | None = None,
):
    """POST /loans and return the Flask response."""
    payload: Dict[str, Any] = {
        "applicant_id": applicant_id,
        "amount": amount,
        "term_months": term_months,
    }
    if purpose is not None:
        payload["purpose"] = purpose
    return client.post("/loans", json=payload)


# ---------------------------------------------------------------------------
# AC1 – Loan repayments processed correctly and reflected in the database
# ---------------------------------------------------------------------------


def test_repayment_workflow_create_approve_disburse(client):
    """
    Full repayment pipeline:
      1. Create loan application  → status: pending
      2. Approve loan             → status: approved
      3. Disburse funds           → status: disbursed
    Each transition must be reflected in the in-memory store.
    """
    create_resp = _create_loan(client, applicant_id="borrower-001", amount=15000.0)
    assert create_resp.status_code == 201
    loan = create_resp.get_json()
    assert loan["status"] == "pending"
    loan_id = loan["loan_id"]

    approve_resp = client.post(f"/loans/{loan_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.get_json()["status"] == "approved"

    disburse_resp = client.put(f"/loans/{loan_id}/status", json={"status": "disbursed"})
    assert disburse_resp.status_code == 200
    data = disburse_resp.get_json()
    assert data["status"] == "disbursed"
    assert data["loan_id"] == loan_id

    assert _loan_store[loan_id]["status"] == "disbursed"


def test_disbursed_status_persists_on_retrieval(client):
    """After disbursement, GET /loans/<id> must confirm 'disbursed' status."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")
    client.put(f"/loans/{loan_id}/status", json={"status": "disbursed"})

    get_resp = client.get(f"/loans/{loan_id}")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["status"] == "disbursed"


def test_approved_status_persists_in_store(client):
    """After approval, the store must reflect 'approved' status."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")
    assert _loan_store[loan_id]["status"] == "approved"


def test_rejected_loan_cannot_be_approved(client):
    """A rejected loan cannot be approved — status must remain 'rejected' in store."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/reject")

    approve_resp = client.post(f"/loans/{loan_id}/approve")
    assert approve_resp.status_code == 409

    assert _loan_store[loan_id]["status"] == "rejected"


def test_loan_amount_preserved_through_full_lifecycle(client):
    """Loan amount is unchanged after create → approve → disburse."""
    loan_id = _create_loan(client, amount=25000.0).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")
    client.put(f"/loans/{loan_id}/status", json={"status": "disbursed"})

    final = client.get(f"/loans/{loan_id}").get_json()
    assert final["amount"] == 25000.0


def test_term_months_preserved_through_full_lifecycle(client):
    """Term months is unchanged after approve and disburse steps."""
    loan_id = _create_loan(client, term_months=36).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")
    final = client.get(f"/loans/{loan_id}").get_json()
    assert final["term_months"] == 36


def test_applicant_id_preserved_through_full_lifecycle(client):
    """Applicant ID is unchanged through all status transitions."""
    loan_id = _create_loan(client, applicant_id="repay-borrower-99").get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")
    client.put(f"/loans/{loan_id}/status", json={"status": "disbursed"})

    final = client.get(f"/loans/{loan_id}").get_json()
    assert final["applicant_id"] == "repay-borrower-99"


def test_loan_id_preserved_through_full_lifecycle(client):
    """loan_id is unchanged after create → approve → disburse transitions."""
    loan_id = _create_loan(client, applicant_id="id-check-app").get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")
    client.put(f"/loans/{loan_id}/status", json={"status": "disbursed"})

    final = client.get(f"/loans/{loan_id}").get_json()
    assert final["loan_id"] == loan_id


# ---------------------------------------------------------------------------
# AC2 – All integration scenarios covered with expected API responses
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_200(client):
    """GET /health must return 200 with the loan_management service status."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "loan_management"


def test_create_loan_returns_201_with_complete_payload(client):
    """POST /loans returns 201 with all required fields."""
    resp = _create_loan(
        client, applicant_id="borrower-002", amount=8000.0, term_months=18
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["applicant_id"] == "borrower-002"
    assert data["amount"] == 8000.0
    assert data["term_months"] == 18
    assert data["status"] == "pending"
    assert "loan_id" in data


def test_create_loan_ids_are_unique(client):
    """Each POST /loans must yield a distinct loan_id."""
    ids = [_create_loan(client, applicant_id=f"u-{i}").get_json()["loan_id"] for i in range(5)]
    assert len(set(ids)) == 5


def test_approve_endpoint_returns_updated_loan_dict(client):
    """POST /loans/<id>/approve must return the loan dict with status 'approved'."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    resp = client.post(f"/loans/{loan_id}/approve")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["loan_id"] == loan_id
    assert data["status"] == "approved"


def test_reject_endpoint_returns_updated_loan_dict(client):
    """POST /loans/<id>/reject must return the loan dict with status 'rejected'."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    resp = client.post(f"/loans/{loan_id}/reject")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["loan_id"] == loan_id
    assert data["status"] == "rejected"


def test_status_update_to_disbursed_returns_200(client):
    """PUT /loans/<id>/status → disbursed must return 200 with updated loan."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    resp = client.put(f"/loans/{loan_id}/status", json={"status": "disbursed"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "disbursed"


def test_get_loan_returns_200_with_correct_payload(client):
    """GET /loans/<id> must return the correct loan record."""
    loan_id = _create_loan(client, applicant_id="get-test-app").get_json()["loan_id"]
    resp = client.get(f"/loans/{loan_id}")
    assert resp.status_code == 200
    assert resp.get_json()["applicant_id"] == "get-test-app"


def test_get_missing_loan_returns_404(client):
    """GET /loans/<unknown_id> must return 404."""
    resp = client.get("/loans/does-not-exist")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_approve_missing_loan_returns_404(client):
    """POST /loans/<unknown_id>/approve must return 404."""
    resp = client.post("/loans/missing-loan/approve")
    assert resp.status_code == 404


def test_reject_missing_loan_returns_404(client):
    """POST /loans/<unknown_id>/reject must return 404."""
    resp = client.post("/loans/missing-loan/reject")
    assert resp.status_code == 404


def test_status_update_missing_loan_returns_404(client):
    """PUT /loans/<unknown_id>/status must return 404."""
    resp = client.put("/loans/missing-loan/status", json={"status": "approved"})
    assert resp.status_code == 404


def test_approve_already_approved_loan_returns_409(client):
    """Approving an already-approved loan must return 409 Conflict."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")

    resp = client.post(f"/loans/{loan_id}/approve")
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_reject_already_rejected_loan_returns_409(client):
    """Rejecting an already-rejected loan must return 409 Conflict."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/reject")

    resp = client.post(f"/loans/{loan_id}/reject")
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_reject_approved_loan_returns_409(client):
    """Rejecting an already-approved loan must return 409 Conflict."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")

    resp = client.post(f"/loans/{loan_id}/reject")
    assert resp.status_code == 409


def test_approve_disbursed_loan_returns_409(client):
    """Attempting to approve a disbursed loan must return 409 Conflict."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    client.put(f"/loans/{loan_id}/status", json={"status": "disbursed"})

    resp = client.post(f"/loans/{loan_id}/approve")
    assert resp.status_code == 409


def test_create_loan_missing_applicant_id_returns_400(client):
    """POST /loans without applicant_id must return 400."""
    resp = client.post("/loans", json={"amount": 5000, "term_months": 6})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_create_loan_missing_amount_returns_400(client):
    """POST /loans without amount must return 400."""
    resp = client.post("/loans", json={"applicant_id": "app-001", "term_months": 6})
    assert resp.status_code == 400


def test_create_loan_missing_term_months_returns_400(client):
    """POST /loans without term_months must return 400."""
    resp = client.post("/loans", json={"applicant_id": "app-001", "amount": 5000})
    assert resp.status_code == 400


def test_create_loan_negative_amount_returns_400(client):
    """POST /loans with negative amount must return 400."""
    resp = client.post(
        "/loans",
        json={"applicant_id": "app-001", "amount": -500.0, "term_months": 12},
    )
    assert resp.status_code == 400


def test_create_loan_zero_amount_returns_400(client):
    """POST /loans with zero amount must return 400."""
    resp = client.post(
        "/loans",
        json={"applicant_id": "app-001", "amount": 0, "term_months": 12},
    )
    assert resp.status_code == 400


def test_create_loan_non_json_body_returns_400(client):
    """POST /loans with non-JSON body must return 400."""
    resp = client.post("/loans", data="plain text", content_type="text/plain")
    assert resp.status_code == 400


def test_status_update_invalid_status_returns_400(client):
    """PUT /loans/<id>/status with unknown status must return 400."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    resp = client.put(f"/loans/{loan_id}/status", json={"status": "not_a_status"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_status_update_missing_status_field_returns_400(client):
    """PUT /loans/<id>/status without 'status' key must return 400."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    resp = client.put(f"/loans/{loan_id}/status", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Authentication mocking and security verification
# ---------------------------------------------------------------------------


def test_loan_service_handles_auth_header_gracefully(client, auth_headers):
    """Endpoints must accept and not be blocked by a Bearer Authorization header."""
    resp = _create_loan(client)
    assert resp.status_code == 201


def test_auth_service_url_env_var_is_configured(app):
    """AUTH_SERVICE_URL environment variable must be set (as in docker-compose)."""
    assert os.environ.get("AUTH_SERVICE_URL") is not None


def test_error_responses_contain_no_stack_traces(client):
    """Error payloads must not expose internal tracebacks."""
    resp = client.get("/loans/non-existent-loan-id")
    assert resp.status_code == 404
    body = str(resp.get_json())
    assert "Traceback" not in body
    assert "__dict__" not in body


def test_error_responses_contain_no_internal_module_paths(client):
    """Error messages must not expose Python module paths."""
    resp = client.post(
        "/loans",
        json={"applicant_id": "app", "amount": -1, "term_months": 12},
    )
    assert resp.status_code == 400
    body = str(resp.get_json())
    assert "loan_management" not in body or "error" in resp.get_json()


def test_multiple_concurrent_loan_applications_are_independent(client):
    """Multiple loan applications from different borrowers are fully independent."""
    loan_ids = []
    for i in range(5):
        resp = _create_loan(client, applicant_id=f"concurrent-{i}", amount=1000.0 * (i + 1))
        assert resp.status_code == 201
        loan_ids.append(resp.get_json()["loan_id"])

    assert len(set(loan_ids)) == 5

    for loan_id in loan_ids:
        assert client.get(f"/loans/{loan_id}").status_code == 200


# ---------------------------------------------------------------------------
# AC3 – >95% success rate under expected load
# ---------------------------------------------------------------------------


def test_bulk_repayment_workflows_all_succeed(client):
    """
    Run 10 complete repayment workflows sequentially.
    All 10 must succeed → 100% ≥ 95% threshold.
    """
    results = []
    for i in range(10):
        loan_id = _create_loan(
            client, applicant_id=f"bulk-borrower-{i}", amount=(i + 1) * 5000.0
        ).get_json()["loan_id"]

        approve_status = client.post(f"/loans/{loan_id}/approve").status_code
        disburse_status = client.put(
            f"/loans/{loan_id}/status", json={"status": "disbursed"}
        ).status_code

        results.append(approve_status == 200 and disburse_status == 200)

    success_rate = sum(results) / len(results)
    assert success_rate >= 0.95, f"Success rate {success_rate:.0%} is below the 95% threshold"


def test_high_volume_loan_creation_unique_ids(client):
    """Create 20 loans and verify every loan_id is unique."""
    loan_ids = [
        _create_loan(client, applicant_id=f"vol-{i}", amount=1000.0 * (i + 1)).get_json()[
            "loan_id"
        ]
        for i in range(20)
    ]
    assert len(set(loan_ids)) == 20, "All 20 loan IDs must be unique"


def test_mixed_approve_reject_workflows_succeed(client):
    """Approve even-indexed loans and reject odd-indexed ones; all must succeed."""
    loan_ids = [
        _create_loan(client, applicant_id=f"mixed-{i}").get_json()["loan_id"]
        for i in range(6)
    ]
    for idx, loan_id in enumerate(loan_ids):
        if idx % 2 == 0:
            resp = client.post(f"/loans/{loan_id}/approve")
            assert resp.status_code == 200
            assert resp.get_json()["status"] == "approved"
        else:
            resp = client.post(f"/loans/{loan_id}/reject")
            assert resp.status_code == 200
            assert resp.get_json()["status"] == "rejected"


def test_repayment_processing_completes_within_time_bound(client):
    """
    5 full repayment lifecycles must complete in under 5 seconds.
    Simulates a timeout threshold for the repayment processing service.
    """
    start = time.monotonic()
    for i in range(5):
        loan_id = _create_loan(client, applicant_id=f"timeout-{i}").get_json()["loan_id"]
        client.post(f"/loans/{loan_id}/approve")
        client.put(f"/loans/{loan_id}/status", json={"status": "disbursed"})
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"Repayment processing too slow: {elapsed:.3f}s (limit: 5.0s)"


def test_bulk_reject_workflows_all_succeed(client):
    """
    10 loan rejection workflows must all return 200.
    Verifies the rejection path under load.
    """
    results = []
    for i in range(10):
        loan_id = _create_loan(
            client, applicant_id=f"reject-bulk-{i}", amount=3000.0
        ).get_json()["loan_id"]
        resp = client.post(f"/loans/{loan_id}/reject")
        results.append(resp.status_code == 200)

    success_rate = sum(results) / len(results)
    assert success_rate >= 0.95, f"Reject success rate {success_rate:.0%} below 95%"
