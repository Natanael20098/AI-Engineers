"""
Minimal Flask application for the Loan Management service.

Provides the core endpoints exercised in integration tests:

    GET  /health                       liveness probe
    POST /loans                        create a loan application
    GET  /loans/<loan_id>              retrieve a loan application
    PUT  /loans/<loan_id>/status       update loan application status
    POST /loans/<loan_id>/approve      approve a pending loan
    POST /loans/<loan_id>/reject       reject a pending loan

Data is held in-memory (no DB dependency) to keep the service self-contained
for testing.  In production this would be backed by PostgreSQL via the
DATABASE_URL environment variable.
"""

from __future__ import annotations

import uuid
from typing import Any

from flask import Flask, jsonify, request

# Valid loan status values
_VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "approved", "rejected", "disbursed"}
)

# In-memory store: {loan_id: loan_dict}
_loan_store: dict[str, dict[str, Any]] = {}


def create_loan_app() -> Flask:
    """Application factory for the loan management service."""
    app = Flask(__name__)

    @app.route("/health")
    def health():
        return jsonify({"status": "healthy", "service": "loan_management"}), 200

    @app.route("/loans", methods=["POST"])
    def create_loan():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        for field_name in ("applicant_id", "amount", "term_months"):
            if field_name not in data:
                return jsonify({"error": f"'{field_name}' is required"}), 400

        amount = data["amount"]
        if not isinstance(amount, (int, float)) or amount <= 0:
            return jsonify({"error": "amount must be a positive number"}), 400

        term = data["term_months"]
        if not isinstance(term, int) or term <= 0:
            return jsonify({"error": "term_months must be a positive integer"}), 400

        loan_id = str(uuid.uuid4())
        loan: dict[str, Any] = {
            "loan_id": loan_id,
            "applicant_id": data["applicant_id"],
            "amount": amount,
            "term_months": term,
            "status": "pending",
        }
        _loan_store[loan_id] = loan
        return jsonify(loan), 201

    @app.route("/loans/<loan_id>", methods=["GET"])
    def get_loan(loan_id: str):
        loan = _loan_store.get(loan_id)
        if loan is None:
            return jsonify({"error": f"Loan '{loan_id}' not found"}), 404
        return jsonify(loan), 200

    @app.route("/loans/<loan_id>/status", methods=["PUT"])
    def update_loan_status(loan_id: str):
        loan = _loan_store.get(loan_id)
        if loan is None:
            return jsonify({"error": f"Loan '{loan_id}' not found"}), 404

        data = request.get_json(silent=True)
        if not data or "status" not in data:
            return jsonify({"error": "'status' is required"}), 400

        new_status = data["status"]
        if new_status not in _VALID_STATUSES:
            return (
                jsonify(
                    {
                        "error": (
                            f"Invalid status. Must be one of: "
                            f"{sorted(_VALID_STATUSES)}"
                        )
                    }
                ),
                400,
            )

        loan["status"] = new_status
        return jsonify(loan), 200

    @app.route("/loans/<loan_id>/approve", methods=["POST"])
    def approve_loan(loan_id: str):
        loan = _loan_store.get(loan_id)
        if loan is None:
            return jsonify({"error": f"Loan '{loan_id}' not found"}), 404
        if loan["status"] != "pending":
            return jsonify({"error": "Only pending loans can be approved"}), 409
        loan["status"] = "approved"
        return jsonify(loan), 200

    @app.route("/loans/<loan_id>/reject", methods=["POST"])
    def reject_loan(loan_id: str):
        loan = _loan_store.get(loan_id)
        if loan is None:
            return jsonify({"error": f"Loan '{loan_id}' not found"}), 404
        if loan["status"] != "pending":
            return jsonify({"error": "Only pending loans can be rejected"}), 409
        loan["status"] = "rejected"
        return jsonify(loan), 200

    return app


loan_app = create_loan_app()

if __name__ == "__main__":
    loan_app.run(host="0.0.0.0", port=8000)
