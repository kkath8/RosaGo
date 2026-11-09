"""Admin-only authentication. No User cookie, store or provider global logout."""
from contextlib import contextmanager
from functools import wraps

from flask import current_app, g, make_response, redirect, session, url_for

from normal_auth_flask import (NormalAuthDependencies, NormalAuthEntryError,
                               SessionEstablishmentError, LocalLogoutError)
from normal_auth_coordinator import (NormalAuthCoordinator, SupabaseAdapters,
                                    AuthenticationRequired, SessionBusy, ClientUnavailable,
                                    VerifiedLoginCredentials)
from normal_auth_store import NormalAuthStore
from session_realms import AdminBrowserSession, rotate_admin_browser, SessionStorageUnavailable


def init_admin_auth(app, url, public_key):
    if 'rosago_shared_sessions' in app.extensions:
        from shared_session_runtime import session_model
        store = session_model(app, 'admin', 'auth')
    else:
        store = NormalAuthStore()
    from shared_session_runtime import auth_adapters
    adapters = auth_adapters(app,url,public_key)
    from shared_session_runtime import provider_checker
    coordinator = NormalAuthCoordinator(store, refresh_transport=adapters.refresh,
        client_factory=adapters.database_client, issuer=adapters.issuer, realm='admin',
        provider_session_check=provider_checker(app))
    app.extensions['rosago_admin_auth'] = NormalAuthDependencies(store, adapters, coordinator)


def get_admin_auth_dependencies():
    return current_app.extensions['rosago_admin_auth']


def verify_admin_candidate(credentials):
    """Membership before installation, with sanitized construction/cleanup errors."""
    from admin_authorization_service import is_current_admin, AdminAuthorizationError
    from normal_auth_coordinator import AuthenticatedContext
    try:
        with get_admin_auth_dependencies().adapters.database_client(credentials.access_token) as client:
            candidate = AuthenticatedContext('', credentials.user_id, credentials.user_email, client, 'admin')
            allowed = is_current_admin(candidate)
    except Exception:
        pass
    else:
        return allowed
    raise AdminAuthorizationError() from None


def read_admin_session_id():
    if not isinstance(session, AdminBrowserSession):
        return None
    handle = session.get('auth_session_id')
    return handle if type(handle) is str and handle else None


def clear_admin_auth_authority():
    if isinstance(session, AdminBrowserSession):
        session.pop('auth_session_id', None)


def establish_admin_session(credentials):
    import time
    if (type(credentials) is not VerifiedLoginCredentials or
            credentials.access_expires_at <= time.time() or
            not isinstance(session, AdminBrowserSession)):
        raise SessionEstablishmentError()
    dependencies = get_admin_auth_dependencies()
    from redis_session_flask import shared_interface, finish_login
    if shared_interface():
        return finish_login(credentials)
    old = read_admin_session_id()
    new = None
    try:
        new = dependencies.store.create(user_id=credentials.user_id, user_email=credentials.user_email,
            access_token=credentials.access_token, refresh_token=credentials.refresh_token,
            access_expires_at=credentials.access_expires_at, session_id=credentials.session_id)
        rotate_admin_browser(new)
    except BaseException as error:
        if new:
            dependencies.store.revoke(new)
        if not isinstance(error, Exception):
            raise
    else:
        if old:
            dependencies.store.revoke(old)
        return new
    raise SessionEstablishmentError() from None


def logout_admin_session():
    from redis_session_flask import shared_interface, shared_logout
    if shared_interface():
        if not isinstance(session, AdminBrowserSession):
            raise LocalLogoutError()
        return shared_logout()
    try:
        handle = read_admin_session_id()
        if handle:
            get_admin_auth_dependencies().store.revoke(handle)
        current_app.session_interface.store.revoke(session.handle)
        session.clear()
        session.delete_cookie = True
    except Exception:
        raise LocalLogoutError() from None


@contextmanager
def admin_authenticated():
    handle = read_admin_session_id()
    if handle is None:
        raise NormalAuthEntryError('unauthenticated')
    # Catch only context entry failures, never errors from the view body.
    from contextlib import ExitStack
    with ExitStack() as stack:
        try:
            auth = stack.enter_context(get_admin_auth_dependencies().coordinator.authenticated(handle))
        except AuthenticationRequired:
            failure = NormalAuthEntryError('unauthenticated')
        except SessionBusy:
            failure = NormalAuthEntryError('busy')
        except (ClientUnavailable,SessionStorageUnavailable):
            failure = NormalAuthEntryError('unavailable')
        else:
            absent = object()
            previous = g.get('admin_auth', absent)
            g.admin_auth = auth
            try:
                yield auth
            finally:
                if previous is absent:
                    g.pop('admin_auth', None)
                else:
                    g.admin_auth = previous
            return
    raise failure from None


def admin_login_required(view=None, *, login_endpoint='admin.login'):
    if view is None:
        return lambda handler: admin_login_required(handler, login_endpoint=login_endpoint)
    @wraps(view)
    def wrapped(*args, **kwargs):
        from contextlib import ExitStack
        with ExitStack() as stack:
            try:
                stack.enter_context(admin_authenticated())
            except NormalAuthEntryError as error:
                if error.may_clear_authority:
                    clear_admin_auth_authority()
                    return redirect(url_for(login_endpoint, login_required='1'))
                response = make_response('Authentication is temporarily unavailable. Please try again.', 503)
                response.headers['Retry-After'] = '1'
                return response
            return view(*args, **kwargs)
    return wrapped
