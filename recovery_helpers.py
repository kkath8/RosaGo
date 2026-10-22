"""Short-lived, process-local recovery grants for this development phase."""
import hashlib
import base64
import re
import secrets
import time
from dataclasses import dataclass
from threading import Lock

from recovery_diagnostics import recovery_diagnostic


RECOVERY_SECONDS = 600
RECOVERY_ERROR = "This password recovery link is invalid, expired, already used, or missing required information. Please request a new link."


def generate_pkce_verifier():
    """Return a 256-bit random, RFC 7636-compatible verifier. Server use only."""
    return secrets.token_urlsafe(32)


def pkce_s256_challenge(verifier):
    """Derive the public S256 challenge without exposing the verifier."""
    if not isinstance(verifier, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
        raise ValueError("Invalid PKCE verifier format.")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass(frozen=True, repr=False)
class PendingRecovery:
    """Server-only record: never serialize into cookies, HTML, URLs, or logs."""

    verifier: str
    created_at: float
    expires_at: float


class PendingRecoveries:
    """Development-only, single-process store; restart discards all requests.

    Use shared server-side storage with atomic consumption before multi-process
    production deployment. Only the opaque identifier may later enter a Flask
    session. Exchange must reserve(), then finalize() after success or release()
    after failure. Reservations prevent concurrent exchanges of one record.
    """

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._records = {}
        self._reserved = {}
        self._lock = Lock()

    def _prune(self, now):
        self._records = {
            key: record for key, record in self._records.items()
            if record.expires_at > now
        }
        self._reserved = {key: value for key, value in self._reserved.items() if key in self._records}

    def reserve(self, handle):
        """Return a server-only lease and record, or None if unavailable."""
        with self._lock:
            self._prune(self._clock())
            if not isinstance(handle, str) or handle not in self._records or handle in self._reserved:
                return None
            lease = secrets.token_urlsafe(32)
            self._reserved[handle] = lease
            return lease, self._records[handle]

    def release(self, handle, lease):
        with self._lock:
            self._prune(self._clock())
            if self._reserved.get(handle) == lease:
                self._reserved.pop(handle, None)

    def finalize(self, handle, lease):
        """Consume only a matching live reservation after a successful exchange."""
        with self._lock:
            self._prune(self._clock())
            if handle not in self._reserved or self._reserved[handle] != lease:
                return None
            self._reserved.pop(handle)
            return self._records.pop(handle, None)

    def create(self):
        with self._lock:
            now = self._clock()
            self._prune(now)
            handle = secrets.token_urlsafe(32)
            while handle in self._records:
                handle = secrets.token_urlsafe(32)
            self._records[handle] = PendingRecovery(
                verifier=generate_pkce_verifier(),
                created_at=now,
                expires_at=now + RECOVERY_SECONDS,
            )
            return handle

    def lookup(self, handle):
        with self._lock:
            self._prune(self._clock())
            return self._records.get(handle) if isinstance(handle, str) else None

    def consume(self, handle):
        """Atomically remove and return an unexpired record; replay returns None."""
        with self._lock:
            self._prune(self._clock())
            if isinstance(handle, str):
                self._reserved.pop(handle, None)
            return self._records.pop(handle, None) if isinstance(handle, str) else None


def recovery_expiry(claims, user, issuer, now):
    """Only trust claims returned by Supabase's get_claims, never decoded client data."""
    if not isinstance(claims, dict):
        recovery_diagnostic("RECOVERY_CLAIMS_REJECTED")
        return None
    if not user or not user.id or not user.email:
        recovery_diagnostic("RECOVERY_USER_VALIDATION_REJECTED")
        return None
    if claims.get("sub") != user.id:
        recovery_diagnostic("RECOVERY_SUBJECT_MISMATCH")
        return None
    if claims.get("iss") != issuer:
        recovery_diagnostic("RECOVERY_ISSUER_MISMATCH")
        return None
    if claims.get("aud") != "authenticated":
        recovery_diagnostic("RECOVERY_AUDIENCE_REJECTED")
        return None
    if not isinstance(claims.get("session_id"), str) or not claims["session_id"]:
        recovery_diagnostic("RECOVERY_SESSION_ID_MISSING")
        return None
    expires = claims.get("exp")
    if not isinstance(expires, (int, float)):
        recovery_diagnostic("RECOVERY_EXPIRY_INVALID")
        return None
    if expires <= now:
        recovery_diagnostic("RECOVERY_EXPIRED")
        return None
    methods = claims.get("amr", [])
    if not isinstance(methods, list):
        recovery_diagnostic("RECOVERY_VERIFIED_AMR_INVALID")
        recovery_diagnostic("RECOVERY_METHOD_REJECTED")
        return None
    # TEMPORARY: classify only server-verified methods using fixed labels.
    # Implicit Supabase email verification can use "otp" for multiple flows.
    # Neither that method nor a browser-provided type proves recovery by itself.
    if not methods:
        recovery_diagnostic("RECOVERY_VERIFIED_AMR_EMPTY")
    method_categories = {
        "otp": "RECOVERY_VERIFIED_AMR_OTP",
        "password": "RECOVERY_VERIFIED_AMR_PASSWORD",
        "recovery": "RECOVERY_VERIFIED_AMR_RECOVERY",
    }
    for method in methods:
        name = method.get("method") if isinstance(method, dict) else None
        category = method_categories.get(name) if isinstance(name, str) else None
        recovery_diagnostic(category or "RECOVERY_VERIFIED_AMR_OTHER")
    rejection = "RECOVERY_METHOD_REJECTED"
    for method in methods:
        if not isinstance(method, dict) or method.get("method") != "recovery":
            continue
        issued = method.get("timestamp")
        if isinstance(issued, (int, float)) and now - RECOVERY_SECONDS < issued <= now + 30:
            return min(expires, issued + RECOVERY_SECONDS, now + RECOVERY_SECONDS)
        rejection = "RECOVERY_EXPIRED" if isinstance(issued, (int, float)) and issued <= now - RECOVERY_SECONDS else "RECOVERY_TIMESTAMP_REJECTED"
    recovery_diagnostic(rejection)
    return None


@dataclass(frozen=True, repr=False)
class RecoveryGrant:
    user_id: str
    expires: float
    access_token: str
    csrf: str


class RecoveryGrants:
    """Development-only server memory. Never serialize records into cookies/logs.

    Shared server-side storage with atomic reservations is required before
    multi-process production. Restart discards credentials and grants.
    """
    def __init__(self):
        self._grants = {}
        self._used = {}
        self._busy = {}
        self._lock = Lock()

    def _prune(self, now):
        self._grants = {key: value for key, value in self._grants.items() if value.expires > now}
        self._busy = {key: value for key, value in self._busy.items() if key in self._grants}
        self._used = {key: expires for key, expires in self._used.items() if expires > now}

    def issue(self, user_id, recovery_session_id, expires, access_token):
        fingerprint = hashlib.sha256(recovery_session_id.encode()).hexdigest()
        with self._lock:
            now = time.time()
            self._prune(now)
            if expires <= now:
                recovery_diagnostic("RECOVERY_EXPIRED")
                return None
            if fingerprint in self._used:
                recovery_diagnostic("RECOVERY_REPLAY_REJECTED")
                return None
            handle = secrets.token_urlsafe(32)
            self._used[fingerprint] = now + RECOVERY_SECONDS + 30
            self._grants[handle] = RecoveryGrant(user_id, expires, access_token, secrets.token_urlsafe(32))
            return handle

    def valid(self, handle):
        with self._lock:
            self._prune(time.time())
            return isinstance(handle, str) and handle in self._grants

    def revoke(self, handle):
        with self._lock:
            if isinstance(handle, str):
                self._grants.pop(handle, None)
                self._busy.pop(handle, None)

    def csrf(self, handle):
        with self._lock:
            self._prune(time.time())
            record = self._grants.get(handle) if isinstance(handle, str) else None
            return record.csrf if record else None

    def reserve(self, handle):
        with self._lock:
            self._prune(time.time())
            if not isinstance(handle, str) or handle not in self._grants or handle in self._busy:
                return None
            lease = secrets.token_urlsafe(32)
            self._busy[handle] = lease
            return lease, self._grants[handle]

    def release(self, handle, lease):
        with self._lock:
            self._prune(time.time())
            if self._busy.get(handle) == lease:
                self._busy.pop(handle, None)
