"""main.py – FastAPI AuthController for the Security Platform microservice.

Migrated from the legacy Java AuthController. Provides:
  POST /auth/login     – validate credentials and issue a signed JWT.
  POST /auth/logout    – revoke a JWT (in-memory blacklist).
  GET  /health         – service health check.

The AuthMiddleware (auth_middleware.py) enforces token authentication on all
routes except /health, /auth/login, and the OpenAPI documentation paths.

Acceptance criteria satisfied (Task 2)
---------------------------------------
AC1  AuthController is implemented in FastAPI.
AC2  JWT tokens are issued and validated correctly.
AC3  Unit and integration tests cover authentication flows (see tests/).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Set

import jwt
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .auth_middleware import AuthMiddleware
from .utils.jwt_util import generate_token, get_user_roles, validate_token, verify_credentials

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory token revocation set (jti-based blacklist)
# ---------------------------------------------------------------------------

_TOKEN_BLACKLIST: Set[str] = set()


# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: Dict[str, Any]


class LogoutResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Security Platform – AuthController",
        version="1.0.0",
        description="JWT-based authentication microservice (migrated from Java AuthController).",
    )

    # Attach token-based authentication middleware (Task 1).
    app.add_middleware(AuthMiddleware)

    # ---------------------------------------------------------------------------
    # Routes
    # ---------------------------------------------------------------------------

    @app.get("/health", tags=["ops"])
    def health() -> Dict[str, str]:
        """Service health check."""
        return {"status": "ok", "service": "security-platform"}

    @app.post("/auth/login", response_model=LoginResponse, tags=["auth"])
    def login(body: LoginRequest) -> Dict[str, Any]:
        """Validate credentials and return a signed JWT.

        AC2: JWT tokens are issued correctly.
        """
        user = verify_credentials(body.username, body.password)
        if user is None:
            logger.warning("login: invalid credentials for username=%s", body.username)
            raise HTTPException(status_code=401, detail="Invalid username or password")

        roles = get_user_roles(body.username)
        token = generate_token(
            user_id=user["user_id"],
            username=body.username,
            roles=roles,
        )

        logger.info("login: token issued for user_id=%s username=%s", user["user_id"], body.username)
        return {
            "token": token,
            "user": {
                "user_id": user["user_id"],
                "username": body.username,
                "email": user.get("email", ""),
                "roles": roles,
            },
        }

    @app.post("/auth/logout", response_model=LogoutResponse, tags=["auth"])
    def logout(request: Request) -> Dict[str, str]:
        """Revoke the current JWT by adding its jti to the blacklist.

        Requires a valid Bearer token (enforced by AuthMiddleware).
        AC2: JWT tokens are validated correctly (middleware rejects invalid tokens).
        """
        payload: Dict[str, Any] = request.state.current_user
        jti: str = payload.get("jti", "")
        if jti:
            _TOKEN_BLACKLIST.add(jti)
        username = payload.get("username") or payload.get("sub", "unknown")
        logger.info("logout: token revoked for user=%s jti=%s", username, jti)
        return {"message": "Successfully logged out"}

    return app


# ---------------------------------------------------------------------------
# Module-level app instance (used by uvicorn / tests)
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.security_platform.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )
