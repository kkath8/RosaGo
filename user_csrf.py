"""User-purpose login/logout CSRF; never reads Admin browser state."""
import secrets

from flask import current_app, g, request, session
from jinja2 import pass_context
from session_realms import is_admin_path


def user_login_csrf():
    if is_admin_path(request.path):
        return ''
    challenges = current_app.extensions['rosago_login_challenges']
    token = session.get('user_login_csrf')
    if not challenges.valid('user', token):
        token = challenges.issue('user')
        session['user_login_csrf'] = token
    return token


def validate_user_login_csrf():
    from redis_session_flask import begin_login
    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return False
    tokens = request.form.getlist('csrf_token')
    expected = session.get('user_login_csrf')
    return (len(tokens) == 1 and type(expected) is str and
            secrets.compare_digest(tokens[0].encode(), expected.encode()) and
            begin_login('user', expected))


@pass_context
def user_logout_csrf(context=None, *, resolve=False):
    if is_admin_path(request.path):
        return ''
    if context is not None and context.get('ui_authenticated') and context.get('csrf'):
        # Reuse the display-safe User token already copied before authority was
        # hidden from Jinja. No new authentication lookup during rendering.
        return context['csrf']
    # Public catalog rendering must remain free of authentication lookups or
    # cookie mutations. Authenticated scopes copy this display-safe token.
    token = g.get('user_logout_token')
    if token:
        return token
    auth = g.get('auth')
    if auth is not None and auth.realm == 'user':
        from normal_auth_flask import get_normal_auth_dependencies
        record = get_normal_auth_dependencies().store.resolve(auth.auth_session_id)
        return record.csrf if record else ''
    if not resolve:
        return ''
    from normal_auth_flask import read_auth_session_id, get_normal_auth_dependencies
    handle = read_auth_session_id()
    record = get_normal_auth_dependencies().store.resolve(handle) if handle else None
    if record:
        return record.csrf
    token = session.get('user_logout_csrf')
    if type(token) is not str:
        token = secrets.token_urlsafe(32)
        session['user_logout_csrf'] = token
    return token


def validate_user_logout_csrf():
    if (request.headers.get('Origin') != request.host_url.rstrip('/') or request.files
            or set(request.form) != {'csrf_token'} or len(request.form.getlist('csrf_token')) != 1):
        return False
    from normal_auth_flask import read_auth_session_id, get_normal_auth_dependencies
    handle = read_auth_session_id()
    supplied = request.form['csrf_token']
    if handle is not None and get_normal_auth_dependencies().store.resolve(handle) is not None:
        return get_normal_auth_dependencies().coordinator.validate_csrf(handle, supplied)
    expected = session.get('user_logout_csrf')
    return type(expected) is str and secrets.compare_digest(expected.encode(), supplied.encode())
