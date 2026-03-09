"""
oauth.py – OAuth2 integration for third-party authentication providers.

Implements the Authorization Code Flow:
  1. GET  /auth/oauth2/authorize  -> redirect user to provider
  2. GET  /auth/oauth2/callback   -> exchange code for tokens, return JWT
"""

from __future__ import annotations

import secrets
import urllib.parse
from typing import Optional

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, session

from .models import UserProfileModel

oauth_bp = Blueprint("oauth", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_authorize_url(state: str) -> str:
    """Construct the provider authorization URL."""
    cfg = current_app.config
    params = {
        "client_id": cfg["OAUTH2_CLIENT_ID"],
        "redirect_uri": cfg["OAUTH2_REDIRECT_URI"],
        "response_type": "code",
        "scope": cfg["OAUTH2_SCOPES"],
        "state": state,
        "access_type": "online",
    }
    return cfg["OAUTH2_AUTHORIZE_URL"] + "?" + urllib.parse.urlencode(params)


def _exchange_code_for_tokens(code: str) -> dict:
    """Exchange an authorization code for provider access/id tokens."""
    cfg = current_app.config
    response = requests.post(
        cfg["OAUTH2_TOKEN_URL"],
        data={
            "code": code,
            "client_id": cfg["OAUTH2_CLIENT_ID"],
            "client_secret": cfg["OAUTH2_CLIENT_SECRET"],
            "redirect_uri": cfg["OAUTH2_REDIRECT_URI"],
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _fetch_userinfo(access_token: str) -> dict:
    """Retrieve user profile information from the provider."""
    cfg = current_app.config
    response = requests.get(
        cfg["OAUTH2_USERINFO_URL"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _get_or_create_user(
    provider: str, userinfo: dict
) -> UserProfileModel:
    """Return an existing UserProfileModel or create one from OAuth2 userinfo."""
    import uuid

    subject = userinfo.get("sub", "")
    email = userinfo.get("email", "")
    name = userinfo.get("name", email.split("@")[0] if email else subject)

    user = UserProfileModel.get_by_oauth(provider, subject)
    if user is None:
        user = UserProfileModel.create_oauth_user(
            user_id=str(uuid.uuid4()),
            username=name,
            email=email,
            oauth_provider=provider,
            oauth_subject=subject,
        )
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@oauth_bp.route("/auth/oauth2/authorize")
def authorize():
    """Redirect the user to the OAuth2 provider's authorization page.

    Returns
    -------
    302 Redirect  -> provider login page
    """
    state = secrets.token_urlsafe(32)
    session["oauth2_state"] = state
    return redirect(_build_authorize_url(state))


@oauth_bp.route("/auth/oauth2/callback")
def callback():
    """Handle the provider redirect, issue a local JWT.

    Returns
    -------
    200 JSON  {"token": "<jwt>", "user": {...}}
    400 JSON  on state mismatch or missing code
    502 JSON  on provider communication failure
    """
    # CSRF / state validation
    state = request.args.get("state", "")
    if not state or state != session.pop("oauth2_state", None):
        return jsonify({"error": "Invalid or missing OAuth2 state parameter"}), 400

    code = request.args.get("code", "")
    if not code:
        return jsonify({"error": "Authorization code not provided"}), 400

    try:
        token_data = _exchange_code_for_tokens(code)
        access_token = token_data.get("access_token", "")
        userinfo = _fetch_userinfo(access_token)
    except requests.HTTPError as exc:
        current_app.logger.error("OAuth2 provider error: %s", exc)
        return jsonify({"error": "Failed to communicate with OAuth2 provider"}), 502
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.error("Unexpected OAuth2 error: %s", exc)
        return jsonify({"error": "OAuth2 authentication failed"}), 502

    # Determine provider name from the token URL host
    provider = urllib.parse.urlparse(
        current_app.config["OAUTH2_TOKEN_URL"]
    ).hostname or "oauth2"

    user = _get_or_create_user(provider, userinfo)

    # Issue a local JWT for the authenticated user
    from .authentication import generate_jwt_token  # avoid circular import at module load

    jwt_token = generate_jwt_token(user)
    return jsonify({"token": jwt_token, "user": user.to_dict()}), 200
