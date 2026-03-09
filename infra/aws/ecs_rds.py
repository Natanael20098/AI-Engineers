"""
ECS and RDS configuration utilities.

Functions:
    configure_ecs: Register an ECS task definition and return task definition details.
    connect_rds:   Establish a connection to an RDS PostgreSQL instance and verify it.

These functions wrap the AWS ECS and PostgreSQL APIs.  In production they operate
against real AWS infrastructure described in infra/aws/ecs.tf and infra/aws/rds.tf;
in tests they are exercised through moto mocks and unittest.mock psycopg2 patches,
mirroring the docker-compose setup defined in docker-compose.yml.
"""

from __future__ import annotations

from typing import Any

import boto3


def configure_ecs(
    cluster_name: str,
    task_family: str,
    container_definitions: list[dict[str, Any]],
    cpu: str = "256",
    memory: str = "512",
    network_mode: str = "awsvpc",
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Register an ECS task definition for the given cluster.

    Parameters
    ----------
    cluster_name:
        Name of the ECS cluster (must already exist).
    task_family:
        Task definition family name.
    container_definitions:
        List of container definition dicts (name, image, portMappings, …).
    cpu:
        Fargate CPU units (e.g. "256", "512").
    memory:
        Fargate memory in MiB (e.g. "512", "1024").
    network_mode:
        ECS network mode; "awsvpc" is required for Fargate.
    region:
        AWS region name.

    Returns
    -------
    dict
        Task definition details including taskDefinitionArn, family, revision,
        status, and cluster name.

    Raises
    ------
    botocore.exceptions.ClientError
        On any AWS API error.
    """
    client = boto3.client("ecs", region_name=region)

    response = client.register_task_definition(
        family=task_family,
        networkMode=network_mode,
        requiresCompatibilities=["FARGATE"],
        cpu=cpu,
        memory=memory,
        containerDefinitions=container_definitions,
    )
    task_def = response["taskDefinition"]
    return {
        "task_definition_arn": task_def["taskDefinitionArn"],
        "family": task_def["family"],
        "revision": task_def["revision"],
        "status": task_def["status"],
        "cluster": cluster_name,
    }


def connect_rds(
    host: str,
    port: int,
    dbname: str,
    user: str,
    password: str,
    connect_timeout: int = 10,
) -> bool:
    """Connect to an RDS PostgreSQL instance and verify connectivity.

    Establishes a psycopg2 connection to the specified host, executes
    ``SELECT 1`` to confirm the database is reachable, then closes the
    connection.

    Parameters
    ----------
    host:
        RDS endpoint hostname (or ``localhost`` / service name in docker-compose).
    port:
        PostgreSQL port (typically 5432).
    dbname:
        Target database name.
    user:
        Database user name.
    password:
        Database user password.
    connect_timeout:
        Seconds to wait before aborting the connection attempt.

    Returns
    -------
    bool
        ``True`` if the connection succeeded and ``SELECT 1`` returned a result.

    Raises
    ------
    psycopg2.OperationalError
        If the connection cannot be established within *connect_timeout* seconds,
        or if the host is unreachable (handles network latency and RDS failover).
    """
    import psycopg2  # imported here to allow patching in tests

    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=connect_timeout,
    )
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        return result is not None and result[0] == 1
    finally:
        conn.close()
