"""Admin presentation and protected auth entry points; no destination queries."""
from contextlib import ExitStack
import secrets
import time

from flask import Blueprint, g, redirect, request, session, url_for

from admin_auth import admin_required, render_admin_page
from admin_authorization_service import AdminAuthorizationError, is_current_admin
from admin_places_service import (
    destination_counts, list_destinations, AdminPlacesError, STATUSES, PAGE_SIZE, MAX_OFFSET,
)
from auth_helpers import login_required
from normal_auth_coordinator import PasswordLoginError
from normal_auth_flask import (
    normal_authenticated, NormalAuthEntryError, clear_normal_auth_authority,
    get_normal_auth_dependencies, establish_normal_session, SessionEstablishmentError,
    logout_normal_session, LocalLogoutError,
)

admin = Blueprint('admin', __name__, url_prefix='/admin')


def _login_csrf():
    token = session.get('admin_login_csrf')
    issued = session.get('admin_login_csrf_at')
    if (type(token) is not str or type(issued) not in (int, float)
            or not 0 <= time.time() - issued < 1800):
        token = secrets.token_urlsafe(32)
        session['admin_login_csrf'] = token
        session['admin_login_csrf_at'] = time.time()
    return token


def _strict_form(fields):
    return (request.headers.get('Origin') == request.host_url.rstrip('/')
            and not request.files and set(request.form) == fields
            and all(len(request.form.getlist(key)) == 1 for key in fields))


def _logout_csrf():
    record = get_normal_auth_dependencies().store.resolve(g.auth.auth_session_id)
    return record.csrf if record else ''


def _login_page(message='', status=200, *, email='', signed_in=False):
    return render_admin_page('admin/login.html', message=message, email=email,
        login_csrf=_login_csrf(), signed_in=signed_in,
        logout_csrf=_logout_csrf() if signed_in else ''), status


def _current_login_destination():
    """Check membership inside the normal context; render without its authority."""
    with ExitStack() as stack:
        try:
            stack.enter_context(normal_authenticated())
        except NormalAuthEntryError as error:
            if error.may_clear_authority:
                clear_normal_auth_authority()
                return _login_page()
            return _login_page('Authentication is temporarily unavailable. Please try again.', 503)
        try:
            allowed = is_current_admin(g.auth)
        except AdminAuthorizationError:
            return _login_page('Admin authorization is temporarily unavailable. Please try again.',
                               503, signed_in=True)
        if allowed:
            return redirect(url_for('admin.index'), code=303)
        return _login_page('Admin access required. You can continue to the User side or log out.',
                           403, signed_in=True)


@admin.route('/login', methods=['GET', 'POST'])
def login():
    if request.method != 'POST':
        return _current_login_destination()
    if not _strict_form({'csrf_token', 'email', 'password'}):
        return _login_page('Please reload this page and try again.', 403)
    supplied = request.form['csrf_token']
    expected = session.get('admin_login_csrf')
    issued = session.get('admin_login_csrf_at')
    if (type(expected) is not str or not supplied
            or type(issued) not in (int, float) or not 0 <= time.time() - issued < 1800
            or not secrets.compare_digest(supplied.encode(), expected.encode())):
        return _login_page('Please reload this page and try again.', 403)
    email = request.form['email'].strip()
    password = request.form['password']
    if not email or not password.strip():
        return _login_page('Enter your email and password.', 400, email=email)
    try:
        credentials = get_normal_auth_dependencies().adapters.password_login(email, password)
        establish_normal_session(credentials)
    except PasswordLoginError as error:
        status, message = {
            'invalid_credentials': (401, 'Invalid email or password.'),
            'unconfirmed_email': (403, 'Please verify your email before logging in.'),
            'throttled': (429, 'Too many login attempts. Please wait before trying again.'),
            'invalid_result': (401, 'We could not confirm your login. Please try again.'),
            'service_failure': (503, 'We could not complete your login. Please try again later.'),
        }[error.reason]
        return _login_page(message, status, email=email)
    except SessionEstablishmentError:
        return _login_page('We could not complete your login. Please try again later.', 503)
    session.pop('admin_login_csrf', None)
    session.pop('admin_login_csrf_at', None)
    return _current_login_destination()


@admin.route('/logout', methods=['POST'])
@login_required(login_endpoint='admin.login')
def logout():
    # Membership revocation must not prevent a signed-in user from logging out.
    if (not _strict_form({'csrf_token'})
            or not get_normal_auth_dependencies().coordinator.validate_csrf(
                g.auth.auth_session_id, request.form.get('csrf_token', ''))):
        return 'Please reload this page and try again.', 403
    try:
        logout_normal_session()
        session.clear()
    except LocalLogoutError:
        return 'Logout could not be completed. Please try again.', 503
    return redirect(url_for('admin.login'), code=303)


@admin.route('')
@admin_required
def index():
    try:
        counts = destination_counts(g.auth)
    except AdminPlacesError:
        counts = None
    return render_admin_page('admin/dashboard.html', logout_csrf=_logout_csrf(),
                             active='dashboard', counts=counts), 200 if counts is not None else 503


@admin.route('/places')
@admin_required
def places():
    if (set(request.args) - {'status', 'offset'}
            or any(len(request.args.getlist(key)) != 1 for key in request.args)):
        return 'Invalid destination filter or page.', 400
    status = request.args.get('status')
    raw_offset = request.args.get('offset', '0')
    if ((status is not None and status not in STATUSES) or not raw_offset.isascii()
            or not raw_offset.isdecimal() or len(raw_offset) > 10
            or str(int(raw_offset)) != raw_offset or int(raw_offset) > MAX_OFFSET):
        return 'Invalid destination filter or page.', 400
    offset = int(raw_offset)
    try:
        rows = list_destinations(g.auth, status=status, offset=offset)
    except AdminPlacesError:
        rows = None
    next_offset = (offset + PAGE_SIZE if rows is not None and len(rows) == PAGE_SIZE
                   and offset + PAGE_SIZE <= MAX_OFFSET else None)
    return render_admin_page('admin/places.html', logout_csrf=_logout_csrf(), active='places',
        rows=rows, selected_status=status, offset=offset, next_offset=next_offset,
        previous_offset=max(0, offset - PAGE_SIZE)), 200 if rows is not None else 503
