"""Independent browser realms. Memory backend: single-process LOCAL TESTING only."""
from copy import deepcopy
import re
import secrets
from threading import RLock
import time

from flask import request, session
from flask.sessions import SecureCookieSession, SecureCookieSessionInterface, SessionInterface


class SessionStorageUnavailable(RuntimeError):
    pass


def is_admin_path(path):
    return path == '/admin' or path.startswith('/admin/')


class LoginChallenges:
    """Bounded, purpose-bound, single-use challenges; never credential authority."""
    def __init__(self, *, clock=time.monotonic, capacity=4096):
        self.clock, self.capacity = clock, capacity
        self.records = {}
        self.attempts = {}
        self.lock = RLock()

    def _prune(self):
        now = self.clock()
        self.records = {k: v for k, v in self.records.items() if now < v[1]}

    def issue(self, realm):
        with self.lock:
            self._prune()
            if len(self.records) >= self.capacity:
                raise SessionStorageUnavailable('Login temporarily unavailable.')
            token = secrets.token_urlsafe(32)
            self.records[token] = (realm, self.clock() + 1800)
            return token

    def valid(self, realm, token, *, consume=False):
        with self.lock:
            self._prune()
            value = self.records.get(token) if type(token) is str else None
            if value is None or value[0] != realm:
                return False
            if consume:
                self.records.pop(token)
            return True

    def allow_attempt(self, realm, address):
        with self.lock:
            now = self.clock()
            self.attempts = {k: v for k, v in self.attempts.items() if now < v[0] + 60}
            key = (realm, address)
            if key not in self.attempts and len(self.attempts) >= self.capacity:
                return False
            started, count = self.attempts.get(key, (now, 0))
            self.attempts[key] = (started, count + 1)
            return count < 20


class AdminWebStore:
    """CAS web state, separate from bearer credentials and User state.

    Stale saves never recreate removed records or overwrite a newer snapshot.
    Auth lifetime is independently enforced by the credential store.
    """
    def __init__(self, *, clock=time.monotonic, capacity=4096):
        self.clock, self.capacity = clock, capacity
        self.records = {}
        self.lock = RLock()

    def _prune(self):
        now = self.clock()
        self.records = {k: v for k, v in self.records.items()
                        if now < v[2] and now < v[3] + 1800}

    def create(self, values):
        with self.lock:
            self._prune()
            if len(self.records) >= self.capacity:
                raise SessionStorageUnavailable('Admin sessions temporarily unavailable.')
            handle = secrets.token_urlsafe(32)
            now = self.clock()
            lifetime = 28800 if values.get('auth_session_id') else 1800
            self.records[handle] = (deepcopy(values), 0, now + lifetime, now)
            return handle

    def read(self, handle):
        with self.lock:
            self._prune()
            record = self.records.get(handle)
            if record is None:
                return None
            data, version, expires, _ = record
            self.records[handle] = (data, version, expires, self.clock())
            return deepcopy(data), version

    def save(self, handle, version, values):
        with self.lock:
            self._prune()
            old = self.records.get(handle)
            if old is None or old[1] != version:
                return False
            self.records[handle] = (deepcopy(values), version + 1, old[2], self.clock())
            return True

    def revoke(self, handle):
        with self.lock:
            self.records.pop(handle, None)


class AdminBrowserSession(SecureCookieSession):
    realm = 'admin'

    def __init__(self, values=None, *, handle=None, version=0, invalid=False):
        super().__init__(values)
        self.handle, self.version, self.invalid = handle, version, invalid
        self.issue_cookie = False
        self.delete_cookie = False


