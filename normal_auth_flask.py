"""Flask normal-auth integration backed by a process-local development store."""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from enum import Enum
import time
from typing import Literal

from flask import current_app, g, session

from normal_auth_coordinator import (
    AuthenticationRequired, ClientUnavailable, NormalAuthCoordinator,
    SessionBusy, SupabaseAdapters, VerifiedLoginCredentials,
)
from normal_auth_store import NormalAuthStore


EXTENSION_KEY = 'rosago_normal_auth'


@dataclass(frozen=True, slots=True, repr=False)
class NormalAuthDependencies:
    store: NormalAuthStore
    adapters: SupabaseAdapters
    coordinator: NormalAuthCoordinator

    def __repr__(self):
        return '<NormalAuthDependencies>'


def init_normal_auth(app, url, public_key):
    """Register once per app; constructors create no user SDK/HTTP clients."""
    if EXTENSION_KEY in app.extensions:
        raise RuntimeError('Normal authentication is already initialized.')
    store = NormalAuthStore()
    adapters = SupabaseAdapters(url, public_key)
    coordinator = NormalAuthCoordinator(
        store, refresh_transport=adapters.refresh,
        client_factory=adapters.database_client, issuer=adapters.issuer)
    dependencies = NormalAuthDependencies(store, adapters, coordinator)
    app.extensions[EXTENSION_KEY] = dependencies
    return dependencies


def get_normal_auth_dependencies():
    return current_app.extensions[EXTENSION_KEY]


def read_auth_session_id():
    """Read a candidate only; cookie identity and recovery keys grant nothing."""
    handle = session.get('auth_session_id')
    return handle if type(handle) is str and handle.strip() else None


def clear_normal_auth_authority():
    """Explicit cookie cleanup only; does not revoke records or recovery state."""
    for key in ('auth_session_id', 'user_id', 'user_email'):
        session.pop(key, None)


class LocalLogoutError(Exception):
    def __init__(self):
        super().__init__('Local normal-auth logout could not be completed.')


def logout_normal_session():
    """Revoke locally before cookie cleanup; no coordinator or provider calls.

    Revocation is never rolled back if cookie mutation fails. Later cookie
    serialization/delivery cannot be atomic with this process-local store;
    a retained old cookie still points to revoked server-side authority.
    """
    try:
        handle = read_auth_session_id()
        if handle is not None:
            get_normal_auth_dependencies().store.revoke(handle)
        clear_normal_auth_authority()
        return
    except Exception:
        pass
    raise LocalLogoutError() from None


class SessionEstablishmentError(Exception):
    def __init__(self):
        super().__init__('Normal authentication session could not be established.')


def establish_normal_session(credentials, *, clock=time.time):
    """Install trusted password_login output; never perform sign-in here.

    This transaction covers in-request session mutations, not later cookie
    serialization/delivery. A Python result type is a server-side contract,
    not proof for objects reconstructed from browser input.
    """
    new_handle = None
    store = None
    previous = {}
    try:
        if type(credentials) is not VerifiedLoginCredentials:
            raise SessionEstablishmentError()
        store = get_normal_auth_dependencies().store
        old_handle = read_auth_session_id()
        keys = ('auth_session_id', 'user_id', 'user_email')
        previous = {key: session[key] for key in keys if key in session}
        if not credentials.access_expires_at > clock():
            raise SessionEstablishmentError()
        new_handle = store.create(
            user_id=credentials.user_id, user_email=credentials.user_email,
            access_token=credentials.access_token, refresh_token=credentials.refresh_token,
            access_expires_at=credentials.access_expires_at, session_id=credentials.session_id)
        session['auth_session_id'] = new_handle
        session.pop('user_id', None)
        session.pop('user_email', None)
        if old_handle is not None and old_handle != new_handle:
            store.revoke(old_handle)
        return new_handle
    except BaseException as error:
        if new_handle is not None:
            store.revoke(new_handle)
            # Restore just the original normal keys, including their absence.
            # A broken session backend may reject restoration too; the new
            # handle is already revoked and cannot grant authority in that case.
            for key in ('auth_session_id', 'user_id', 'user_email'):
                try:
                    if key in previous:
                        session[key] = previous[key]
                    else:
                        session.pop(key, None)
                except Exception:
                    pass
        if not isinstance(error, Exception):
            raise
    raise SessionEstablishmentError() from None


@dataclass(frozen=True, slots=True)
class AuthStateDecision:
    state: Literal['authenticated', 'unauthenticated', 'busy', 'unavailable']
    user_id: str | None = None
    user_email: str | None = None


class AuthRedirectDecision(Enum):
    REDIRECT_USER = 'redirect_user'
    SHOW_FORM = 'show_form'
    RETRYABLE_TEMPORARY = 'retryable_temporary'
    SERVICE_TEMPORARY = 'service_temporary'


def normal_auth_state():
    """Copy safe identity and close the client before returning a decision."""
    with ExitStack() as stack:
        try:
            auth = stack.enter_context(normal_authenticated())
        except NormalAuthEntryError as error:
            if error.may_clear_authority:
                clear_normal_auth_authority()
            decision = AuthStateDecision(error.kind)
        else:
            # Keep body/teardown outside the entry handler: bugs are not states.
            decision = AuthStateDecision('authenticated', auth.user_id, auth.user_email)
    return decision


def normal_auth_redirect_decision():
    """Auth-page action only; no response construction or redirects."""
    return {
        'authenticated': AuthRedirectDecision.REDIRECT_USER,
        'unauthenticated': AuthRedirectDecision.SHOW_FORM,
        'busy': AuthRedirectDecision.RETRYABLE_TEMPORARY,
        'unavailable': AuthRedirectDecision.SERVICE_TEMPORARY,
    }[normal_auth_state().state]


class NormalAuthEntryError(Exception):
    """Fixed classification for routes, never a provider exception.

    unauthenticated: login redirect/status false; cleanup is permitted.
    busy/unavailable: generic 503; retain authority and allow retry.
    This exception does not itself alter cookies or create HTTP responses.
    """
    def __init__(self, kind):
        messages = {
            'unauthenticated': 'Normal authentication required.',
            'busy': 'Authentication is busy; please retry.',
            'unavailable': 'Authentication service temporarily unavailable.',
        }
        self.kind = kind
        self.retryable = kind != 'unauthenticated'
        self.suggested_status = 503 if self.retryable else None
        self.may_clear_authority = not self.retryable
        super().__init__(messages[kind])


@contextmanager
def normal_authenticated():
    """Scope g.auth and the client to this operation, including eager rendering.

    Nested operations restore their still-active outer context. No client may
    escape the with-block for streaming, background work or later callbacks.
    Only entry errors are classified; body and teardown errors propagate.
    """
    handle = read_auth_session_id()
    if handle is None:
        raise NormalAuthEntryError('unauthenticated')
    with ExitStack() as stack:
        try:
            auth = stack.enter_context(
                get_normal_auth_dependencies().coordinator.authenticated(handle))
        except AuthenticationRequired:
            failure = NormalAuthEntryError('unauthenticated')
        except SessionBusy:
            failure = NormalAuthEntryError('busy')
        except ClientUnavailable:
            failure = NormalAuthEntryError('unavailable')
        else:
            absent = object()
            previous = g.get('auth', absent)
            g.auth = auth
            try:
                yield auth
            finally:
                if previous is absent:
                    g.pop('auth', None)
                else:
                    g.auth = previous
            return
    # Leave the handler before raising so provider causes/contexts cannot escape.
    raise failure from None
