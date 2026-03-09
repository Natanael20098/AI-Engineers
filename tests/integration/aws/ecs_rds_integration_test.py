"""
Integration tests: ECS and RDS configuration.

Verifies that:
  AC1  ECS can connect to RDS without errors in the test environment.
  AC2  All integration tests pass with success, no timeouts occur.
  AC3  Simulated ECS and RDS running seamlessly in a docker-compose-like setup.

Local stack simulation
----------------------
In a live environment the stack is started with::

    docker-compose up postgres authentication

For CI the tests substitute real AWS / Postgres calls with:
  - moto (mock_ecs decorator) for ECS task-definition registration.
  - unittest.mock.patch for psycopg2.connect to simulate RDS connectivity
    without requiring a running database.

Edge cases covered
------------------
- Network latency between ECS and RDS (connect_timeout parameter).
- RDS failover scenario (OperationalError raised → callers surface the error).
- Connection longevity (multiple sequential queries on the same connection).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import boto3
import pytest

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from moto import mock_aws  # noqa: E402 – env vars must be set first

from infra.aws.ecs_rds import configure_ecs, connect_rds  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def aws_credentials(monkeypatch):
    """Ensure moto receives dummy credentials even if real ones exist."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture()
def ecs_cluster(aws_credentials):
    """Create a mock ECS cluster via moto."""
    with mock_aws():
        client = boto3.client("ecs", region_name="us-east-1")
        client.create_cluster(clusterName="natanael-test")
        yield client


@pytest.fixture()
def sample_container_definitions():
    return [
        {
            "name": "authentication",
            "image": "natanael/authentication-service:latest",
            "portMappings": [{"containerPort": 5000, "protocol": "tcp"}],
            "environment": [
                {"name": "FLASK_ENV", "value": "testing"},
                {"name": "TOKEN_BLACKLIST_BACKEND", "value": "memory"},
            ],
        }
    ]


