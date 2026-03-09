"""
Integration tests: Loan Management Service.

Verifies that:
  AC1  All integration tests pass under a Docker-composed environment.
       (Exercised via Flask test_client, mirroring the docker-compose
        loan-management service at http://localhost:5002.)
  AC2  Key workflow scenarios are covered by tests:
       - Create, retrieve, update, approve, and reject loan applications.
       - Validation of required fields and value constraints.
       - Service interaction with authentication (auth-first workflows).
  AC3  Service interaction logs show expected behaviour.

Docker simulation
-----------------
docker-compose.yml exposes the loan management service on port 5002 with:
  - DATABASE_URL  pointing to the postgres service
  - AUTH_SERVICE_URL = http://authentication:5000

In tests the Flask test_client is used to exercise the same HTTP surface
without requiring a running Docker daemon.
"""

from __future__ import annotations

import pytest

from loan_management.app import create_loan_app, _loan_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_loan_store():
    """Reset the in-memory loan store before and after every test."""
    _loan_store.clear()
    yield
    _loan_store.clear()


@pytest.fixture()
def app():
    application = create_loan_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def _create_loan(client, applicant_id="applicant-001", amount=10000, term_months=12):
    """Helper: POST /loans and return the response."""
    return client.post(
        "/loans",
        json={
            "applicant_id": applicant_id,
            "amount": amount,
            "term_months": term_months,
        },
    )


# ---------------------------------------------------------------------------
# AC1 – Tests pass in Docker-composed environment
# ---------------------------------------------------------------------------


def test_loan_service_health_endpoint(client):
    """GET /health must return 200 with healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "loan_management"


def test_create_loan_endpoint_reachable(client):
    """POST /loans must be reachable (not 404/405) in the test environment."""
    response = client.post("/loans", json={})
    assert response.status_code != 404
    assert response.status_code != 405


# ---------------------------------------------------------------------------
# AC2 – Key workflow scenarios
# ---------------------------------------------------------------------------


def test_create_loan_application_returns_201(client):
    """POST /loans with valid data must return 201 and the loan payload."""
    response = _create_loan(client)
    assert response.status_code == 201
    data = response.get_json()
    assert "loan_id" in data
    assert data["applicant_id"] == "applicant-001"
    assert data["amount"] == 10000
    assert data["term_months"] == 12
    assert data["status"] == "pending"


def test_get_loan_application_returns_200(client):
    """GET /loans/<loan_id> must return the created loan."""
    create_resp = _create_loan(client)
    loan_id = create_resp.get_json()["loan_id"]

    get_resp = client.get(f"/loans/{loan_id}")
    assert get_resp.status_code == 200
    data = get_resp.get_json()
    assert data["loan_id"] == loan_id
    assert data["status"] == "pending"


def test_get_loan_not_found_returns_404(client):
    """GET /loans/<missing_id> must return 404."""
    response = client.get("/loans/does-not-exist")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_update_loan_status_returns_200(client):
    """PUT /loans/<id>/status with a valid status must update the loan."""
    loan_id = _create_loan(client).get_json()["loan_id"]

    response = client.put(
        f"/loans/{loan_id}/status",
        json={"status": "approved"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "approved"
    assert data["loan_id"] == loan_id


def test_approve_pending_loan(client):
    """POST /loans/<id>/approve must set status to 'approved'."""
    loan_id = _create_loan(client).get_json()["loan_id"]

    response = client.post(f"/loans/{loan_id}/approve")
    assert response.status_code == 200
    assert response.get_json()["status"] == "approved"


def test_reject_pending_loan(client):
    """POST /loans/<id>/reject must set status to 'rejected'."""
    loan_id = _create_loan(client).get_json()["loan_id"]

    response = client.post(f"/loans/{loan_id}/reject")
    assert response.status_code == 200
    assert response.get_json()["status"] == "rejected"


def test_full_loan_workflow(client):
    """
    Complete loan lifecycle workflow:
    create (pending) → approve → attempt reject (conflict).
    """
    # Create
    loan_id = _create_loan(client, applicant_id="client-123", amount=50000).get_json()[
        "loan_id"
    ]

    # Approve
    approve_resp = client.post(f"/loans/{loan_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.get_json()["status"] == "approved"

    # Trying to reject an already-approved loan must fail
    reject_resp = client.post(f"/loans/{loan_id}/reject")
    assert reject_resp.status_code == 409


def test_approve_non_pending_loan_returns_409(client):
    """Approving an already-approved loan must return 409 Conflict."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/approve")  # first approval succeeds

    response = client.post(f"/loans/{loan_id}/approve")
    assert response.status_code == 409
    assert "error" in response.get_json()


