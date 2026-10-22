"""PKCE recovery request adapter with caller-owned HTTP transport.

The caller supplies server-side configuration and an HTTP client. This module
does not load environment variables, create clients, retry, or send on import.
Tests must inject a mock transport. Never log request headers/bodies or responses.
"""
import re
from urllib.parse import urlsplit

import httpx

from recovery_diagnostics import recovery_diagnostic


RECOVERY_REDIRECT_TO = "http://127.0.0.1:5000/auth/reset-callback"


class RecoveryTransportError(Exception):
    """Safe failure category without provider response or credential details."""


class RecoveryRequestRejected(RecoveryTransportError):
    """Provider rejection: callers should preserve account-enumeration protection."""


def send_pkce_recovery(email, code_challenge, *, supabase_url, supabase_key, client):
    """Send only the public challenge, never the verifier, through a caller client.

    The supplied client must not enable sensitive HTTP tracing. Its lifecycle
    belongs to the caller. No response body is returned to a future route.
    """
    if not isinstance(code_challenge, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", code_challenge):
        raise ValueError("Invalid PKCE S256 challenge format.")
    if not isinstance(email, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Invalid recovery email format.")
    if not isinstance(supabase_key, str) or not supabase_key.strip():
        raise ValueError("Supabase recovery configuration is missing.")
    # Accept only a configured HTTPS origin, never a browser-supplied URL.
    try:
        origin = urlsplit(supabase_url)
        valid_origin = (
            origin.scheme == "https" and origin.hostname
            and not origin.username and not origin.password
            and origin.path in ("", "/") and not origin.query and not origin.fragment
        )
    except (TypeError, ValueError):
        valid_origin = False
    if not valid_origin:
        raise ValueError("Invalid Supabase recovery origin.")
    try:
        response = client.post(
            supabase_url.rstrip("/") + "/auth/v1/recover",
            params={"redirect_to": RECOVERY_REDIRECT_TO},
            headers={"apikey": supabase_key},
            json={
                "email": email,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            },
            timeout=10.0,
            follow_redirects=False,
        )
    except httpx.TimeoutException:
        recovery_diagnostic("RECOVERY_TRANSPORT_TIMEOUT")
        raise RecoveryTransportError("Password recovery request could not be completed.") from None
    except httpx.RequestError:
        recovery_diagnostic("RECOVERY_TRANSPORT_NETWORK_ERROR")
        raise RecoveryTransportError("Password recovery request could not be completed.") from None
    if not 200 <= response.status_code < 300:
        # Fixed labels only. Never pass response/request objects or exception text.
        categories = {
            400: "RECOVERY_TRANSPORT_HTTP_400",
            401: "RECOVERY_TRANSPORT_HTTP_401",
            403: "RECOVERY_TRANSPORT_HTTP_403",
            404: "RECOVERY_TRANSPORT_HTTP_404",
            409: "RECOVERY_TRANSPORT_HTTP_409",
            422: "RECOVERY_TRANSPORT_HTTP_422",
            429: "RECOVERY_TRANSPORT_HTTP_429",
        }
        category = ("RECOVERY_TRANSPORT_HTTP_5XX" if 500 <= response.status_code < 600
                    else categories.get(response.status_code, "RECOVERY_TRANSPORT_HTTP_OTHER"))
        recovery_diagnostic(category)
        raise RecoveryRequestRejected("Password recovery request was not accepted.")
