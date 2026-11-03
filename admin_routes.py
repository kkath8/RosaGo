"""Protected Admin management, operational projections and authentication routes."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import os
import re
import secrets
import time

from flask import Blueprint, current_app, flash, g, redirect, request, session, url_for

from admin_auth import admin_required, render_admin_page
from admin_authorization_service import AdminAuthorizationError, is_current_admin
from admin_dashboard_service import published_catalog_health
from admin_insights_service import catalog_insights, ISSUES, SCOPES, ATTENTION_PAGE_SIZE
from admin_places_service import (
    destination_counts, catalog_page, validate_catalog_filters, AdminPlacesFilterError,
    get_destination, AdminPlacesError, STATUSES, PAGE_SIZE, MAX_OFFSET,
)
from place_model import CATEGORIES
from admin_management_service import (BASIC_FIELDS, TOURISM_FIELDS as EDIT_TOURISM_FIELDS,
    ACTIONS, DestinationValidationError, mutate_destination, operational_overview)
from destination_weather_metadata import load_weather_catalog
from profile_service import get_own_profile, ProfileServiceError
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
    health = None
    if counts is not None:
        try:
            health = published_catalog_health(g.auth, tourism_metadata_enabled=(
                os.getenv('ROSAGO_TOURISM_METADATA_ENABLED', '').lower() == 'true'))
        except AdminPlacesError:
            pass
    overview = _overview_or_none()
    if overview is not None:
        overview = {key: overview[key] for key in ('users_total', 'trips_total')}
    try:
        attention = catalog_insights(g.auth, tourism_metadata_enabled=_tourism_enabled(),scope='all')['attention_total']
    except AdminPlacesError:
        attention = None
    return render_admin_page('admin/dashboard.html', logout_csrf=_logout_csrf(),
        active='dashboard', counts=counts, health=health,
        overview=overview, attention=attention,
        observed_at=datetime.now(timezone(timedelta(hours=8)))), 200 if counts is not None else 503


@admin.route('/account')
@admin_required
def account():
    if request.args:
        return 'This account page does not accept selection parameters.', 400
    display_name = None
    profile_unavailable = False
    try:
        profile = get_own_profile(g.auth)
    except ProfileServiceError:
        profile_unavailable = True
    else:
        if profile is not None:
            display_name = ' '.join(part for part in (profile.first_name, profile.last_name) if part) or None
    # Pass display strings only, never the profile's ID, auth context or claims.
    # User updates are explicitly outside Phase 4, including own-name changes.
    return render_admin_page('admin/account.html', active='account', logout_csrf=_logout_csrf(),
        display_name=display_name, account_email=g.auth.user_email, profile_unavailable=profile_unavailable)


@admin.route('/settings')
@admin_required
def settings():
    if request.args:
        return 'This settings page does not accept selection parameters.', 400
    return render_admin_page('admin/settings.html', active='settings', logout_csrf=_logout_csrf())


@admin.route('/help')
@admin_required
def help_page():
    if request.args:
        return 'This guide does not accept selection parameters.', 400
    return render_admin_page('admin/help.html', active='help', logout_csrf=_logout_csrf())


@admin.route('/about')
@admin_required
def about():
    if request.args:
        return 'This information page does not accept selection parameters.', 400
    return render_admin_page('admin/about.html', active='about', logout_csrf=_logout_csrf())


@admin.route('/insights')
@admin_required
def insights():
    if (set(request.args) - {'scope', 'issue', 'page'}
            or any(len(request.args.getlist(key)) != 1 for key in request.args)):
        return 'Invalid catalog insight filter.', 400
    scope = request.args.get('scope', 'published')
    issue = request.args.get('issue') or None
    raw_page = request.args.get('page', '1')
    if (scope not in SCOPES or (issue is not None and issue not in ISSUES)
            or not raw_page.isascii() or not raw_page.isdecimal()
            or len(raw_page) > 3 or str(int(raw_page)) != raw_page or not 1 <= int(raw_page) <= 200):
        return 'Invalid catalog insight filter.', 400
    page = int(raw_page)
    enabled = os.getenv('ROSAGO_TOURISM_METADATA_ENABLED', '').lower() == 'true'
    try:
        data = catalog_insights(g.auth, tourism_metadata_enabled=enabled, scope=scope, issue=issue, page=page)
    except AdminPlacesError:
        data = None
    page_args = dict(scope=scope, issue=issue) if issue else dict(scope=scope)
    return render_admin_page('admin/insights.html', active='insights', logout_csrf=_logout_csrf(),
        data=data, scope=scope, issue=issue, issues=ISSUES, tourism_enabled=enabled, page=page,
        page_size=ATTENTION_PAGE_SIZE,
        previous_url=url_for('admin.insights', **page_args, page=page - 1, _anchor='needs-attention') if page > 1 else None,
        next_url=url_for('admin.insights', **page_args, page=page + 1, _anchor='needs-attention')
            if data is not None and data['attention_has_next'] else None,
        observed_at=datetime.now(timezone(timedelta(hours=8)))), 200 if data is not None else 503


@admin.route('/places')
@admin_required
def places():
    if (set(request.args) - {'q', 'status', 'category', 'tourism_type', 'coordinates', 'offset'}
            or any(len(request.args.getlist(key)) != 1 for key in request.args)):
        return 'Invalid destination filter or page.', 400
    raw_offset = request.args.get('offset', '0')
    if (not raw_offset.isascii()
            or not raw_offset.isdecimal() or len(raw_offset) > 10
            or str(int(raw_offset)) != raw_offset or int(raw_offset) > MAX_OFFSET):
        return 'Invalid destination filter or page.', 400
    offset = int(raw_offset)
    enabled = os.getenv('ROSAGO_TOURISM_METADATA_ENABLED', '').lower() == 'true'
    try:
        filters = validate_catalog_filters(q=request.args.get('q', ''),
            status=request.args.get('status') or None, category=request.args.get('category') or None,
            tourism_type=request.args.get('tourism_type') or None,
            coordinates=request.args.get('coordinates') or None, offset=offset,
            tourism_metadata_enabled=enabled)
    except AdminPlacesFilterError:
        return 'Invalid destination filter or search.', 400
    try:
        catalog = catalog_page(g.auth, **filters)
    except AdminPlacesError:
        catalog = None
    page_args = {key: value for key, value in filters.items()
                 if key not in ('offset', 'tourism_metadata_enabled') and value}
    next_offset = offset + PAGE_SIZE if catalog is not None and offset + PAGE_SIZE < catalog.matching else None
    return render_admin_page('admin/places.html', logout_csrf=_logout_csrf(), active='places',
        catalog=catalog, filters=filters, categories=sorted(CATEGORIES), offset=offset,
        previous_url=url_for('admin.places', **page_args, offset=max(0, offset - PAGE_SIZE)) if offset else None,
        next_url=url_for('admin.places', **page_args, offset=next_offset) if next_offset is not None else None,
        tourism_enabled=enabled), 200 if catalog is not None else 503


@admin.route('/places/new', methods=['GET', 'POST'])
@admin_required
def new_place():
    return _destination_form()


def _tourism_enabled():
    return os.getenv('ROSAGO_TOURISM_METADATA_ENABLED', '').lower() == 'true'


def _valid_mutation_form(fields):
    return (_strict_form(set(fields) | {'csrf_token'}) and
        get_normal_auth_dependencies().coordinator.validate_csrf(
            g.auth.auth_session_id, request.form.get('csrf_token', '')))


def _load_management_place(slug):
    return get_destination(g.auth, slug, tourism_metadata_enabled=_tourism_enabled())


def _destination_form(slug=None):
    enabled = _tourism_enabled()
    fields = BASIC_FIELDS + (EDIT_TOURISM_FIELDS if enabled else ())
    error, status, place = '', 200, None
    if request.args:
        return 'Destination forms do not accept selection parameters.', 400
    if request.method == 'POST' and not _valid_mutation_form(fields + (('expected_updated_at',) if slug else ())):
        return 'Please reload this page and try again.', 403
    try:
        if slug:
            place = _load_management_place(slug)
            if place is None:
                return render_admin_page('admin/catalog_error.html', active='places',
                    logout_csrf=_logout_csrf(), unavailable=False), 404
        if request.method == 'POST':
            result = mutate_destination(g.auth, action='edit' if slug else 'create', slug=slug,
                expected_updated_at=request.form.get('expected_updated_at'),
                values={key: request.form[key] for key in fields}, tourism_enabled=enabled)
            flash('Destination changes saved.' if slug else 'Destination created as Draft.', 'success')
            return redirect(url_for('admin.place_detail', slug=result['slug']), code=303)
    except DestinationValidationError as exc:
        error, status = str(exc), 400
    except AdminPlacesError:
        error, status = ('Destination could not be saved or loaded. Reload before retrying. '
            'The write capability may need deployment, or this record may have changed.'), 503
        if slug and place is None:
            return render_admin_page('admin/catalog_error.html', active='places',
                logout_csrf=_logout_csrf(), unavailable=True), 503
    values = {key: request.form.get(key, '') if request.method == 'POST' else
              (getattr(place, key, None) if place else '') for key in fields}
    return render_admin_page('admin/place_form.html', active='places', logout_csrf=_logout_csrf(),
        place=place, values=values, error=error, tourism_enabled=enabled, categories=sorted(CATEGORIES),
        form_version=request.form.get('expected_updated_at','') if request.method == 'POST' else
            (place.updated_at.isoformat() if place else '')), status


def _destination_page(slug, template):
    try:
        place = get_destination(g.auth, slug, tourism_metadata_enabled=(
            os.getenv('ROSAGO_TOURISM_METADATA_ENABLED', '').lower() == 'true'))
    except AdminPlacesError:
        return render_admin_page('admin/catalog_error.html', active='places',
            logout_csrf=_logout_csrf(), unavailable=True), 503
    if place is None:
        return render_admin_page('admin/catalog_error.html', active='places',
            logout_csrf=_logout_csrf(), unavailable=False), 404
    return render_admin_page(template, active='places', logout_csrf=_logout_csrf(),
        place=place, categories=sorted(CATEGORIES), destination_weather=load_weather_catalog().for_place(place))


@admin.route('/places/<slug>')
@admin_required
def place_detail(slug):
    return _destination_page(slug, 'admin/place_detail.html')


@admin.route('/places/<slug>/edit', methods=['GET', 'POST'])
@admin_required
def edit_place(slug):
    return _destination_form(slug)


@admin.route('/places/<slug>/publication/<action>', methods=['GET', 'POST'])
@admin_required
def publication(slug, action):
    if action not in ACTIONS or request.args:
        return 'Invalid publication action.', 400
    if request.method == 'POST' and not _valid_mutation_form(('expected_updated_at',)):
        return 'Please reload this page and try again.', 403
    try:
        place = _load_management_place(slug)
        if place is None:
            return render_admin_page('admin/catalog_error.html', active='places',
                logout_csrf=_logout_csrf(), unavailable=False), 404
        allowed = {'draft': ('publish','archive'), 'published': ('draft','archive'), 'archived': ('restore',)}
        if action not in allowed[place.status]:
            return 'This publication action is no longer available. Reload the destination.', 409
        if request.method == 'POST':
            mutate_destination(g.auth, action=action, slug=slug,
                expected_updated_at=request.form['expected_updated_at'])
            flash('Destination publication updated.', 'success')
            return redirect(url_for('admin.place_detail', slug=slug), code=303)
    except AdminPlacesError:
        return render_admin_page('admin/catalog_error.html', active='places',
            logout_csrf=_logout_csrf(), unavailable=True), 503
    except DestinationValidationError as exc:
        return str(exc), 400
    return render_admin_page('admin/publication.html', active='places', logout_csrf=_logout_csrf(),
        place=place, action=action)


def _overview_or_none(**kwargs):
    try:
        return operational_overview(g.auth, **kwargs)
    except AdminPlacesError:
        return None


@admin.route('/users')
@admin_required
def users():
    if (set(request.args) - {'q','page'} or any(len(request.args.getlist(k)) != 1 for k in request.args)):
        return 'Invalid user search or page.', 400
    raw_page, q = request.args.get('page','1'), request.args.get('q','')
    if not re.fullmatch(r'[1-9][0-9]{0,5}',raw_page) or int(raw_page)>100000:
        return 'Invalid user page.', 400
    page = int(raw_page)
    try:
        data = _overview_or_none(q=q, page=page)
    except ValueError:
        return 'Invalid user search.', 400
    return render_admin_page('admin/users.html', active='users', logout_csrf=_logout_csrf(),
        data=data, q=q, page=page,
        previous_url=url_for('admin.users',q=q,page=page-1) if page>1 else None,
        next_url=url_for('admin.users',q=q,page=page+1) if data and page*25<data['users_matching'] else None), 200 if data is not None else 503


@admin.route('/trips')
@admin_required
def trips():
    if request.args:
        return 'This aggregate page does not accept selection parameters.', 400
    data = _overview_or_none()
    # Never pass the user directory into trip presentation.
    trip_data = {k:v for k,v in data.items() if not k.startswith('users')} if data else None
    return render_admin_page('admin/trips.html', active='trips', logout_csrf=_logout_csrf(),
        data=trip_data), 200 if data is not None else 503


@admin.route('/system')
@admin_required
def system():
    if (set(request.args)-{'page'} or any(len(request.args.getlist(k)) != 1 for k in request.args)):
        return 'Invalid weather review page.', 400
    raw_page=request.args.get('page','1')
    if not re.fullmatch(r'[1-9][0-9]{0,2}',raw_page) or int(raw_page)>200:
        return 'Invalid weather review page.', 400
    page=int(raw_page)
    try:
        data=catalog_insights(g.auth,tourism_metadata_enabled=_tourism_enabled(),scope='all',
            issue='weather_unknown',page=page)
    except AdminPlacesError:
        data=None
    weather=current_app.extensions['rosago_weather'].get_weather()
    return render_admin_page('admin/system.html', active='system', logout_csrf=_logout_csrf(),
        data=data, weather=weather, routing_provider=current_app.extensions['rosago_routing'].label,
        previous_url=url_for('admin.system',page=page-1) if page>1 else None,
        next_url=url_for('admin.system',page=page+1) if data and data['attention_has_next'] else None)
