# Authentication Module – API Documentation

> **Version:** 1.0.0
> **Last Updated:** 2026-03-09
> **Epic:** User Authentication — Microservice Redesign
> **Base URL (local):** `http://localhost:5001` (via Docker) or `http://localhost:5000` (direct)
> **Nginx Gateway:** `http://localhost:80/auth/` → authentication service

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Authentication Flow](#authentication-flow)
3. [Common Conventions](#common-conventions)
4. [JWT Token Structure](#jwt-token-structure)
5. [Endpoints – Core Authentication Service](#endpoints--core-authentication-service)
   - [POST /auth/login](#post-authlogin)
   - [POST /auth/logout](#post-authlogout)
   - [GET /auth/oauth2/authorize](#get-authoauth2authorize)
   - [GET /auth/oauth2/callback](#get-authoauth2callback)
6. [Endpoints – Auth Microservice (RBAC)](#endpoints--auth-microservice-rbac)
   - [POST /auth/login (RBAC)](#post-authlogin-rbac)
   - [POST /auth/refresh-token](#post-authrefresh-token)
   - [GET /auth/protected](#get-authprotected)
   - [GET /health](#get-health)
7. [Endpoints – Session Management Gateway](#endpoints--session-management-gateway)
   - [POST /sessions/create](#post-sessionscreate)
   - [POST /sessions/refresh](#post-sessionsrefresh)
   - [POST /sessions/terminate](#post-sessionsterminate)
8. [Error Reference](#error-reference)
9. [Environment Configuration](#environment-configuration)
10. [Token Blacklist Backends](#token-blacklist-backends)
11. [Role-Based Access Control](#role-based-access-control)

---

## Architecture Overview

The authentication system is composed of three layers implemented as Python/Flask microservices:

```mermaid
graph TD
    Client["Client (Browser / API consumer)"]
    Nginx["Nginx Reverse Proxy\n:80"]
    AuthSvc["Authentication Service\n:5001 → :5000\nservices/authentication/"]
    AuthMS["Auth Microservice\n(RBAC + Refresh Tokens)\nmicroservices/auth_service/"]
    SessionGW["Session Management Gateway\nsrc/microservices/auth/"]
    Redis["Redis\n:6379\n(Token Blacklist)"]
    Postgres["PostgreSQL\n:5432"]

    Client --> Nginx
    Nginx -->|"/auth/*"| AuthSvc
    AuthSvc --> Redis
    AuthSvc --> Postgres
    AuthMS --> Redis
    SessionGW --> AuthMS
```

| Layer | Location | Purpose |
|---|---|---|
| Core Authentication Service | `services/authentication/` | Login, logout, OAuth2 flow, token blacklist |
| Auth Microservice (RBAC) | `microservices/auth_service/` | JWT with roles/permissions, token refresh |
| Session Management Gateway | `src/microservices/auth/` | Session lifecycle management |

---

## Authentication Flow

### Password Login Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Auth Service
    participant DB as User Store
    participant BL as Token Blacklist

    C->>A: POST /auth/login {username, password}
    A->>DB: get_by_username(username)
    DB-->>A: UserProfileModel
    A->>A: verify_password(PBKDF2-HMAC-SHA256)
    A->>A: generate_jwt_token() → {sub, username, email, iat, exp, jti}
    A-->>C: 200 {token, user}

    Note over C,A: Authenticated requests
    C->>A: POST /auth/logout\nAuthorization: Bearer <token>
    A->>A: decode JWT, extract jti
    A->>BL: blacklist.add(jti, exp)
    A-->>C: 200 {message: "Successfully logged out"}
```

### OAuth2 Authorization Code Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Auth Service
    participant P as OAuth2 Provider (Google)

    C->>A: GET /auth/oauth2/authorize
    A->>A: Generate state token (CSRF), store in session
    A-->>C: 302 Redirect → Provider Login Page

    C->>P: User logs in
    P-->>C: Redirect to /auth/oauth2/callback?code=...&state=...

    C->>A: GET /auth/oauth2/callback?code=...&state=...
    A->>A: Validate state (CSRF check)
    A->>P: POST token_url {code, client_id, client_secret, ...}
    P-->>A: {access_token, id_token}
    A->>P: GET userinfo_url (Bearer access_token)
    P-->>A: {sub, email, name}
    A->>A: get_or_create_user(provider, userinfo)
    A->>A: generate_jwt_token(user)
    A-->>C: 200 {token, user}
```

---

## Common Conventions

### Request Format

All endpoints that accept a body expect **`Content-Type: application/json`**.

### Authentication Header

Protected endpoints require the JWT passed as a Bearer token:

```
Authorization: Bearer <jwt>
```

### Response Envelope

**Core Authentication Service** responses are flat JSON:

```json
{ "token": "...", "user": { ... } }
```

**Session Management Gateway** uses a consistent envelope:

```json
{ "status": "success", "data": { ... } }
{ "status": "error",   "message": "..." }
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| `200` | OK – request succeeded |
| `201` | Created – resource created (session) |
| `302` | Redirect – OAuth2 provider redirect |
| `400` | Bad Request – missing or malformed body |
| `401` | Unauthorized – invalid/expired/revoked credentials or token |
| `403` | Forbidden – authenticated but insufficient role |
| `404` | Not Found – session does not exist |
| `502` | Bad Gateway – upstream OAuth2 provider error |

---

## JWT Token Structure

### Access Token Payload (Core Auth Service)

```json
{
  "sub":      "user-uuid-...",
  "username": "alice",
  "email":    "alice@example.com",
  "iat":      1741478400,
  "exp":      1741482000,
  "jti":      "a1b2c3d4-..."
}
```

### Access Token Payload (RBAC Auth Microservice)

```json
{
  "userId":      "user-001",
  "username":    "alice",
  "roles":       ["ROLE_USER"],
  "permissions": ["read", "write"],
  "iat":         1741478400,
  "exp":         1741482000,
  "expiry":      "2026-03-09T11:00:00+00:00",
  "jti":         "a1b2c3d4-...",
  "token_type":  "access"
}
```

### Refresh Token Payload

```json
{
  "userId":     "user-001",
  "username":   "alice",
  "iat":        1741478400,
  "exp":        1742083200,
  "expiry":     "2026-03-16T10:00:00+00:00",
  "jti":        "e5f6g7h8-...",
  "token_type": "refresh"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sub` / `userId` | string | Unique user identifier |
| `username` | string | User's login handle |
| `email` | string | User's email (core service only) |
| `roles` | array | RBAC roles (microservice only) |
| `permissions` | array | Explicit permissions (microservice only) |
| `iat` | number | Issued-at (UTC epoch seconds) |
| `exp` | number | Expiry (UTC epoch seconds) |
| `expiry` | string | Human-readable ISO-8601 expiry |
| `jti` | string | Unique JWT ID (used for revocation) |
| `token_type` | string | `"access"` or `"refresh"` |

**Algorithm:** HS256
**Default Access Token Lifetime:** 60 minutes
**Default Refresh Token Lifetime:** 7 days

---

## Endpoints – Core Authentication Service

> **Source:** `services/authentication/`
> **Service port:** `5000` (container), `5001` (host via Docker)

---

### POST /auth/login

Validate username and password credentials. Returns a signed JWT on success.

#### Request

```
POST /auth/login
Content-Type: application/json
```

```json
{
  "username": "alice",
  "password": "s3cr3t"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | ✅ | User's login handle (whitespace trimmed) |
| `password` | string | ✅ | User's plain-text password |

#### Response – 200 OK

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "user_id":   "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "username":  "alice",
    "email":     "alice@example.com",
    "is_active": true
  }
}
```

#### Response – 400 Bad Request

```json
{ "error": "Request body must be valid JSON" }
{ "error": "username and password are required" }
```

#### Response – 401 Unauthorized

```json
{ "error": "Invalid username or password" }
{ "error": "Account is disabled" }
```

> **Security note:** "not found" and "wrong password" return the same message to prevent username enumeration.

#### curl Example

```bash
curl -s -X POST http://localhost:5001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "s3cr3t"}'
```

---

### POST /auth/logout

Revoke the caller's JWT by adding its `jti` to the token blacklist. Requires a valid, non-revoked Bearer token.

#### Request

```
POST /auth/logout
Authorization: Bearer <token>
```

No request body needed.

#### Response – 200 OK

```json
{ "message": "Successfully logged out" }
```

#### Response – 401 Unauthorized

```json
{ "error": "Authorization token is missing" }
{ "error": "Token has expired" }
{ "error": "Token has been revoked" }
{ "error": "Invalid token: ..." }
```

#### curl Example

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -s -X POST http://localhost:5001/auth/logout \
  -H "Authorization: Bearer $TOKEN"
```

> **Effect:** After logout, any subsequent request with the same token returns `401 Token has been revoked`. The blacklist entry expires automatically when the original token would have expired.

---

### GET /auth/oauth2/authorize

Redirect the user's browser to the configured OAuth2 provider's login page. A CSRF `state` token is generated per request and stored in the server-side session.

#### Request

```
GET /auth/oauth2/authorize
```

No parameters required. The service builds the authorization URL from environment configuration (`OAUTH2_AUTHORIZE_URL`, `OAUTH2_CLIENT_ID`, `OAUTH2_REDIRECT_URI`, `OAUTH2_SCOPES`).

#### Response – 302 Found

```
Location: https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=...&response_type=code&scope=openid+email+profile&state=<csrf_token>&access_type=online
```

#### curl Example

```bash
# Follow the redirect in a browser or with -L
curl -v http://localhost:5001/auth/oauth2/authorize
```

---

### GET /auth/oauth2/callback

Handle the provider's redirect after successful authentication. Validates the CSRF state, exchanges the authorization code for provider tokens, fetches user information, and issues a local JWT.

#### Request

```
GET /auth/oauth2/callback?code=<authorization_code>&state=<csrf_state>
```

| Query Param | Type | Required | Description |
|-------------|------|----------|-------------|
| `code` | string | ✅ | Authorization code from the provider |
| `state` | string | ✅ | CSRF state token (must match session value) |

#### Response – 200 OK

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "user_id":        "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "username":       "Alice Smith",
    "email":          "alice@gmail.com",
    "is_active":      true,
    "oauth_provider": "accounts.google.com",
    "oauth_subject":  "109876543210987654321"
  }
}
```

#### Response – 400 Bad Request

```json
{ "error": "Invalid or missing OAuth2 state parameter" }
{ "error": "Authorization code not provided" }
```

#### Response – 502 Bad Gateway

```json
{ "error": "Failed to communicate with OAuth2 provider" }
{ "error": "OAuth2 authentication failed" }
```

> **Note:** New OAuth2 users are automatically provisioned. Returning users are looked up by `(provider, subject)` pair, so the same account is reused across multiple logins.

---

## Endpoints – Auth Microservice (RBAC)

> **Source:** `microservices/auth_service/`
> **Includes:** JWT with embedded roles and permissions, token refresh, role-protected routes.

---

### POST /auth/login (RBAC)

Authenticate a user and receive both an **access token** (with roles and permissions) and a **refresh token**.

#### Request

```
POST /auth/login
Content-Type: application/json
```

```json
{
  "username": "alice",
  "password": "alice_pass"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | ✅ | User's login handle |
| `password` | string | ✅ | User's plain-text password |

**Built-in test users:**

| Username | Password | Roles | Permissions |
|----------|----------|-------|-------------|
| `alice` | `alice_pass` | `ROLE_USER` | `read`, `write` |
| `admin` | `admin_pass` | `ROLE_ADMIN`, `ROLE_USER` | `read`, `write`, `delete` |
| `bob` | `bob_pass` | `ROLE_USER` | `read` |

#### Response – 200 OK

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "user_id":     "user-001",
    "username":    "alice",
    "roles":       ["ROLE_USER"],
    "permissions": ["read", "write"]
  }
}
```

#### Response – 400 Bad Request

```json
{ "error": "Request body must be valid JSON" }
{ "error": "username and password are required" }
```

#### Response – 401 Unauthorized

```json
{ "error": "Invalid username or password" }
```

#### curl Example

```bash
curl -s -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "alice_pass"}' | jq .
```

---

### POST /auth/refresh-token

Exchange an existing token (access or refresh, including expired access tokens) for a new access token. Preserves the user's identity and roles from the original token.

#### Request

```
POST /auth/refresh-token
Content-Type: application/json
```

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `refresh_token` | string | ✅ (or `token`) | Refresh token or any previously-issued token |
| `token` | string | ✅ (or `refresh_token`) | Alternative field name accepted |

#### Response – 200 OK

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Response – 400 Bad Request

```json
{ "error": "Request body must be valid JSON" }
{ "error": "refresh_token is required" }
```

#### Response – 401 Unauthorized

```json
{ "error": "Invalid token: ..." }
```

#### curl Example

```bash
REFRESH_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -s -X POST http://localhost:5000/auth/refresh-token \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}"
```

---

### GET /auth/protected

Example role-protected endpoint. Demonstrates the `ROLE_ADMIN` access control enforcement.

#### Request

```
GET /auth/protected
Authorization: Bearer <token>
```

#### Response – 200 OK (admin users only)

```json
{
  "message": "Access granted",
  "user": "admin"
}
```

#### Response – 401 Unauthorized

```json
{ "error": "Authorization token is missing" }
{ "error": "Token has expired" }
{ "error": "Invalid token: ..." }
```

#### Response – 403 Forbidden (non-admin users)

```json
{ "error": "Forbidden: role 'ROLE_ADMIN' required" }
```

#### curl Example

```bash
# Login as admin first
TOKEN=$(curl -s -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin_pass"}' | jq -r .token)

curl -s http://localhost:5000/auth/protected \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /health

Service liveness probe. Returns immediately without authentication.

#### Request

```
GET /health
```

#### Response – 200 OK

```json
{
  "status": "ok",
  "service": "auth-service"
}
```

#### curl Example

```bash
curl -s http://localhost:5000/health
```

---

## Endpoints – Session Management Gateway

> **Source:** `src/microservices/auth/`
> **Blueprint prefix:** `/sessions`
> **Response envelope:** `{"status": "success"|"error", "data"|"message": ...}`

---

### POST /sessions/create

Create a new session for an authenticated user. Issues both an access token and a refresh token, and persists a `UserSession` record.

#### Request

```
POST /sessions/create
Content-Type: application/json
```

```json
{
  "user_id":     "user-001",
  "username":    "alice",
  "roles":       ["ROLE_USER"],
  "permissions": ["read", "write"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | User's unique identifier |
| `username` | string | ✅ | User's login handle |
| `roles` | array | ❌ | RBAC roles (resolved from mock data if omitted) |
| `permissions` | array | ❌ | Permissions (resolved from mock data if omitted) |

#### Response – 201 Created

```json
{
  "status": "success",
  "data": {
    "session_id":   "d4e5f6a7-...",
    "token":        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_at":   "2026-03-16T10:00:00+00:00"
  }
}
```

#### Response – 400 Bad Request

```json
{ "status": "error", "message": "Request body must be valid JSON" }
{ "status": "error", "message": "user_id and username are required" }
```

#### curl Example

```bash
curl -s -X POST http://localhost:5000/sessions/create \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-001",
    "username": "alice",
    "roles": ["ROLE_USER"],
    "permissions": ["read", "write"]
  }' | jq .
```

---

### POST /sessions/refresh

Refresh an existing session. Validates the refresh token's expiry, issues new access and refresh tokens, and updates the stored session.

#### Request

```
POST /sessions/refresh
Content-Type: application/json
```

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `refresh_token` | string | ✅ | Refresh token obtained from `/sessions/create` |

#### Response – 200 OK

```json
{
  "status": "success",
  "data": {
    "token":         "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "session_id":    "d4e5f6a7-..."
  }
}
```

#### Response – 400 Bad Request

```json
{ "status": "error", "message": "Request body must be valid JSON" }
{ "status": "error", "message": "refresh_token is required" }
```

#### Response – 401 Unauthorized

```json
{ "status": "error", "message": "Refresh token has expired" }
{ "status": "error", "message": "Invalid refresh token: ..." }
{ "status": "error", "message": "Session has expired or been terminated" }
```

#### Response – 404 Not Found

```json
{ "status": "error", "message": "Session not found" }
```

#### curl Example

```bash
REFRESH_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -s -X POST http://localhost:5000/sessions/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}" | jq .
```

---

### POST /sessions/terminate

Terminate an active session. Marks the session as inactive; subsequent refresh attempts on the same session will be rejected.

#### Request

```
POST /sessions/terminate
Content-Type: application/json
```

```json
{
  "session_id": "d4e5f6a7-..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | ✅ | Session identifier from `/sessions/create` |

#### Response – 200 OK

```json
{
  "status": "success",
  "data": {
    "message":    "Session terminated",
    "session_id": "d4e5f6a7-..."
  }
}
```

#### Response – 400 Bad Request

```json
{ "status": "error", "message": "Request body must be valid JSON" }
{ "status": "error", "message": "session_id is required" }
```

#### Response – 404 Not Found

```json
{ "status": "error", "message": "Session not found" }
```

#### curl Example

```bash
SESSION_ID="d4e5f6a7-..."

curl -s -X POST http://localhost:5000/sessions/terminate \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\"}" | jq .
```

---

## Error Reference

### Error Response Structure

| Service Layer | Error Format |
|---|---|
| Core Authentication | `{ "error": "<message>" }` |
| RBAC Microservice | `{ "error": "<message>" }` |
| Session Gateway | `{ "status": "error", "message": "<message>" }` |

### Common Error Messages

| HTTP Code | Message | Cause |
|-----------|---------|-------|
| `400` | `Request body must be valid JSON` | Missing body or wrong Content-Type |
| `400` | `username and password are required` | Empty username or password field |
| `400` | `Invalid or missing OAuth2 state parameter` | CSRF state mismatch on callback |
| `400` | `Authorization code not provided` | Missing `code` query param on callback |
| `401` | `Invalid username or password` | Unknown user or wrong password |
| `401` | `Account is disabled` | `is_active = False` on the user record |
| `401` | `Authorization token is missing` | No `Authorization: Bearer ...` header |
| `401` | `Token has expired` | JWT `exp` claim in the past |
| `401` | `Token has been revoked` | Token `jti` is in the blacklist |
| `401` | `Invalid token: ...` | Bad signature or malformed JWT |
| `401` | `Refresh token has expired` | Session refresh attempted with expired refresh token |
| `403` | `Forbidden: role '...' required` | User lacks the required RBAC role |
| `404` | `Session not found` | No session matches the provided `session_id` / `refresh_token` |
| `502` | `Failed to communicate with OAuth2 provider` | Provider HTTP error during token exchange |

---

## Environment Configuration

### Core Authentication Service (`services/authentication/config.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | `development` / `testing` / `production` |
| `SECRET_KEY` | `change-me-in-production` | Flask session secret |
| `JWT_SECRET_KEY` | `jwt-secret-change-in-production` | HMAC signing key for JWTs |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | `60` | Access token lifetime in minutes |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/authdb` | PostgreSQL connection string |
| `OAUTH2_CLIENT_ID` | _(empty)_ | OAuth2 provider client ID |
| `OAUTH2_CLIENT_SECRET` | _(empty)_ | OAuth2 provider client secret |
| `OAUTH2_AUTHORIZE_URL` | `https://accounts.google.com/o/oauth2/v2/auth` | Provider authorization endpoint |
| `OAUTH2_TOKEN_URL` | `https://oauth2.googleapis.com/token` | Provider token exchange endpoint |
| `OAUTH2_USERINFO_URL` | `https://www.googleapis.com/oauth2/v3/userinfo` | Provider user profile endpoint |
| `OAUTH2_REDIRECT_URI` | `http://localhost:5000/auth/oauth2/callback` | Callback URL registered with the provider |
| `OAUTH2_SCOPES` | `openid email profile` | Space-separated OAuth2 scopes |
| `TOKEN_BLACKLIST_BACKEND` | `memory` | `memory` or `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |

### RBAC Auth Microservice (`microservices/auth_service/config.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | `jwt-secret-change-in-production` | HMAC signing key |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | `60` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRES_DAYS` | `7` | Refresh token lifetime |
| `AUTH_SERVICE_HOST` | `0.0.0.0` | Bind address |
| `AUTH_SERVICE_PORT` | `5000` | Bind port |

### Docker Compose Overrides

The `docker-compose.yml` passes the following to the `authentication` container:

```yaml
environment:
  FLASK_ENV: ${FLASK_ENV:-development}
  SECRET_KEY: ${SECRET_KEY:-dev-secret-key-change-in-prod}
  JWT_EXPIRY_MINUTES: ${JWT_EXPIRY_MINUTES:-60}
  REDIS_URL: redis://redis:6379/0
  TOKEN_BLACKLIST_BACKEND: ${TOKEN_BLACKLIST_BACKEND:-redis}
```

> **Production:** Set `TOKEN_BLACKLIST_BACKEND=redis` to support multi-container deployments. The default `memory` backend does not persist across process restarts.

---

## Token Blacklist Backends

The `token_store.py` module provides two backend implementations:

### In-Memory (`TOKEN_BLACKLIST_BACKEND=memory`)

- Default. Suitable for development and single-process deployments.
- Stores `{jti → expires_at}` in a Python dict.
- Automatically removes expired entries on lookup.
- **Not suitable** for multi-container production use (each container maintains its own store).

### Redis (`TOKEN_BLACKLIST_BACKEND=redis`)

- Production backend. Requires `redis` package and `REDIS_URL`.
- Each revoked `jti` is stored with Redis TTL matching the token's remaining lifetime.
- Redis handles expiry automatically (`SETEX`).
- Key prefix: `auth:blacklist:<jti>`
- Safe for multi-container deployments.

---

## Role-Based Access Control

Roles and permissions are embedded in JWT payloads issued by the RBAC microservice layer.

### Available Roles

| Role | Description |
|------|-------------|
| `ROLE_USER` | Standard authenticated user |
| `ROLE_ADMIN` | Administrative access; supersedes `ROLE_USER` |

### Permission Model

| Permission | Granted to |
|------------|-----------|
| `read` | All users (`alice`, `bob`, `admin`) |
| `write` | `alice`, `admin` |
| `delete` | `admin` only |

### Protecting an Endpoint

Use the `role_required` decorator from `LoginController.py`:

```python
from .LoginController import role_required

@app.route("/admin/resource")
@role_required("ROLE_ADMIN")
def admin_resource():
    return jsonify({"message": "admin-only data"})
```

The decorator:
1. Validates the Bearer token via `jwt_required`.
2. Checks the `roles` array in the decoded payload.
3. Returns `403 Forbidden` if the required role is absent.

### Checking Roles Programmatically

```python
from microservices.auth_service.utils.jwt_util import has_role, check_roles

# Check directly from a token string
if has_role(token, "ROLE_ADMIN"):
    ...

# Check from an already-decoded payload
if check_roles(payload, "ROLE_ADMIN"):
    ...
```