class RealmSessionInterface(SessionInterface):
    """Never mutate app cookie configuration while handling a request."""
    def __init__(self, web_store, *, secure=False):
        self.user = SecureCookieSessionInterface()
        self.store = web_store
        self.secure = secure
        self.cookie_name = '__Secure-rosago_admin_session' if secure else 'rosago_admin_session_dev'
        self.cookie_path = '/admin'

    def get_signing_serializer(self, app):
        return self.user.get_signing_serializer(app)

    def open_session(self, app, req):
        if not is_admin_path(req.path):
            return self.user.open_session(app, req)
        candidates = req.cookies.getlist(self.cookie_name)
        if len(candidates) > 1 or (candidates and not re.fullmatch(r'[A-Za-z0-9_-]{43}', candidates[0])):
            return AdminBrowserSession(invalid=True)
        handle = candidates[0] if candidates else None
        record = self.store.read(handle) if handle else None
        return (AdminBrowserSession(record[0], handle=handle, version=record[1])
                if record else AdminBrowserSession())

    def save_session(self, app, state, response):
        if not isinstance(state, AdminBrowserSession):
            return self.user.save_session(app, state, response)
        response.vary.add('Cookie')
        if state.invalid:
            return
        if state.delete_cookie:
            response.delete_cookie(self.cookie_name, path=self.cookie_path,
                                   secure=self.secure, httponly=True, samesite='Lax')
            return
        if not state.modified:
            return
        try:
            if state.handle is None:
                if not state:
                    return
                state.handle = self.store.create(dict(state))
                state.issue_cookie = True
            elif not self.store.save(state.handle, state.version, dict(state)):
                # The action may already have completed: never automatically retry.
                response.status_code = 409
                response.headers.pop('Location', None)
                response.set_data('Session state changed. Reload and verify the result before retrying.')
                response.headers['Cache-Control'] = 'private, no-store'
                return
        except RuntimeError:
            response.status_code = 503
            response.headers.pop('Location', None)
            response.set_data('Session storage is temporarily unavailable. Reload before retrying.')
            return
        if state.issue_cookie:
            response.set_cookie(self.cookie_name, state.handle, path=self.cookie_path,
                                secure=self.secure, httponly=True, samesite='Lax')


def rotate_admin_browser(auth_handle):
    interface = request.environ['rosago.realm_interface']
    old_handle = session.handle
    values = {'auth_session_id': auth_handle}
    new_handle = interface.store.create(values)
    try:
        session.clear()
        session.update(values)
        session.handle, session.version = new_handle, 0
        session.issue_cookie = True
    except BaseException:
        interface.store.revoke(new_handle)
        # Keep the old browser/server record authoritative even if a broken
        # request mapping cannot be restored. Never save partial state.
        session.invalid = True
        raise
    interface.store.revoke(old_handle)


def init_session_realms(app, *, mode='development', local_runtime=None):
    if mode not in ('development', 'redis-local', 'production'):
        raise RuntimeError('Invalid ROSAGO_AUTH_MODE.')
    # Shared adapters can be qualified locally. Production still requires a
    # separate infrastructure/failover/configuration readiness approval.
    if mode == 'production':
        raise RuntimeError('Production authentication requires a reviewed shared session backend; memory mode is local only.')
    if local_runtime is not None and mode != 'redis-local':
        raise RuntimeError('Injected shared runtime is local qualification only.')
    if app.config.get('APPLICATION_ROOT', '/') != '/':
        raise RuntimeError('Local session realms currently require a root-mounted app.')
    app.extensions['rosago_login_challenges'] = LoginChallenges()
    app.session_interface = RealmSessionInterface(AdminWebStore(), secure=False)
    if mode == 'redis-local':
        import os
        from redis_session_store import local_realms, RedisChallenges
        from redis_session_flask import SharedSessionInterface
        from session_readiness import configure_local_https
        secure=configure_local_https(app,os.environ)
        if local_runtime is not None:
            from shared_session_runtime import LocalSessionRuntime
            if not isinstance(local_runtime,LocalSessionRuntime):
                raise RuntimeError('Invalid injected local runtime.')
            local_runtime.install(app,secure=secure)
            realms=app.extensions['rosago_shared_sessions']
        else:
            realms = local_realms(os.environ)
            app.extensions['rosago_shared_sessions'] = realms
            app.extensions['rosago_login_challenges'] = RedisChallenges(realms)
            app.session_interface = SharedSessionInterface(realms,secure=secure)

        @app.get('/auth/session-readiness')
        def session_readiness():
            checks=[realm.readiness() for realm in realms.values()]
            return {'ready':all(c['ready'] for c in checks),'protocol':3,'production_approved':False},200,{'Cache-Control':'no-store'}

    @app.errorhandler(SessionStorageUnavailable)
    def storage_unavailable(error):
        return 'Authentication temporarily unavailable. Please try again later.', 503

    @app.before_request
    def realm_boundary():
        request.environ['rosago.realm_interface'] = app.session_interface
        if getattr(session, 'storage_failed', False):
            return 'Authentication temporarily unavailable. Please try again later.', 503
        if request.script_root:
            return 'This authentication configuration requires a root-mounted app.', 503
        if getattr(session, 'invalid', False):
            label = 'Admin' if isinstance(session, AdminBrowserSession) else 'User'
            return f'Invalid {label} session cookie. Clear this site cookie and sign in again.', 403
