# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] – 2026-03-09 – Epic: User Authentication

### Added (DOCS phase)
- `docs/auth_api_docs.md` – comprehensive API documentation covering all authentication endpoints: `POST /auth/login`, `POST /auth/logout`, `GET /auth/oauth2/authorize`, `GET /auth/oauth2/callback`, `POST /auth/refresh-token`, `GET /auth/protected`, `GET /health`, `POST /sessions/create`, `POST /sessions/refresh`, `POST /sessions/terminate`; includes JWT payload structure, environment configuration reference, token blacklist backend comparison, RBAC role/permission model, Mermaid flow diagrams, and curl examples for every endpoint

### Added (TEST phase)
- `microservices/auth_service/tests/test_jwt_util.py` – extended with `TestGenerateRefreshToken`, `TestExtractUsername`, `TestEdgeCases` classes; `jwt_util.py` now at **100% coverage** (Task 1)
- `services/tests/integration/test_authentication_flow_it.py` – full authentication flow integration tests covering login, token validation via endpoints, token uniqueness, and error handling (Task 2 / AuthenticationFlowIT)
- `auth/__init__.py` + `auth/login.py` – public `generate_jwt()` / `verify_jwt()` API with input validation (Task 3)
- `tests/unit/auth/test_login.py` – 31 unit tests for `auth/login.py`; **100% coverage** (Task 3)
- `tests/integration/auth/test_rbac.py` – RBAC integration tests covering role policies, 403 for unauthorized roles, and token expiry handling (Task 4)
- Updated `pyproject.toml` – `testpaths` extended to include `microservices` and `tests`; `--import-mode=importlib` added; coverage targets expanded

### Test Results
- **185 tests pass, 0 failures**
- `auth/login.py`: 100% coverage
- `microservices/auth_service/utils/jwt_util.py`: 100% coverage
- Overall project coverage: 95%


### Added
- **Task 4 – Base Python Microservice Structure** (`microservices/auth_service/`)
  - `main.py` – Flask application factory with `/health` route; environment-based startup.
  - `config.py` – `Config`, `DevelopmentConfig`, `TestingConfig`, `ProductionConfig` driven by environment variables.
  - `requirements.txt` – Pinned Flask, PyJWT, gunicorn, python-dotenv.

- **Task 3 + 6 – JWT Authentication Logic + RBAC** (`microservices/auth_service/`)
  - `utils/jwt_util.py` – `generate_token()` (embeds `userId`, `roles`, `permissions`, `expiry`), `generate_refresh_token()`, `validate_token()`, `renew_token()` (renews even expired tokens), `has_role()`, `check_roles()`, and mock role/permission helpers.
  - `controllers/LoginController.py` – Flask blueprint with `POST /auth/login` (issues access + refresh tokens with roles), `POST /auth/refresh-token`, `GET /auth/protected` (ROLE_ADMIN required); `jwt_required` and `role_required` decorators.
  - `tests/test_jwt_util.py` – 23 unit tests covering all jwt_util acceptance criteria.
  - `tests/test_login_controller.py` – 13 integration tests covering all LoginController acceptance criteria.

- **Task 2 – Session Management API Gateway** (`src/microservices/auth/`)
  - `user_sessions.py` – `UserSession` dataclass with in-memory store; `create()`, `terminate()`, `update_tokens()`, `is_expired()` methods.
  - `api_gateway.py` – Flask blueprint with `POST /sessions/create`, `POST /sessions/refresh` (validates token expiry, AC3), `POST /sessions/terminate`; consistent `{status, data}` response envelope (AC2).

- **Task 1 – Java JwtUtil** (`src/main/java/com/zcloud/platform/util/JwtUtil.java`)
  - `generateToken(userId, roles)` – issues HS256 JWT with `userId`, `roles`, `expiry`, `jti` claims.
  - `renewToken(token)` – renews even expired tokens by ignoring `exp` during parse.
  - `validateToken(token)` / `validateToken(token, requiredRole)` – rejects expired, tampered, or payload-incomplete tokens with `JwtValidationException` (401-semantic message).
  - `src/test/java/.../TestJwtUtil.java` – 10 JUnit 5 tests covering all three ACs.

- **Task 5 – Java SecurityUtils** (`src/main/java/com/zcloud/platform/util/SecurityUtils.java`)
  - `hasRole()`, `hasRoleInClaims()`, `hasAllRoles()`, `hasAnyRole()` – role-based access checks; thread-safe.
  - `recordFailedAttempt()`, `getFailedAttemptCount()`, `resetFailedAttempts()`, `isLockedOut()` – concurrent access attempt tracking via `ConcurrentHashMap`.
  - `src/test/java/.../TestSecurityUtils.java` – 14 JUnit 5 tests covering 100% of new methods.

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
