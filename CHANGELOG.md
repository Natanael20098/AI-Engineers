# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] – 2026-03-09

### Added
- **User Authentication Microservice** (`services/authentication/`)
  - `authentication.py` – Flask application with `POST /auth/login` and `POST /auth/logout` endpoints; `generate_jwt_token()` issues HS256-signed JWTs with configurable expiry and a `jti` claim for revocation.
  - `models.py` – `BaseModel` and `UserProfileModel` (extends `BaseModel`) with PBKDF2-HMAC-SHA256 password hashing and OAuth2 user support.
  - `oauth.py` – OAuth2 Authorization Code Flow blueprint (`GET /auth/oauth2/authorize`, `GET /auth/oauth2/callback`) for third-party authentication.
  - `token_store.py` – Pluggable JWT blacklist with in-memory (default) and Redis backends.
  - `config.py` – Environment-driven configuration with `development`, `testing`, and `production` profiles.
  - `Dockerfile` – Multi-stage Docker image running Gunicorn with a non-root user.
  - `requirements.txt` – Pinned production dependencies (Flask, PyJWT, requests, gunicorn, redis).
  - `tests/test_authentication.py` – 12 unit/integration tests covering all acceptance criteria.
- `README.md` – Project overview, setup instructions, and API reference.
- `.gitignore` – Python/Node/IDE/OS ignore patterns.
- `.dockerignore` – Docker build context exclusions.

## [Unreleased] – 2026-03-09

### Added
- **Project-level Poetry skeleton** (`pyproject.toml`) with Python 3.12, shared dev dependencies (pytest, black, isort, flake8, mypy), and root pytest configuration targeting the `services/` tree.
- **Per-service Poetry configs** (`services/authentication/pyproject.toml`, `services/loan_management/pyproject.toml`, `services/client_management/pyproject.toml`) with pinned production and dev dependencies.
- **Loan Management service skeleton** (`services/loan_management/`) – DDD package layout with `domain/`, `application/`, `infrastructure/`, and `presentation/` layers under `src/loan_management/`.
- **Client Management service skeleton** (`services/client_management/`) – identical DDD layer structure under `src/client_management/`.
- **Root `docker-compose.yml`** for local development: PostgreSQL 16, Redis 7, Nginx 1.25 (reverse proxy), and all three microservices with health checks, named network (`natanael-net`), and named volumes.
- **`infra/nginx/nginx.conf`** – Nginx upstream and location blocks routing `/auth/`, `/loans/`, and `/clients/` to the respective services.
- **`infra/docker-compose.yml`** – Production-oriented Nginx + Redis compose for ECS-adjacent deployments with memory-limited Redis and health checks.
- **Terraform infrastructure** (`infra/aws/`):
  - `main.tf` – AWS provider (v5), S3 remote state with DynamoDB locking.
  - `variables.tf` – All shared variables (region, environment, VPC CIDRs, RDS config, ECS sizing, image URIs, alert email).
  - `outputs.tf` – VPC ID, subnet IDs, ECS cluster name, RDS endpoint, ALB DNS name.
  - `vpc.tf` – VPC, public/private subnets across two AZs, Internet Gateway, NAT Gateway, route tables, and security groups (ALB, ECS tasks, RDS).
  - `ecs.tf` – ECS Fargate cluster with Container Insights, IAM execution/task roles, ALB with target group and HTTP listener, CloudWatch log group, task definition with Secrets Manager injection, ECS service with deployment circuit breaker and rolling update, and CPU-based auto-scaling policy.
  - `rds.tf` – Multi-AZ RDS PostgreSQL 16 instance with gp3 encrypted storage, parameter group, automated backups, Performance Insights, and SSM parameters for endpoint/name.
  - `monitoring.tf` – CloudWatch dashboard (ECS CPU/memory, RDS CPU, ALB request count), SNS alarm topic with email subscription, metric alarms for ECS CPU/memory/task-count, RDS CPU/storage, ALB 5xx errors, and CloudTrail with S3 audit log bucket.
- **Jenkins CI/CD pipeline** (`ci_cd/jenkins/Jenkinsfile`) – Parameterized pipeline for all three services across dev/staging/prod: lint, unit tests with coverage publishing, Docker build, Trivy security scan, ECR push, and ECS rolling deploy with Slack notifications.
- **`scripts/deployment/build_scripts.sh`** – Executable bash script with `build`, `push`, and `deploy` subcommands for building Docker images, pushing to ECR (auto-creating repos with scan-on-push), and deploying new task definition revisions to ECS with stability wait.
- **`.env.example`** – Environment variable template covering authentication, database, Redis, AWS, and Jenkins/Slack settings.