@pytest.fixture()
def mock_rds_connection():
    """Return a configured mock for a successful psycopg2 connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    return mock_conn


# ---------------------------------------------------------------------------
# AC1 – ECS can connect to RDS without errors
# ---------------------------------------------------------------------------


def test_configure_ecs_registers_task_definition(
    ecs_cluster, sample_container_definitions
):
    """configure_ecs must register a task definition without raising."""
    with mock_aws():
        result = configure_ecs(
            cluster_name="natanael-test",
            task_family="authentication-service",
            container_definitions=sample_container_definitions,
        )

    assert result["family"] == "authentication-service"
    assert result["task_definition_arn"] != ""
    assert result["status"] == "ACTIVE"
    assert result["cluster"] == "natanael-test"
    assert result["revision"] >= 1


def test_connect_rds_returns_true_on_successful_connection(mock_rds_connection):
    """connect_rds must return True when psycopg2 connects and SELECT 1 works."""
    with patch("psycopg2.connect", return_value=mock_rds_connection):
        result = connect_rds(
            host="postgres",
            port=5432,
            dbname="natanael_db",
            user="natanael",
            password="natanael_secret",
        )

    assert result is True


def test_connect_rds_passes_correct_parameters_to_psycopg2(mock_rds_connection):
    """connect_rds must forward all connection parameters to psycopg2.connect."""
    with patch("psycopg2.connect", return_value=mock_rds_connection) as mock_connect:
        connect_rds(
            host="rds-host.us-east-1.rds.amazonaws.com",
            port=5432,
            dbname="natanael_db",
            user="natanael",
            password="s3cr3t",
            connect_timeout=10,
        )

    mock_connect.assert_called_once_with(
        host="rds-host.us-east-1.rds.amazonaws.com",
        port=5432,
        dbname="natanael_db",
        user="natanael",
        password="s3cr3t",
        connect_timeout=10,
    )


def test_ecs_and_rds_integration_no_errors(
    ecs_cluster, sample_container_definitions, mock_rds_connection
):
    """ECS task definition registers AND RDS connects without any error."""
    with mock_aws():
        ecs_result = configure_ecs(
            cluster_name="natanael-test",
            task_family="authentication-service",
            container_definitions=sample_container_definitions,
        )

    with patch("psycopg2.connect", return_value=mock_rds_connection):
        rds_result = connect_rds(
            host="postgres",
            port=5432,
            dbname="natanael_db",
            user="natanael",
            password="natanael_secret",
        )

    # Both operations succeed without raising
    assert ecs_result["status"] == "ACTIVE"
    assert rds_result is True


# ---------------------------------------------------------------------------
# AC2 – No timeouts
# ---------------------------------------------------------------------------


def test_connect_rds_respects_custom_timeout(mock_rds_connection):
    """connect_timeout is forwarded to psycopg2 and no TimeoutError is raised."""
    with patch("psycopg2.connect", return_value=mock_rds_connection) as mock_connect:
        result = connect_rds(
            host="postgres",
            port=5432,
            dbname="natanael_db",
            user="natanael",
            password="secret",
            connect_timeout=5,
        )

    assert result is True
    _, kwargs = mock_connect.call_args
    assert kwargs["connect_timeout"] == 5


def test_configure_ecs_completes_without_timeout(
    aws_credentials, sample_container_definitions
):
    """configure_ecs must complete in well under 30 seconds with moto."""
    import time

    start = time.monotonic()
    with mock_aws():
        configure_ecs(
            cluster_name="natanael-test",
            task_family="auth-perf-test",
            container_definitions=sample_container_definitions,
        )
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"configure_ecs took {elapsed:.2f}s — possible timeout"


def test_multiple_sequential_rds_connections(mock_rds_connection):
    """Multiple sequential connect_rds calls all succeed (connection longevity)."""
    with patch("psycopg2.connect", return_value=mock_rds_connection):
        for _ in range(5):
            result = connect_rds(
                host="postgres",
                port=5432,
                dbname="natanael_db",
                user="natanael",
                password="natanael_secret",
            )
            assert result is True


# ---------------------------------------------------------------------------
# AC3 – Simulated ECS and RDS in docker-compose-like setup
# ---------------------------------------------------------------------------


def test_configure_ecs_fargate_compatible(
    aws_credentials, sample_container_definitions
):
    """Task definition must declare FARGATE compatibility (matches ecs.tf)."""
    with mock_aws():
        ecs_client = boto3.client("ecs", region_name="us-east-1")
        ecs_client.create_cluster(clusterName="natanael-dev")
        result = configure_ecs(
            cluster_name="natanael-dev",
            task_family="fargate-auth",
            container_definitions=sample_container_definitions,
            cpu="256",
            memory="512",
            network_mode="awsvpc",
        )

    assert "task_definition_arn" in result
    assert result["revision"] >= 1


def test_configure_ecs_multiple_revisions(
    aws_credentials, sample_container_definitions
):
    """Registering the same family twice creates successive revisions."""
    with mock_aws():
        first = configure_ecs(
            cluster_name="natanael-test",
            task_family="auth-service",
            container_definitions=sample_container_definitions,
        )
        second = configure_ecs(
            cluster_name="natanael-test",
            task_family="auth-service",
            container_definitions=sample_container_definitions,
        )

    assert second["revision"] > first["revision"]


def test_ecs_service_discovery_simulated(
    aws_credentials, sample_container_definitions
):
    """
    ECS service discovery simulation:
    The container_definitions environment contains AUTH_SERVICE_URL,
    mirroring the docker-compose AUTH_SERVICE_URL=http://authentication:5000.
    """
    discovery_defs = [
        {
            "name": "loan-management",
            "image": "python:3.12-slim",
            "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
            "environment": [
                {"name": "AUTH_SERVICE_URL", "value": "http://authentication:5000"},
                {
                    "name": "DATABASE_URL",
                    "value": "postgresql://natanael:secret@postgres:5432/natanael_db",
                },
            ],
        }
    ]
    with mock_aws():
        result = configure_ecs(
            cluster_name="natanael-dev",
            task_family="loan-management",
            container_definitions=discovery_defs,
        )

    assert result["family"] == "loan-management"
    assert result["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# Edge cases: network latency and RDS failover
# ---------------------------------------------------------------------------


def test_connect_rds_raises_on_operational_error():
    """
    RDS failover scenario: psycopg2.OperationalError must propagate to callers
    so they can implement retry logic.
    """
    import psycopg2

    with patch(
        "psycopg2.connect",
        side_effect=psycopg2.OperationalError("could not connect to server"),
    ):
        with pytest.raises(psycopg2.OperationalError, match="could not connect"):
            connect_rds(
                host="failed-replica.rds.amazonaws.com",
                port=5432,
                dbname="natanael_db",
                user="natanael",
                password="secret",
            )


def test_connect_rds_handles_network_latency_via_timeout():
    """
    Network latency simulation: OperationalError with timeout message must
    propagate cleanly so the caller can detect a timed-out connection.
    """
    import psycopg2

    with patch(
        "psycopg2.connect",
        side_effect=psycopg2.OperationalError("connection timed out"),
    ):
        with pytest.raises(psycopg2.OperationalError, match="timed out"):
            connect_rds(
                host="slow-rds.us-east-1.rds.amazonaws.com",
                port=5432,
                dbname="natanael_db",
                user="natanael",
                password="secret",
                connect_timeout=3,
            )


def test_connect_rds_closes_connection_on_query_error(mock_rds_connection):
    """Connection must be closed even if cursor.execute raises."""
    mock_cursor = mock_rds_connection.cursor.return_value
    mock_cursor.execute.side_effect = Exception("query failed")

    with patch("psycopg2.connect", return_value=mock_rds_connection):
        with pytest.raises(Exception, match="query failed"):
            connect_rds(
                host="postgres",
                port=5432,
                dbname="natanael_db",
                user="natanael",
                password="secret",
            )

    # The finally block must have called close even after the exception
    mock_rds_connection.close.assert_called_once()
