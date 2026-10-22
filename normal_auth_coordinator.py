"""Isolated normal-auth coordination used through normal_auth_flask.

PROCESS-LOCAL DEVELOPMENT ONLY. Dependencies are injectable for offline tests.
Only normal-store handles are accepted; no cookies, request identity fields,
recovery stores, or browser-provided tokens/claims are accepted by the resolver.
The store must have been populated with verified NORMAL sign-in credentials.

Activity means successful resolution and request-client construction, not a
successful database operation. Invalid/busy/failed resolution never touches it.
The returned context is scoped to a with-block; do not retain its client.
Revocation cannot recall an already-issued context or an in-flight HTTP request.
"""
import base64
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
import json
import math
import secrets
import time
from urllib.parse import urlsplit

import httpx
from supabase import ClientOptions, create_client
from supabase_auth.errors import AuthApiError, AuthInvalidJwtError


class AuthenticationRequired(Exception):
    def __init__(self):
        super().__init__('Normal authentication required.')


class SessionBusy(Exception):
    def __init__(self):
        super().__init__('Normal authentication is busy; retry resolution later.')


class ClientUnavailable(Exception):
    def __init__(self):
        super().__init__('Authenticated client unavailable.')


class PasswordLoginError(Exception):
    """Fixed public classification only; never retain provider exceptions."""
    def __init__(self, reason):
        messages = {
            'invalid_credentials': 'Invalid email or password.',
            'unconfirmed_email': 'Email confirmation required.',
            'throttled': 'Password login is temporarily rate limited.',
            'service_failure': 'Password login service unavailable.',
            'invalid_result': 'Password login could not be verified.',
        }
        self.reason = reason if reason in messages else 'service_failure'
        super().__init__(messages[self.reason])


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedLoginCredentials:
    """Approved server-only input for store.create; never serialize.

    Expiry is checked before return; the eventual caller must check it again
    before storage if any intervening work can delay session creation.
    """
    user_id: str
    user_email: str
    access_token: str
    refresh_token: str
    access_expires_at: float
    session_id: str

    def __repr__(self):
        return '<VerifiedLoginCredentials redacted>'


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedRefresh:
    """Trusted transport result, never construct from request JSON.

    claims must come from SDK get_claims verification, not local JWT decoding.
    user_id/email come from get_user; response/session IDs are checked separately.
    """
    user_id: str
    user_email: str
    response_user_id: str
    session_user_id: str
    access_token: str
    refresh_token: str
    expires_at: float
    claims: dict

    def __repr__(self):
        return '<VerifiedRefresh redacted>'


@dataclass(frozen=True, slots=True, repr=False)
class AuthenticatedContext:
    auth_session_id: str
    user_id: str
    user_email: str
    client: object

    def __repr__(self):
        return '<AuthenticatedContext redacted>'


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _text(value):
    return type(value) is str and bool(value.strip())


def _normal_claims(claims, issuer):
    """Shared password-only claims shape/policy, after SDK verification.

    Identity binding and effective expiry remain the caller's responsibility.
    """
    if (not isinstance(claims, dict)
            or not _text(claims.get('sub')) or not _text(claims.get('session_id'))
            or claims.get('iss') != issuer or claims.get('aud') != 'authenticated'
            or claims.get('role') != 'authenticated' or not _number(claims.get('exp'))):
        return False
    methods = claims.get('amr')
    return (isinstance(methods, list) and bool(methods)
            and all(isinstance(method, dict) and method.get('method') == 'password'
                    and type(method.get('timestamp')) is int for method in methods))


def _configuration(url, key):
    # Classification only: Supabase validates the public key on actual requests.
    # Never accept a privileged secret/service-role key in either adapter.
    valid = False
    try:
        parsed = urlsplit(url)
        valid = (type(url) is str and parsed.scheme == 'https' and parsed.hostname
                 and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment and parsed.path in ('', '/'))
        if not _text(key):
            valid = False
        elif not key.startswith('sb_publishable_'):
            parts = key.split('.')
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
            valid = valid and len(parts) == 3 and isinstance(payload, dict) and payload.get('role') == 'anon'
    except Exception:
        valid = False
    if not valid:
        raise ValueError('Invalid normal-auth public configuration.') from None
    return url.rstrip('/'), key


