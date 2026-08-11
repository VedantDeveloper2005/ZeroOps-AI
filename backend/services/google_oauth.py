"""
Google OAuth service.
Handles OAuth URL construction, token exchange, and profile retrieval.
"""

import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

try:
    from backend import config
except ImportError:
    import config

logger = logging.getLogger("zeroops.google_oauth")


def get_authorization_url(state: str, redirect_uri: str, code_challenge: str) -> str:
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config.GOOGLE_OAUTH_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def exchange_code_for_token(code: str, redirect_uri: str, code_verifier: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code != 200:
            logger.error("Google token exchange failed.")
            return None

        data = response.json()
        access_token = data.get("access_token")
        if not access_token:
            logger.error("Google token exchange did not return an access token.")
            return None
        return access_token


async def get_google_user(token: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            logger.error("Google user fetch failed: HTTP %s", response.status_code)
            return None
        return response.json()
