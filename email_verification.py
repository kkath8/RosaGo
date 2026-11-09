"""Bounded pending signup state. Never stores passwords, OTPs or Auth tokens.

Like the existing auth/recovery stores, this store is process-local. A shared
atomic store is required before deployment across multiple workers.
"""
from dataclasses import dataclass, replace
import math
import secrets
from threading import Lock
import time

from supabase import ClientOptions, create_client
import httpx


@dataclass(frozen=True, repr=False)
class PendingEmail:
    email: str
    csrf: str
    expires: float
    resend_at: float
    verify_at: float = 0
    busy: bool = False
    verified: bool = False


class PendingEmailStore:
    def __init__(self, *, clock=time.monotonic, limit=1000):
        self.clock, self.limit = clock, limit
        self._records, self._email_resends = {}, {}
        self._lock = Lock()

    def _prune(self, now):
        self._records = {h:r for h,r in self._records.items() if r.expires > now}
        self._email_resends = {e:t for e,t in self._email_resends.items() if t > now}

    def create(self, email):
        with self._lock:
            now = self.clock()
            self._prune(now)
            if len(self._records) >= self.limit:
                return None
            handle = secrets.token_urlsafe(32)
            due = max(now + 60, self._email_resends.get(email.casefold(), 0))
            self._email_resends[email.casefold()] = due
            self._records[handle] = PendingEmail(email, secrets.token_urlsafe(32), now + 1800, due)
            return handle

    def get(self, handle):
        with self._lock:
            self._prune(self.clock())
            return self._records.get(handle) if type(handle) is str else None

    def seconds(self, record):
        return max(0, math.ceil(record.resend_at - self.clock()))

    def reserve(self, handle, action):
        with self._lock:
            now = self.clock()
            self._prune(now)
            record = self._records.get(handle)
            if record is None or record.verified:
                return None, 0
            due = (max(record.resend_at, self._email_resends.get(record.email.casefold(), 0))
                   if action == 'resend' else record.verify_at)
            if record.busy or due > now:
                return None, max(1, math.ceil(due - now))
            changes = {'busy':True}
            if action == 'resend':
                changes['resend_at'] = now + 60
                self._email_resends[record.email.casefold()] = now + 60
            else:
                changes['verify_at'] = now + 5
            self._records[handle] = replace(record, **changes)
            return record, 0

    def finish(self, handle, *, verified=False, resent=False, limited=False, uncertain=False):
        with self._lock:
            record = self._records.get(handle)
            if record is not None:
                changes = {'busy':bool(uncertain), 'verified':record.verified or verified}
                if resent or limited:
                    changes['resend_at'] = self.clock() + 60
                    self._email_resends[record.email.casefold()] = changes['resend_at']
                if limited:
                    changes['verify_at'] = self.clock() + 60
                self._records[handle] = replace(record, **changes)


class EmailVerificationService:
    def __init__(self, url, public_key, *, sdk_factory=create_client, http_factory=httpx.Client):
        self._url, self._key = url, public_key
        self._sdk_factory, self._http_factory = sdk_factory, http_factory

    def verify(self, email, token):
        # A fresh public-key client owns any temporary OTP session. No credentials
        # are copied into Flask cookies, normal-auth storage or shared SDK state.
        with self._http_factory(timeout=20, follow_redirects=False, trust_env=False) as http:
            client = self._sdk_factory(self._url, self._key, options=ClientOptions(
                persist_session=False, auto_refresh_token=False, httpx_client=http))
            response = client.auth.verify_otp({'email':email, 'token':token, 'type':'email'})
            user = getattr(response, 'user', None)
            return bool(user and getattr(user, 'email_confirmed_at', None)
                and type(getattr(user, 'email', None)) is str and user.email.casefold() == email.casefold())

    def resend(self, email):
        with self._http_factory(timeout=20, follow_redirects=False, trust_env=False) as http:
            client = self._sdk_factory(self._url, self._key, options=ClientOptions(
                persist_session=False, auto_refresh_token=False, httpx_client=http))
            client.auth.resend({'type':'signup', 'email':email})