class SupabaseAdapters:
    """Request-owned HTTP resources, no global authenticated SDK instances.

    refresh() may contact Auth, never application tables. database_client()
    constructs a client only; it does not query any table or restore an SDK
    session (set_session can refresh implicitly, so it is deliberately unused).
    """
    def __init__(self, url, public_key, *, sdk_factory=create_client,
                 http_factory=httpx.Client, clock=time.time):
        self._url, self._key = _configuration(url, public_key)
        self.issuer = self._url + '/auth/v1'
        self._sdk_factory = sdk_factory
        self._http_factory = http_factory
        self._clock = clock

    @contextmanager
    def _client(self, access_token=None):
        with self._http_factory(timeout=20, follow_redirects=False, trust_env=False) as http:
            headers = {} if access_token is None else {'Authorization': 'Bearer ' + access_token}
            client = self._sdk_factory(self._url, self._key, options=ClientOptions(
                headers=headers, persist_session=False, auto_refresh_token=False,
                httpx_client=http, schema='public'))
            # Supabase subclients share this owned HTTP client; it closes on exit.
            yield client

    def password_login(self, email, password):
        """Verify password sign-in without creating store or browser authority.

        All ordinary failures are sanitized after owned-resource cleanup.
        Shutdown/cancellation signals retain their normal propagation behavior.
        """
        stage = 'construction'
        reason = 'service_failure'
        try:
            if not _text(email) or not _text(password):
                raise PasswordLoginError('invalid_credentials')
            with self._client() as client:
                stage = 'sign_in'
                response = client.auth.sign_in_with_password({'email': email, 'password': password})
                stage = 'verification'
                session = getattr(response, 'session', None)
                response_user = getattr(response, 'user', None)
                session_user = getattr(session, 'user', None)
                access = getattr(session, 'access_token', None)
                refresh = getattr(session, 'refresh_token', None)
                expires = getattr(session, 'expires_at', None)
                response_id = getattr(response_user, 'id', None)
                session_user_id = getattr(session_user, 'id', None)
                if (session is None or response_user is None or session_user is None
                        or not _text(access) or not _text(refresh)):
                    raise PasswordLoginError('invalid_result')
                verified = client.auth.get_claims(access)
                claims = verified.get('claims') if isinstance(verified, dict) else None
                confirmed = getattr(client.auth.get_user(access), 'user', None)
                user_id = getattr(confirmed, 'id', None)
                user_email = getattr(confirmed, 'email', None)
                if (not _text(user_id) or not _text(user_email)
                        or not _normal_claims(claims, self.issuer)
                        or user_id != response_id or user_id != session_user_id
                        or user_id != claims['sub'] or not _number(expires)):
                    raise PasswordLoginError('invalid_result')
                if not getattr(confirmed, 'email_confirmed_at', None):
                    raise PasswordLoginError('unconfirmed_email')
                approved = VerifiedLoginCredentials(
                    user_id, user_email, access, refresh, min(expires, claims['exp']),
                    claims['session_id'])
                stage = 'cleanup'
            # Cleanup can take time: check immediately before returning approval.
            if approved.access_expires_at <= self._clock():
                raise PasswordLoginError('invalid_result')
            return approved
        except PasswordLoginError as error:
            reason = error.reason
        except AuthInvalidJwtError:
            reason = 'invalid_result'
        except AuthApiError as error:
            if stage in ('sign_in', 'verification'):
                if error.status == 429:
                    reason = 'throttled'
                elif stage == 'sign_in' and error.code == 'invalid_credentials':
                    reason = 'invalid_credentials'
                elif stage == 'sign_in' and error.code == 'email_not_confirmed':
                    reason = 'unconfirmed_email'
                elif stage == 'verification' and error.status in (400, 401, 403):
                    reason = 'invalid_result'
        except Exception:
            pass
        # Raising outside all handlers discards sensitive __context__/__cause__.
        raise PasswordLoginError(reason) from None

    def refresh(self, refresh_token):
        try:
            if not _text(refresh_token):
                raise AuthenticationRequired()
            with self._client() as client:
                result = client.auth.refresh_session(refresh_token)
                session, user = result.session, result.user
                if not session or not user or not session.user or not _text(session.access_token):
                    raise AuthenticationRequired()
                verified = client.auth.get_claims(session.access_token)
                claims = verified.get('claims') if isinstance(verified, dict) else None
                if not isinstance(claims, dict) or not claims:
                    raise AuthenticationRequired()
                confirmed = client.auth.get_user(session.access_token).user
                if not confirmed or not confirmed.email_confirmed_at:
                    raise AuthenticationRequired()
                return VerifiedRefresh(
                    confirmed.id, confirmed.email, user.id, session.user.id,
                    session.access_token, session.refresh_token, session.expires_at,
                    claims)
        except Exception:
            pass
        # Cleanup has finished; do not retain sensitive SDK exceptions in context.
        raise AuthenticationRequired() from None

    @contextmanager
    def database_client(self, access_token):
        if not _text(access_token):
            raise ClientUnavailable()
        with self._client(access_token) as client:
            yield client


