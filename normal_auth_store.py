"""PROCESS-LOCAL DEVELOPMENT STORAGE for normal authentication only.

Not integrated with Flask. No network calls, token verification, or refresh
calls occur here. Callers must supply already-verified identity/credentials.
Never serialize records/reservations into cookies, logs, or browser responses.
Only the opaque handle may later enter the Flask cookie as auth_session_id.

Restart/reloader restart loses all sessions. Separate workers have separate
stores: production requires shared storage and atomic distributed coordination.
Lifecycle times use an injectable monotonic clock (process-relative seconds).
access_expires_at is separate Unix-time metadata, not a local session deadline.
"""
from dataclasses import dataclass, replace
import math
import secrets
from threading import Lock
import time


IDLE_SECONDS = 30 * 60
ABSOLUTE_SECONDS = 8 * 60 * 60


@dataclass(frozen=True, slots=True, repr=False)
class NormalAuthSession:
    user_id: str
    user_email: str
    access_token: str
    refresh_token: str
    access_expires_at: float
    session_id: str
    created_at: float
    last_activity_at: float
    generation: int
    revoked: bool
    csrf: str

    def __repr__(self):
        return '<NormalAuthSession redacted>'


@dataclass(frozen=True, slots=True, repr=False)
class RefreshReservation:
    nonce: str
    generation: int

    def __repr__(self):
        return '<RefreshReservation redacted>'


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _credentials_valid(user_id, user_email, access_token, refresh_token,
                       access_expires_at, session_id):
    return (all(type(value) is str and bool(value.strip()) for value in
                (user_id, user_email, access_token, refresh_token, session_id))
            and _finite_number(access_expires_at))


class NormalAuthStore:
    """Thread-safe, single-process store with explicit refresh coordination.

    resolve never touches activity. touch never extends absolute lifetime.
    Reserve, perform future network work OUTSIDE this store, then replace or
    release in a finally block. Reservations do not auto-expire independently:
    a stalled worker must not let a second refresh race a still-running first.
    Idle/absolute expiry and revocation invalidate reservations unconditionally.
    A snapshot already held by a caller cannot be erased by revocation; future
    integration must re-check lifecycle before authorizing subsequent work.
    """

    def __init__(self, *, idle_seconds=IDLE_SECONDS,
                 absolute_seconds=ABSOLUTE_SECONDS, clock=time.monotonic):
        if not all(_finite_number(value) and value > 0
                   for value in (idle_seconds, absolute_seconds)):
            raise ValueError('Invalid normal-session lifetime.')
        self._idle = idle_seconds
        self._absolute = absolute_seconds
        self._clock = clock
        self._records = {}
        self._busy = {}
        self._lock = Lock()

    def _prune(self, now):
        self._records = {
            key: record for key, record in self._records.items()
            if not record.revoked
            and now < record.last_activity_at + self._idle
            and now < record.created_at + self._absolute
        }
        self._busy = {key: value for key, value in self._busy.items()
                      if key in self._records}

    def _read(self, handle):
        return self._records.get(handle) if type(handle) is str else None

    def create(self, *, user_id, user_email, access_token, refresh_token,
               access_expires_at, session_id):
        if not _credentials_valid(user_id, user_email, access_token, refresh_token,
                                  access_expires_at, session_id):
            raise ValueError('Invalid normal-session credentials.')
        with self._lock:
            now = self._clock()
            self._prune(now)
            handle = secrets.token_urlsafe(32)
            while handle in self._records:
                handle = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            while csrf == handle:
                csrf = secrets.token_urlsafe(32)
            self._records[handle] = NormalAuthSession(
                user_id, user_email, access_token, refresh_token,
                access_expires_at, session_id, now, now, 0, False, csrf)
            return handle

    def resolve(self, handle):
        with self._lock:
            self._prune(self._clock())
            record = self._read(handle)
            # Copy even frozen records: deliberate object.__setattr__ on a
            # caller snapshot must not mutate the store's internal record.
            return replace(record) if record else None

    def touch(self, handle, *, expected_generation=None):
        with self._lock:
            now = self._clock()
            self._prune(now)
            record = self._read(handle)
            if (not record or (expected_generation is not None
                    and (record.generation != expected_generation or handle in self._busy))):
                return False
            self._records[handle] = replace(record, last_activity_at=now)
            return True

    def reserve_refresh(self, handle):
        """Return (opaque lease, credential snapshot), or None if unavailable."""
        with self._lock:
            self._prune(self._clock())
            record = self._read(handle)
            if not record or handle in self._busy:
                return None
            lease = RefreshReservation(secrets.token_urlsafe(32), record.generation)
            self._busy[handle] = lease
            return replace(lease), replace(record)

    def _matches(self, handle, lease, record):
        current = self._busy.get(handle) if type(handle) is str else None
        return (record is not None and type(lease) is RefreshReservation
                and current is not None and current == lease
                and record.generation == lease.generation)

    def replace_credentials(self, handle, lease, *, user_id, user_email,
                            access_token, refresh_token, access_expires_at,
                            session_id):
        """Commit one verified refresh atomically, consuming its reservation.

        Identity and Supabase session ID cannot change. Email may be updated
        from a newly verified Auth response. Does not touch activity/lifetimes.
        Failed replacement leaves a live matching lease for explicit release.
        """
        with self._lock:
            self._prune(self._clock())
            record = self._read(handle)
            if not self._matches(handle, lease, record):
                return False
            if (not _credentials_valid(user_id, user_email, access_token,
                                       refresh_token, access_expires_at, session_id)
                    or user_id != record.user_id or session_id != record.session_id):
                return False
            self._records[handle] = replace(
                record, user_email=user_email, access_token=access_token,
                refresh_token=refresh_token, access_expires_at=access_expires_at,
                generation=record.generation + 1)
            self._busy.pop(handle)
            return True

    def release_refresh(self, handle, lease):
        with self._lock:
            self._prune(self._clock())
            if not self._matches(handle, lease, self._read(handle)):
                return False
            self._busy.pop(handle)
            return True

    def revoke(self, handle):
        """Idempotent removal; no credentials/tombstones retained after revoke."""
        with self._lock:
            self._prune(self._clock())
            record = self._read(handle)
            if not record:
                return False
            # Explicit terminal state before deletion; stale snapshots are not
            # authority and cannot be submitted to recreate a removed record.
            self._records[handle] = replace(record, revoked=True)
            self._busy.pop(handle, None)
            self._records.pop(handle)
            return True

    def revoke_refresh(self, handle, lease):
        """Revoke only the still-reserved generation after an uncertain refresh.

        A late failing worker cannot delete credentials committed by a newer
        reservation. Revocation/expiry already performed remains authoritative.
        """
        with self._lock:
            self._prune(self._clock())
            if not self._matches(handle, lease, self._read(handle)):
                return False
            self._busy.pop(handle)
            self._records.pop(handle)
            return True
