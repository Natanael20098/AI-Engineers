# Natanael – User Authentication Microservice

A Flask-based authentication microservice for the ZCloud Security Platform. It replaces the legacy monolithic authentication system and is designed to run in a Docker container.

## Features

- **POST /auth/login** – Validate credentials and issue a signed JWT
- **POST /auth/logout** – Revoke a JWT (token blacklist)
- **GET /auth/oauth2/authorize** – Redirect users to a third-party OAuth2 provider
- **GET /auth/oauth2/callback** – Exchange the authorization code for a local JWT

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+ |
| Web framework | Flask 3 |
| JWT | PyJWT |
| HTTP client (OAuth2) | requests |
| WSGI server | Gunicorn |
| Container | Docker |

## Project Structure

```
services/authentication/
├── __init__.py
├── authentication.py   # Flask app, login/logout routes, JWT utilities
├── config.py           # Environment-driven configuration
├── models.py           # UserProfileModel (extends BaseModel)
├── oauth.py            # OAuth2 Authorization Code Flow blueprint
├── token_store.py      # JWT blacklist (in-memory or Redis)
├── requirements.txt
├── Dockerfile
├── .dockerignore
└── tests/
    ├── __init__.py
    └── test_authentication.py
```

## Setup & Running Locally

### 1. Install dependencies

```bash
cd services/authentication
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env   # (create your own .env)
```

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | `development` / `testing` / `production` |
| `JWT_SECRET_KEY` | *(change me)* | Secret used to sign JWTs |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | `60` | Token lifetime in minutes |
| `OAUTH2_CLIENT_ID` | | Provider OAuth2 client ID |
| `OAUTH2_CLIENT_SECRET` | | Provider OAuth2 client secret |
| `OAUTH2_REDIRECT_URI` | `http://localhost:5000/auth/oauth2/callback` | Callback URL |
| `TOKEN_BLACKLIST_BACKEND` | `memory` | `memory` or `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL (when backend=redis) |

### 3. Run the development server

```bash
FLASK_ENV=development python3 -m services.authentication.authentication
```

### 4. Run with Docker

```bash
cd services/authentication
docker build -t auth-service .
docker run -p 5000:5000 \
  -e JWT_SECRET_KEY=my-secret \
  -e FLASK_ENV=production \
  auth-service
```

> **HTTPS**: In production, place a TLS-terminating reverse proxy (nginx, AWS ALB, etc.) in front of the container. Never expose port 5000 directly to the internet.

## API Reference

### POST /auth/login

**Request**
```json
{ "username": "alice", "password": "s3cr3t" }
```

**Response 200**
```json
{
  "token": "<jwt>",
  "user": { "user_id": "...", "username": "alice", "email": "alice@example.com", ... }
}
```

**Response 401**
```json
{ "error": "Invalid username or password" }
```

---

### POST /auth/logout

**Headers**: `Authorization: Bearer <token>`

**Response 200**
```json
{ "message": "Successfully logged out" }
```

---

### GET /auth/oauth2/authorize

Redirects the browser to the configured OAuth2 provider.

---

### GET /auth/oauth2/callback?code=...&state=...

Exchanges the authorization code for a local JWT.

**Response 200**
```json
{ "token": "<jwt>", "user": { ... } }
```

## Running Tests

```bash
cd <repo-root>
python3 -m pytest services/authentication/tests/ -v
```
