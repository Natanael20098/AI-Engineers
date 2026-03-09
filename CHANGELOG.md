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