class NormalAuthCoordinator:
    def __init__(self, store, *, refresh_transport, client_factory, issuer,
                 clock=time.time, refresh_seconds=60):
        if not _number(refresh_seconds) or refresh_seconds < 0 or not _text(issuer):
            raise ValueError('Invalid normal-auth coordinator configuration.')
        self._store = store
        self._refresh = refresh_transport
        self._clients = client_factory
        self._issuer = issuer
        self._clock = clock
        self._threshold = refresh_seconds

    def _fresh(self, record):
        return record.access_expires_at > self._clock() + self._threshold

    def _validate(self, result, record):
        if not isinstance(result, VerifiedRefresh):
            raise AuthenticationRequired()
        claims = result.claims
        if (not _normal_claims(claims, self._issuer)
                or not all(_text(value) for value in (result.user_id, result.user_email,
                    result.access_token, result.refresh_token))
                or result.user_id != record.user_id
                or result.response_user_id != record.user_id
                or result.session_user_id != record.user_id
                or claims.get('sub') != record.user_id
                or claims.get('session_id') != record.session_id
                or not _number(result.expires_at) or not _number(claims.get('exp'))
                or min(result.expires_at, claims['exp']) <= self._clock()):
            raise AuthenticationRequired()
        return min(result.expires_at, claims['exp'])

    def _resolve(self, handle):
        record = self._store.resolve(handle)
        if record is None:
            raise AuthenticationRequired()
        if self._fresh(record):
            return record
        reservation = self._store.reserve_refresh(handle)
        if reservation is None:
            if self._store.resolve(handle) is None:
                raise AuthenticationRequired()
            raise SessionBusy()
        lease, latest = reservation
        try:
            # Another refresh might have completed before this reservation.
            if self._fresh(latest):
                return latest
            if not _text(latest.refresh_token):
                raise AuthenticationRequired()
            result = self._refresh(latest.refresh_token)
            expires = self._validate(result, latest)
            if not self._store.replace_credentials(handle, lease,
                    user_id=result.user_id, user_email=result.user_email,
                    access_token=result.access_token, refresh_token=result.refresh_token,
                    access_expires_at=expires, session_id=latest.session_id):
                raise AuthenticationRequired()
            current = self._store.resolve(handle)
            if current is None:
                raise AuthenticationRequired()
            return current
        except BaseException as error:
            # A refresh may already have consumed the token. Revoke only our
            # still-reserved generation; never damage a newer worker's result.
            self._store.revoke_refresh(handle, lease)
            # Preserve shutdown/cancellation semantics; finally still releases
            # the reservation before the original signal reaches the caller.
            if not isinstance(error, Exception):
                raise
        finally:
            self._store.release_refresh(handle, lease)
        # Raise outside the handler so sensitive transport errors are not retained
        # in __context__; `from None` alone only hides their formatted traceback.
        raise AuthenticationRequired() from None

    @contextmanager
    def authenticated(self, auth_session_id):
        """Yield a request-scoped immutable context; caller must use with.

        Busy callers receive a transient retry response through the Flask
        integration, not an automatic logout. No polling, global network lock,
        automatic write retry, or concurrent duplicate refresh is performed.
        """
        record = self._resolve(auth_session_id)
        with ExitStack() as stack:
            try:
                client = stack.enter_context(self._clients(record.access_token))
            except Exception:
                pass
            else:
                if (record.access_expires_at <= self._clock()
                        or not self._store.touch(auth_session_id, expected_generation=record.generation)):
                    if self._store.resolve(auth_session_id) is None:
                        raise AuthenticationRequired()
                    raise SessionBusy()
                yield AuthenticatedContext(auth_session_id, record.user_id, record.user_email, client)
                return
        # Finish cleanup and leave the handler before raising, so sensitive
        # construction failures are not retained in the public __context__.
        raise ClientUnavailable() from None

    def validate_csrf(self, auth_session_id, supplied):
        """Server-only comparison, without exposing the secret or touching activity."""
        record = self._store.resolve(auth_session_id)
        return (record is not None and type(supplied) is str
                and secrets.compare_digest(record.csrf.encode(), supplied.encode()))