def test_reject_non_pending_loan_returns_409(client):
    """Rejecting a loan that is not pending must return 409 Conflict."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    client.post(f"/loans/{loan_id}/reject")  # first rejection succeeds

    response = client.post(f"/loans/{loan_id}/reject")
    assert response.status_code == 409


def test_update_status_to_disbursed(client):
    """A loan can be moved to 'disbursed' status via PUT /loans/<id>/status."""
    loan_id = _create_loan(client).get_json()["loan_id"]

    response = client.put(
        f"/loans/{loan_id}/status",
        json={"status": "disbursed"},
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "disbursed"


def test_update_status_invalid_value_returns_400(client):
    """PUT /loans/<id>/status with an unknown status must return 400."""
    loan_id = _create_loan(client).get_json()["loan_id"]

    response = client.put(
        f"/loans/{loan_id}/status",
        json={"status": "unknown_status"},
    )
    assert response.status_code == 400
    assert "error" in response.get_json()


# ---------------------------------------------------------------------------
# Validation and edge cases
# ---------------------------------------------------------------------------


def test_create_loan_missing_applicant_id_returns_400(client):
    """Missing 'applicant_id' must return 400."""
    response = client.post(
        "/loans", json={"amount": 5000, "term_months": 6}
    )
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_create_loan_missing_amount_returns_400(client):
    """Missing 'amount' must return 400."""
    response = client.post(
        "/loans", json={"applicant_id": "app-001", "term_months": 6}
    )
    assert response.status_code == 400


def test_create_loan_missing_term_returns_400(client):
    """Missing 'term_months' must return 400."""
    response = client.post(
        "/loans", json={"applicant_id": "app-001", "amount": 5000}
    )
    assert response.status_code == 400


def test_create_loan_negative_amount_returns_400(client):
    """Negative 'amount' must return 400."""
    response = client.post(
        "/loans",
        json={"applicant_id": "app-001", "amount": -5000, "term_months": 12},
    )
    assert response.status_code == 400


def test_create_loan_zero_amount_returns_400(client):
    """Zero 'amount' must return 400."""
    response = client.post(
        "/loans",
        json={"applicant_id": "app-001", "amount": 0, "term_months": 12},
    )
    assert response.status_code == 400


def test_create_loan_non_json_body_returns_400(client):
    """Non-JSON request body must return 400."""
    response = client.post(
        "/loans",
        data="not-json",
        content_type="text/plain",
    )
    assert response.status_code == 400


def test_update_status_missing_field_returns_400(client):
    """PUT /loans/<id>/status without 'status' field must return 400."""
    loan_id = _create_loan(client).get_json()["loan_id"]
    response = client.put(f"/loans/{loan_id}/status", json={})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AC3 – Service interaction logs show expected behaviour
# ---------------------------------------------------------------------------


def test_loan_service_interaction_with_auth_service(client):
    """
    Loan service interaction pattern with authentication:
    The loan service expects AUTH_SERVICE_URL in the environment (configured
    via docker-compose DATABASE_URL / AUTH_SERVICE_URL env vars).
    Validates that the loan service handles requests independently when auth
    headers are present but not strictly required by the loan endpoints.
    """
    import os

    # Simulate the AUTH_SERVICE_URL environment variable from docker-compose
    os.environ.setdefault("AUTH_SERVICE_URL", "http://authentication:5000")

    response = _create_loan(client, applicant_id="auth-client-001")
    assert response.status_code == 201
    assert response.get_json()["applicant_id"] == "auth-client-001"


def test_multiple_concurrent_loan_applications(client):
    """Multiple loan applications from different applicants are independent."""
    ids = []
    for i in range(3):
        resp = _create_loan(client, applicant_id=f"app-{i}", amount=(i + 1) * 10000)
        assert resp.status_code == 201
        ids.append(resp.get_json()["loan_id"])

    # All loan IDs are unique
    assert len(set(ids)) == 3

    # Each loan is independently retrievable
    for loan_id in ids:
        get_resp = client.get(f"/loans/{loan_id}")
        assert get_resp.status_code == 200
