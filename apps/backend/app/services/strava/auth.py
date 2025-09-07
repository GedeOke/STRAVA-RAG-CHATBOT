import time
import requests
from typing import Dict
from ...settings import (
    STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET,
    STRAVA_ACCESS_TOKEN, STRAVA_REFRESH_TOKEN,
)

TOKEN_URL = "https://www.strava.com/oauth/token"

# simple in-memory token store (nanti bisa diganti DB)
_token: Dict[str, str | int] = {
    "access_token": STRAVA_ACCESS_TOKEN,
    "refresh_token": STRAVA_REFRESH_TOKEN,
    "expires_at": 0,  # force refresh on first call if you want
}

def set_tokens(access_token: str, refresh_token: str, expires_at: int) -> None:
    _token["access_token"] = access_token
    _token["refresh_token"] = refresh_token
    _token["expires_at"] = expires_at

def refresh_if_needed() -> None:
    """Refresh access token if near/after expiry."""
    # give 30s margin
    if not _token["access_token"] or time.time() > int(_token.get("expires_at", 0)) - 30:
        resp = requests.post(TOKEN_URL, data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": _token["refresh_token"],
        })
        resp.raise_for_status()
        data = resp.json()
        set_tokens(data["access_token"], data["refresh_token"], data["expires_at"])

def auth_headers() -> Dict[str, str]:
    refresh_if_needed()
    return {"Authorization": f"Bearer {_token['access_token']}"}
