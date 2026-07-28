"""Server-side verification of LINE LIFF OpenID Connect ID tokens."""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"


class LineLoginError(ValueError):
    """An ID token could not be accepted as a LINE identity."""


class LineLoginUnavailable(RuntimeError):
    """LINE verification could not be reached safely."""


def verify_id_token(id_token: str, channel_id: str, *, timeout: float = 5.0) -> dict:
    """Return only identity data from LINE's successful verification response."""

    if not channel_id:
        raise LineLoginUnavailable("LINE Login is not configured")
    if not isinstance(id_token, str) or not 20 <= len(id_token) <= 10_000:
        raise LineLoginError("Invalid ID token")
    body = urlencode({"id_token": id_token, "client_id": channel_id}).encode("ascii")
    request = Request(VERIFY_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if 400 <= exc.code < 500:
            raise LineLoginError("LINE rejected the ID token") from exc
        raise LineLoginUnavailable("LINE verification failed") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LineLoginUnavailable("LINE verification is unavailable") from exc
    if payload.get("aud") != channel_id or not isinstance(payload.get("sub"), str) or not payload["sub"]:
        raise LineLoginError("LINE identity response is invalid")
    try:
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LineLoginError("LINE identity response is invalid") from exc
    if expires_at <= time.time() or payload.get("iss") != "https://access.line.me":
        raise LineLoginError("LINE ID token has expired or is invalid")
    return {
        "line_user_id": payload["sub"],
        "display_name": str(payload.get("name") or "").strip()[:200] or None,
        "picture_url": str(payload.get("picture") or "").strip()[:1_000] or None,
    }
