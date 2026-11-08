import os
import re
import logging
import time
import httpx
import secrets
import hashlib
import hmac
import unicodedata
from contextlib import ExitStack
from datetime import date, datetime, timezone
from uuid import UUID
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from dotenv import load_dotenv
from flask import Flask, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
from supabase import Client, ClientOptions, create_client
from supabase_auth.errors import AuthApiError, AuthError

from auth_helpers import login_required
from admin_session_flask import init_admin_auth
from session_realms import init_session_realms, LoginChallenges
from public_auth_security import (configured_public_origin, email_form_origin_allowed,
                                  email_attempt_allowed)
from user_csrf import (user_login_csrf, validate_user_login_csrf,
                       user_logout_csrf, validate_user_logout_csrf)
from user_features import init_user_features, personal_scope, visitor_place, notification_cards, alerts_notification_cards
from password_policy import PASSWORD_RULES, password_error
from admin_routes import admin
from itinerary_draft_service import (
    create_itinerary_draft, get_itinerary_draft, update_itinerary_draft_preferences,
    DraftError, DraftValidationError, DraftRejectedError, DraftUnavailableError, DraftConsistencyError,
    validate_complete_preferences,
    get_itinerary_preview_draft, store_itinerary_draft_preview,
    return_itinerary_draft_to_editing,
    adjust_itinerary_draft_preview,
)
from itinerary_preview import (
    build_personalized_preview, compute_catalog_fingerprint, PreviewContractError,
)
from recommendation_engine import (
    rank_candidates, MAX_CANDIDATES, CATEGORY_INTEREST_MATCH, RecommendationInputError,
)
from itinerary_selection_policy import select_destinations, SelectionPolicyError, DESTINATIONS_PER_DAY
from itinerary_geography import order_places
from itinerary_adjustment import validate_adjustment, adjusted_preferences, UNSUPPORTED
from itinerary_quiz_form import (
    COMPANIONS, TRANSPORTATION, TRIP_PACES, ACTIVITIES, ENVIRONMENTS,
    FORM_FIELDS, REPEATED_FIELDS, parse_quiz_form, form_values,
    submitted_values, expected_revision as quiz_expected_revision, QuizTimeWindowError,
)
from trip_service import (
    list_user_trips, list_upcoming_trips, list_dashboard_upcoming_trips, get_user_trip, create_trip, update_trip, delete_trip, add_place,
    TripServiceError, TripValidationError, TripNotFoundError,
    TripOperationRejectedError, TripUnavailableError, TripConsistencyError,
)
from normal_auth_flask import (
    init_normal_auth, get_normal_auth_dependencies, establish_normal_session,
    SessionEstablishmentError, normal_auth_redirect_decision, AuthRedirectDecision,
    normal_auth_state, logout_normal_session,
    normal_authenticated, NormalAuthEntryError, read_auth_session_id,
)
from normal_auth_coordinator import PasswordLoginError
from places_client import PublicPlacesClient
from place_search import normalize_query, search_published
from routing_service import RoutingService, RoutingError, validate_request as validate_route_request
from transport_modes import ROUTE_MODE_LABELS, route_mode_for_preference
from weather_service import WeatherService, manila_now
from itinerary_weather import before_requested_start, forecast_review, ForecastReview
from destination_weather_metadata import load_weather_catalog
from weather_proposal import build_weather_proposal, proposal_binding
from alerts_service import weather_alerts, trip_alerts, TRIP_HORIZON_DAYS
from gemini_service import GeminiService
from email_verification import PendingEmailStore, EmailVerificationService
from assistant_store import AssistantStore, ChatBusy
from assistant_context import (validate_message, recommendation_context, chat_context, weather_requested)
from settings_service import (SESSION_KEY as SETTINGS_SESSION_KEY, ALERT_DISPLAY_OPTIONS,
                              SettingsValidationError, get_settings, validate_settings)
from places_service import (
    CATEGORIES, PlacesService, PlacesValidationError,
    PlacesUnavailableError, PlacesConsistencyError,
)
from destination_categories import CATEGORY_LABELS, category_registry, flexible_catalog_enabled
from profile_service import (
    get_own_profile, update_own_profile, ProfileUnavailableError,
    ProfileConsistencyError, ProfileValidationError, ProfileNotFoundError, profile_initials,
)
from recovery_helpers import RECOVERY_ERROR, RecoveryGrants, recovery_expiry, PendingRecoveries, pkce_s256_challenge
from recovery_diagnostics import recovery_diagnostic
from recovery_transport import send_pkce_recovery, RecoveryRequestRejected

EVALUATION_MODE = os.environ.get('ROSAGO_EVALUATION') == 'true'
if EVALUATION_MODE:
    # Never merge this workspace's real-project .env into an evaluation process.
    from evaluation_config import validate_evaluation_environment
    validate_evaluation_environment(os.environ)
else:
    load_dotenv()

if os.environ.get('ROSAGO_CATALOG_PREVIEW') == 'true':
    from catalog_preview import validate_preview_environment
    validate_preview_environment(os.environ)

# A requested rollout with a missing/unapproved/wrong-project registry must fail
# at startup, before any destination requests, rather than fall back silently.
category_registry()

PUBLIC_ORIGIN = configured_public_origin(os.environ)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

if not FLASK_SECRET_KEY or not FLASK_SECRET_KEY.strip():
    raise RuntimeError("Flask configuration error: FLASK_SECRET_KEY must be set.")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Supabase configuration error: SUPABASE_URL and SUPABASE_KEY must both be set."
    )

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=ClientOptions(persist_session=False, auto_refresh_token=False),
)

app = Flask(__name__)
if EVALUATION_MODE:
    from evaluation_config import configure_evaluation_http
    app.extensions['rosago_evaluation'] = configure_evaluation_http(app, os.environ)

    @app.before_request
    def evaluation_disabled_operations():
        email_paths = ('/register', '/forgot-password', '/verify-email',
                       '/verify-email/resend', '/reset-password')
        if request.path in email_paths:
            return 'Email account workflows are disabled in this synthetic evaluation.', 503
        if request.method == 'POST' and request.path.startswith('/admin/places'):
            photo = request.files.get('photo')
            if (photo is not None and photo.filename) or 'remove_photo' in request.form:
                return 'Photo changes are disabled in this synthetic evaluation.', 403

app.config.update(MAX_CONTENT_LENGTH=6 * 1024 * 1024,
                  MAX_FORM_MEMORY_SIZE=128 * 1024, MAX_FORM_PARTS=100)
app.extensions['rosago_public_email_limits'] = LoginChallenges()


@app.after_request
def browser_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    private_auth = (request.path in ('/register', '/login', '/logout', '/forgot-password')
                    or request.path.startswith(('/auth/', '/verify-email', '/reset-password')))
    response.headers.setdefault('Referrer-Policy',
                                'no-referrer' if private_auth else 'strict-origin-when-cross-origin')
    if private_auth:
        response.headers.setdefault('Cache-Control', 'no-store')
    response.headers.setdefault('Content-Security-Policy',
                                "frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
    return response


@app.get('/health/ready')
def production_readiness():
    # Liveness is not proof of qualified public authentication/recovery.
    return {'ready': False, 'production_sessions_qualified': False}, 503
# Recheck edited Jinja files even when the local server runs without a debugger.
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.globals['password_rules'] = PASSWORD_RULES
app.jinja_env.globals['profile_initials'] = profile_initials


def auth_asset_url(filename):
    """Version only the registration/reset assets by their current contents."""
    if filename not in {'css/auth.css', 'js/password-policy.js', 'js/auth.js', 'js/reset-password.js'}:
        raise ValueError('Unsupported auth asset.')
    with current_app.open_resource('static/' + filename) as asset:
        version = hashlib.sha256(asset.read()).hexdigest()[:12]
    return url_for('static', filename=filename, v=version)


app.jinja_env.globals['auth_asset_url'] = auth_asset_url
app.extensions['rosago_places'] = PlacesService(
    PublicPlacesClient(SUPABASE_URL, SUPABASE_KEY).database_client,
    tourism_metadata_enabled=os.getenv('ROSAGO_TOURISM_METADATA_ENABLED', '').lower() == 'true',
    environment_enabled=os.getenv('ROSAGO_DESTINATION_ENVIRONMENT_ENABLED', '').lower() == 'true',
)
app.extensions['rosago_routing'] = RoutingService.from_environment(os.environ)
app.extensions['rosago_weather'] = WeatherService()
app.extensions['rosago_gemini'] = GeminiService.from_environment(os.environ)
app.extensions['rosago_assistant'] = AssistantStore()
app.extensions['rosago_email_pending'] = PendingEmailStore()
app.extensions['rosago_email_verification'] = EmailVerificationService(SUPABASE_URL, SUPABASE_KEY)


@app.context_processor
def website_template_options():
    return {'website_settings': get_settings(session),
            'category_labels': dict(CATEGORY_LABELS),
            'catalog_category_choices': tuple(CATEGORY_LABELS.items()),
            'flexible_catalog_enabled': flexible_catalog_enabled(),
            'user_login_csrf': user_login_csrf, 'user_logout_csrf': user_logout_csrf}


@app.context_processor
def routing_template_options():
    routing = current_app.extensions['rosago_routing']
    requested_mode = request.args.get('mode')
    preference = request.args.get('transportation')
    selected = requested_mode or route_mode_for_preference(preference, routing.modes)
    return dict(routing_modes=tuple((mode, ROUTE_MODE_LABELS[mode]) for mode in routing.modes),
                routing_provider=routing.label,
                selected_routing_mode=selected if selected in routing.modes else None,
                unsupported_route_preference=bool((requested_mode or preference) and selected not in routing.modes))


init_session_realms(app, mode=os.getenv('ROSAGO_AUTH_MODE', 'development'))
init_normal_auth(app, SUPABASE_URL, SUPABASE_KEY)
init_admin_auth(app, SUPABASE_URL, SUPABASE_KEY)
recovery_grants = RecoveryGrants()
pending_recoveries = PendingRecoveries()
if 'rosago_shared_sessions' in app.extensions:
    from shared_session_runtime import session_model
    recovery_grants = session_model(app, 'user', 'grants')
    pending_recoveries = session_model(app, 'user', 'pending')
    app.extensions['rosago_email_pending'] = session_model(app, 'user', 'email')
app.config.update(
    SECRET_KEY=FLASK_SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Local HTTP only. Set this to True in production when HTTPS is used.
    SESSION_COOKIE_SECURE=bool(getattr(app.session_interface,'secure',False)),
)


class CallbackLogFilter(logging.Filter):
    def filter(self, record):
        # Werkzeug otherwise includes callback query credentials in its access log.
        record.msg = re.sub(
            r'(/auth/(?:reset-callback|callback)|/verify-email(?:/resend)?)\?[^\s"]*', r'\1?[redacted]', record.getMessage()
        )
        record.args = ()
        return True


logging.getLogger("werkzeug").addFilter(CallbackLogFilter())


@app.route("/auth/callback")
def auth_callback():
    # Completion page after Supabase confirmation; this grants no authentication.
    # Legacy link callbacks do not prove verification and confer no authority.
    return render_template("auth/verified.html")


@app.after_request
def protect_auth_response(response):
    # Present existing fixed-message failures without changing their status or authority.
    if (request.path.startswith('/user/') and 400 <= response.status_code < 600
            and response.mimetype == 'text/html' and not response.is_streamed):
        message = response.get_data(as_text=True)
        if message and '<' not in message:
            auth = g.pop('auth', None)
            logout_token = g.pop('user_logout_token', None)
            try:
                response.set_data(render_template('user/error.html', message=message))
            finally:
                if auth is not None:
                    g.auth = auth
                if logout_token is not None:
                    g.user_logout_token = logout_token
    if (request.path in ('/budget', '/user/planner', '/user/transport', '/user/alerts', '/user/settings')
            or request.path == '/user/assistant' or request.path.startswith('/user/assistant/')):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Referrer-Policy'] = 'same-origin'
    if request.path == '/admin' or request.path.startswith('/admin/'):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Referrer-Policy'] = 'same-origin'
    if (request.path == '/user/trips' or request.path.startswith('/user/trips/')
            or request.path.startswith('/user/itinerary/')):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'same-origin'
    if request.path in ("/auth/callback", "/verify-email", "/verify-email/resend", "/auth/reset-callback", "/reset-password", "/login", "/register", "/user", "/user/profile/edit"):
        response.headers["Cache-Control"] = "no-store"
    if request.path in ("/auth/callback", "/auth/reset-callback"):
        response.headers["Referrer-Policy"] = "no-referrer"
    if request.path in ("/login", "/register", "/forgot-password", "/reset-password",
                        "/verify-email", "/verify-email/resend", "/user/profile/edit"):
        # Native POSTs under no-referrer send Origin: null. Preserve a
        # verifiable same-origin POST without sharing cross-origin referrers.
        response.headers["Referrer-Policy"] = "same-origin"
    if request.path in ("/auth/reset-callback", "/reset-password"):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
    return response


@app.route("/auth/reset-callback", methods=["GET"])
def reset_callback():
    recovery_diagnostic("RECOVERY_PKCE_CALLBACK_RECEIVED")

    def failure(status=400):
        return render_template("auth/reset_callback.html", message=RECOVERY_ERROR), status

    if request.headers.get("Origin") not in (None, request.host_url.rstrip("/")):
        recovery_diagnostic("RECOVERY_ORIGIN_REJECTED")
        return failure(403)
    codes = request.args.getlist("code")
    if (len(codes) != 1 or not codes[0].strip() or len(codes[0]) > 4096
            or any(key in request.args for key in (
                "error", "error_code", "error_description", "access_token",
                "refresh_token", "token_hash", "code_verifier", "type"))):
        recovery_diagnostic("RECOVERY_PKCE_CODE_REJECTED")
        return failure()
    recovery_diagnostic("RECOVERY_PKCE_CODE_PRESENT")
    pending_id = session.get("pending_recovery_id")
    reservation = pending_recoveries.reserve(pending_id)
    if reservation is None:
        recovery_diagnostic("RECOVERY_PENDING_REJECTED")
        return failure()
    lease, pending = reservation
    recovery_diagnostic("RECOVERY_PENDING_FOUND")
    try:
        # Never exchange on the shared client: the SDK saves an in-memory session.
        isolated = create_client(
            SUPABASE_URL, SUPABASE_KEY,
            options=ClientOptions(persist_session=False, auto_refresh_token=False),
        )
        with isolated.auth:
            recovery_diagnostic("RECOVERY_PKCE_EXCHANGE_STARTED")
            result = isolated.auth.exchange_code_for_session({
                "auth_code": codes[0], "code_verifier": pending.verifier,
            })
            if not result or not result.session or not result.user:
                recovery_diagnostic("RECOVERY_PKCE_EXCHANGE_FAILED")
                return failure()
            recovery_diagnostic("RECOVERY_PKCE_EXCHANGE_SUCCEEDED")
            # A successful exchange burns this flow even if later validation fails.
            # If replaced/expired while exchanging, do not grant any authorization.
            if pending_recoveries.finalize(pending_id, lease) is None:
                recovery_diagnostic("RECOVERY_PENDING_REJECTED")
                return failure()
            session.pop("pending_recovery_id", None)
            recovery_diagnostic("RECOVERY_PENDING_CONSUMED")
            token = result.session.access_token
            if not isinstance(token, str) or not token:
                return failure()
            recovery_diagnostic("RECOVERY_CLAIMS_CHECK_STARTED")
            verified = isolated.auth.get_claims(token)
            recovery_diagnostic("RECOVERY_USER_CHECK_STARTED")
            validated = isolated.auth.get_user(token)
            user = validated.user if validated else None
            if (not user or not user.id or result.user.id != user.id
                    or not result.session.user or result.session.user.id != user.id):
                recovery_diagnostic("RECOVERY_USER_VALIDATION_REJECTED")
                return failure()
            claims = verified.get("claims") if isinstance(verified, dict) else None
            expires = recovery_expiry(claims, user, SUPABASE_URL.rstrip("/") + "/auth/v1", time.time())
            if expires is None:
                recovery_diagnostic("RECOVERY_CLAIMS_REJECTED")
                return failure()
            recovery_diagnostic("RECOVERY_PKCE_CLAIMS_VALIDATED")
        handle = recovery_grants.issue(user.id, claims["session_id"], expires, token)
        if not handle:
            return failure()
    except AuthError:
        recovery_diagnostic("RECOVERY_PKCE_EXCHANGE_FAILED")
        return failure()
    except Exception:
        recovery_diagnostic("RECOVERY_SDK_ERROR")
        return failure(503)
    finally:
        # No-op after finalization. An unsuccessful exchange can be retried until expiry.
        pending_recoveries.release(pending_id, lease)

    recovery_grants.revoke(session.pop("password_recovery_id", None))
    session["password_recovery_id"] = handle
    recovery_diagnostic("RECOVERY_AUTHORIZED")
    return redirect(url_for("reset_password"), code=303)


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        recovery_diagnostic("RESET_PASSWORD_POST_RECEIVED")
    handle = session.get("password_recovery_id")
    if not recovery_grants.valid(handle):
        session.pop("password_recovery_id", None)
        return render_template("auth/reset_callback.html", process_callback=False, message=RECOVERY_ERROR), 403
    csrf = recovery_grants.csrf(handle)

    def form_error(message, status=400, *, field=None):
        return render_template("auth/reset_password.html", csrf=csrf,
                               message='' if field else message,
                               field_errors={field: message} if field else {}), status

    if request.method == "GET":
        return render_template("auth/reset_password.html", csrf=csrf)
    supplied_csrf = request.form.get("csrf_token", "")
    if not csrf or not supplied_csrf:
        recovery_diagnostic("RESET_PASSWORD_CSRF_MISSING")
        return form_error("Please reload this page and try again.", 403)
    if not secrets.compare_digest(supplied_csrf.encode(), csrf.encode()):
        recovery_diagnostic("RESET_PASSWORD_CSRF_MISMATCH")
        return form_error("Please reload this page and try again.", 403)
    if request.headers.get("Origin") not in (None, request.host_url.rstrip("/")):
        recovery_diagnostic("RESET_PASSWORD_ORIGIN_REJECTED")
        return form_error("Please reload this page and try again.", 403)
    password = request.form.get("new_password", "")
    confirmation = request.form.get("confirm_password", "")
    if not password.strip():
        recovery_diagnostic("RESET_PASSWORD_VALIDATION_REJECTED")
        return form_error("Please enter a new password.", field='new_password')
    policy_error = password_error(password)
    if policy_error:
        recovery_diagnostic("RESET_PASSWORD_VALIDATION_REJECTED")
        return form_error(policy_error, field='new_password')
    if not confirmation:
        recovery_diagnostic("RESET_PASSWORD_VALIDATION_REJECTED")
        return form_error("Please confirm your new password.", field='confirm_password')
    if password != confirmation:
        recovery_diagnostic("RESET_PASSWORD_VALIDATION_REJECTED")
        return form_error("Passwords do not match.", field='confirm_password')
    reservation = recovery_grants.reserve(handle)
    if not reservation:
        return form_error("Recovery access is unavailable or another update is processing.", 409)
    lease, grant = reservation
    try:
        isolated = create_client(SUPABASE_URL, SUPABASE_KEY,
            options=ClientOptions(persist_session=False, auto_refresh_token=False))
        with isolated.auth:
            # No refresh credential is retained: expired access must fail closed.
            restored = isolated.auth.set_session(grant.access_token, "")
            if (not restored or not restored.session or not restored.user
                    or restored.user.id != grant.user_id
                    or not restored.session.user or restored.session.user.id != grant.user_id
                    or not recovery_grants.valid(handle)):
                recovery_grants.revoke(handle)
                session.pop("password_recovery_id", None)
                return form_error("Recovery access is no longer valid. Please request a new link.", 403)
            recovery_diagnostic("RECOVERY_PASSWORD_UPDATE_STARTED")
            recovery_diagnostic("RESET_PASSWORD_UPDATE_STARTED")
            updated = isolated.auth.update_user({"password": password})
            # A completed update is never retried using this grant, even if the
            # returned response is unexpected or client cleanup later fails.
            recovery_grants.revoke(handle)
            session.pop("password_recovery_id", None)
            recovery_diagnostic("RECOVERY_GRANT_CONSUMED")
            if not updated or not updated.user or updated.user.id != grant.user_id:
                return form_error("We could not confirm the update. Please return to login.", 503)
            recovery_diagnostic("RECOVERY_PASSWORD_UPDATE_SUCCEEDED")
            recovery_diagnostic("RESET_PASSWORD_UPDATE_SUCCEEDED")
    except AuthApiError as error:
        recovery_diagnostic("RECOVERY_PASSWORD_UPDATE_FAILED")
        # Explicit client rejection can safely retry (e.g. password policy).
        if int(error.status) not in (400, 422, 429):
            recovery_grants.revoke(handle)
            session.pop("password_recovery_id", None)
        return form_error("The password could not be updated. Please try again or request a new recovery link.")
    except Exception:
        # Network/SDK failure may happen after the provider applied the change.
        # Discard authorization rather than repeat an ambiguous write.
        recovery_diagnostic("RECOVERY_PASSWORD_UPDATE_FAILED")
        recovery_grants.revoke(handle)
        session.pop("password_recovery_id", None)
        return form_error("We could not confirm the update. Please return to login or request a new recovery link.", 503)
    finally:
        recovery_grants.release(handle, lease)
    return redirect(url_for("login", password_updated="1"), code=303)


@app.route("/")
def index():
    # Bounded public preview; never interpret its length as a catalog total.
    places_unavailable = False
    try:
        places = current_app.extensions['rosago_places'].list_published(
            category=None, limit=3, offset=0)
    except (PlacesUnavailableError, PlacesConsistencyError):
        places = ()
        places_unavailable = True

    trips = ()
    first_name = None
    ui_scope = 'guest' if read_auth_session_id() is None else None
    trip_state = 'signed_out'
    # Cookie values are candidates only. Identity comes from the existing scope.
    if read_auth_session_id() is not None:
        with ExitStack() as stack:
            try:
                auth = stack.enter_context(normal_authenticated())
            except NormalAuthEntryError as error:
                if error.kind != 'unauthenticated':
                    trip_state = 'unavailable'
            else:
                g.user_logout_token = user_logout_csrf()
                trip_state = 'ready'
                ui_scope = personal_scope(auth.user_id)
                try:
                    profile = get_own_profile(auth)
                    first_name = profile.first_name if profile else None
                except (ProfileUnavailableError, ProfileConsistencyError):
                    pass
                try:
                    trips = tuple(dict(name=trip.name, visit_date=trip.visit_date,
                                       detail_url=url_for('trips_detail', trip_id=trip.id))
                                  for trip in list_dashboard_upcoming_trips(auth, today=manila_now().date()))
                except (TripUnavailableError, TripConsistencyError):
                    trip_state = 'unavailable'
        # The scope has closed its client and removed g.auth before rendering.
    response = current_app.make_response(render_template(
        'index.html', dashboard_places=tuple(p for p in places if visitor_place(p)), places_unavailable=places_unavailable,
        dashboard_trips=trips, dashboard_first_name=first_name, trip_state=trip_state,
        ui_scope=ui_scope, ui_authenticated=bool(ui_scope and ui_scope != 'guest')))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


def places_error(message, status):
    if request.endpoint in ('places_list', 'places_detail'):
        response = current_app.make_response((render_template('places/error.html', message=message), status))
    else:
        response = current_app.make_response((message, status))
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/places', methods=['GET'])
def places_list():
    categories = request.args.getlist('category')
    if len(categories) > 1 or (categories and categories[0] not in CATEGORIES):
        return places_error('Invalid place category.', 400)
    category = categories[0] if categories else None
    queries = request.args.getlist('q')
    try:
        if len(queries) > 1:
            raise PlacesValidationError()
        query = normalize_query(queries[0] if queries else '')
    except PlacesValidationError:
        return places_error('Enter a search of at most 200 characters without control characters.', 400)
    try:
        service = current_app.extensions['rosago_places']
        places = search_published(service, query, category=category)
    except PlacesValidationError:
        return places_error('Invalid place category.', 400)
    except PlacesUnavailableError:
        return places_error('Places are temporarily unavailable.', 503)
    except PlacesConsistencyError:
        return places_error('Unable to display places.', 500)
    places = tuple(p for p in places if visitor_place(p))
    return render_template('places/list.html', places=places,
                           categories=tuple(sorted(CATEGORIES)), selected_category=category)


@app.route('/map', methods=['GET'])
def map_index():
    try:
        markers = _map_markers()
    except PlacesUnavailableError:
        return places_error('Places are temporarily unavailable.', 503)
    except PlacesConsistencyError:
        return places_error('Unable to display places.', 500)
    return render_template('map.html', markers=markers)


def _map_markers():
    # Page through the catalog so valid destinations beyond the first page are
    # not silently omitted. Existing public/RLS publication checks still apply.
    places, offset = [], 0
    while True:
        page = current_app.extensions['rosago_places'].list_published(
            category=None, limit=50, offset=offset)
        places.extend(page)
        if len(page) < 50:
            break
        offset += 50
    if len({place.id for place in places}) != len(places):
        raise PlacesConsistencyError()
    return [dict(name=place.name,
                    detail_url=url_for('places_detail', slug=place.slug),
                    category=place.category, address=place.address,
                    tourism_type=getattr(place, 'tourism_type', None),
                    latitude=place.latitude, longitude=place.longitude)
               for place in places
               if visitor_place(place) and place.latitude is not None and place.longitude is not None]


@app.route('/api/route', methods=['POST'])
def route_api():
    """Public catalog routing; no auth credentials, caller URLs or DB writes."""
    from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

    def result(body, status=200):
        response = jsonify(body)
        response.status_code = status
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'same-origin'
        if status == 429:
            response.headers['Retry-After'] = '1'
        return response

    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return result({'error': 'invalid_origin', 'message': 'Request a route from RosaGo.'}, 403)
    if not request.is_json:
        return result({'error': 'invalid_request', 'message': 'Send a JSON route request.'}, 415)
    request.max_content_length = 4096
    try:
        data = request.get_json()
    except (BadRequest, RequestEntityTooLarge):
        return result({'error': 'invalid_request', 'message': 'Invalid or oversized route request.'}, 400)
    routing = current_app.extensions['rosago_routing']
    if not routing.configured:
        return result({'error': 'provider_unavailable', 'message': 'Routing is not configured. Please try again later.'}, 503)
    try:
        slug, latitude, longitude, mode = validate_route_request(data, routing.modes)
        place = current_app.extensions['rosago_places'].get_published_by_slug(slug)
        if place is None:
            return result({'error': 'destination_unavailable', 'message': 'This destination is unavailable.'}, 404)
        if place.latitude is None or place.longitude is None:
            return result({'error': 'missing_coordinates',
                           'message': 'This destination has no verified coordinates yet. Routing is unavailable.'}, 422)
        route = routing.route(start_latitude=latitude, start_longitude=longitude,
                              end_latitude=place.latitude, end_longitude=place.longitude, mode=mode)
    except RoutingError as error:
        return result({'error': error.code, 'message': str(error)}, error.status)
    except PlacesValidationError:
        return result({'error': 'invalid_destination', 'message': 'Choose a valid destination.'}, 400)
    except (PlacesUnavailableError, PlacesConsistencyError):
        return result({'error': 'catalog_unavailable', 'message': 'Destinations are temporarily unavailable.'}, 503)
    return result(route)


@app.route('/places/<slug>', methods=['GET'])
def places_detail(slug):
    if slug.lower().startswith('rosago-test-v1-'):
        return places_error('Place not found.', 404)
    try:
        place = current_app.extensions['rosago_places'].get_published_by_slug(slug)
    except PlacesValidationError:
        return places_error('Place not found.', 404)
    except PlacesUnavailableError:
        return places_error('Places are temporarily unavailable.', 503)
    except PlacesConsistencyError:
        return places_error('Unable to display places.', 500)
    if place is None:
        return places_error('Place not found.', 404)
    return render_template('places/detail.html', place=place,
                           destination_weather=load_weather_catalog().for_place(place))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == 'POST' and not email_form_origin_allowed():
        return 'Please reload this page and try again.', 403
    email = ""
    message = ""
    state = ""
    status = 200

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            message = "Please enter your email address."
            state, status = "error", 400
        elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            message = "Please enter a valid email address."
            state, status = "error", 400
        else:
            if not email_attempt_allowed('recovery'):
                return 'Too many requests. Please wait before trying again.', 429, {'Retry-After': '60'}
            message = "If an account exists for that email, a password reset link has been sent."
            state = "success"
            # Replace only the pending recovery flow; normal login is untouched.
            pending_recoveries.consume(session.pop("pending_recovery_id", None))
            pending_id = None
            accepted = False
            try:
                pending_id = pending_recoveries.create()
                recovery_diagnostic("RECOVERY_PENDING_CREATED")
                challenge = pkce_s256_challenge(pending_recoveries.lookup(pending_id).verifier)
                recovery_diagnostic("RECOVERY_PKCE_CREATED")
                with httpx.Client() as client:
                    send_pkce_recovery(
                        email, challenge, supabase_url=SUPABASE_URL,
                        supabase_key=SUPABASE_KEY, client=client,
                        redirect_to=PUBLIC_ORIGIN + '/auth/reset-callback',
                    )
                # Signed cookies contain only this opaque reference, never a verifier.
                session["pending_recovery_id"] = pending_id
                accepted = True
                recovery_diagnostic("RECOVERY_REQUEST_ACCEPTED")
            except RecoveryRequestRejected:
                # Provider errors can depend on account existence or email limits.
                # Keep the same response instead of disclosing those details.
                pass
            except Exception:
                # Do not display or log raw errors or request data.
                message = "We could not process your request right now. Please try again later."
                state, status = "error", 503
            finally:
                if not accepted:
                    pending_recoveries.consume(pending_id)
                    session.pop("pending_recovery_id", None)
                    recovery_diagnostic("RECOVERY_REQUEST_FAILED")

    response = app.make_response((render_template(
        "auth/forgot_password.html", email=email, message=message, state=state
    ), status))
    response.headers["Cache-Control"] = "no-store"
    return response


def normal_auth_page_check(template):
    decision = normal_auth_redirect_decision()
    if decision is AuthRedirectDecision.REDIRECT_USER:
        return redirect(url_for("user_index"), code=303)
    if decision is not AuthRedirectDecision.SHOW_FORM:
        response = app.make_response((render_template(
            template, email="", form_data={}, state="error",
            message="Authentication is temporarily unavailable. Please try again."), 503))
        response.headers["Cache-Control"] = "no-store"
        response.headers["Retry-After"] = "1"
        return response
    return None


def _login_trip_destination():
    # A single validated slug is the only continuation supported. Never accept
    # a caller-provided redirect URL or treat this hint as authentication.
    values = (request.form if request.method == 'POST' else request.args).getlist('add_place')
    if len(values) == 1 and len(values[0]) <= 120 and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', values[0]):
        return values[0]
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == 'POST' and not validate_user_login_csrf():
        response = app.make_response((render_template('auth/login.html', email='',
            message='Please reload this page and try again.', state='error', add_place_slug=None), 403))
        response.headers['Cache-Control'] = 'no-store'
        return response
    if request.method == 'POST' and not app.extensions['rosago_login_challenges'].allow_attempt('user', request.remote_addr):
        response = app.make_response((render_template('auth/login.html', email='',
            message='Too many login attempts. Please wait before trying again.', state='error', add_place_slug=None), 429))
        response.headers['Cache-Control'] = 'no-store'
        return response
    add_place_slug = _login_trip_destination()
    if request.method in ("GET", "HEAD"):
        response = normal_auth_page_check("auth/login.html")
        if response is not None:
            return response

    email = ""
    message = ""
    state = ""
    status = 200

    if request.method == "GET" and request.args.get("logged_out") == "1":
        message = "You have been logged out successfully."
        state = "success"
    elif request.method == "GET" and request.args.get("password_updated") == "1":
        message = "Your password has been updated successfully. You can now log in."
        state = "success"
    elif request.method == "GET" and request.args.get("login_required") == "1":
        message = "Please log in to continue."
        state = "error"

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        errors = []
        if not email:
            errors.append("Please enter your email address.")
        elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            errors.append("Please enter a valid email address.")
        if not password.strip():
            errors.append("Please enter your password.")

        state = "error"
        if errors:
            message = " ".join(errors)
            status = 400
        else:
            try:
                credentials = get_normal_auth_dependencies().adapters.password_login(email, password)
                establish_normal_session(credentials)
                session.pop('user_login_csrf', None)
                return redirect(url_for('trips_add_place', slug=add_place_slug)
                                if add_place_slug else url_for('index'), code=303)
            except PasswordLoginError as error:
                status, message = {
                    "invalid_credentials": (401, "Invalid email or password."),
                    "unconfirmed_email": (403, "Please verify your email before logging in. Check your inbox for the verification code."),
                    "throttled": (429, "Too many login attempts. Please wait before trying again."),
                    "invalid_result": (401, "We could not confirm your login. Please try again."),
                    "service_failure": (503, "We could not complete your login. Please try again later."),
                }[error.reason]
            except SessionEstablishmentError:
                message = "We could not complete your login. Please try again later."
                status = 503

    response = app.make_response((render_template(
        "auth/login.html", email=email, message=message, state=state,
        add_place_slug=add_place_slug
    ), status))
    response.headers["Cache-Control"] = "no-store"
    return response


app.register_blueprint(admin)


@app.route("/user")
@login_required
def user_index():
    try:
        profile = get_own_profile(g.auth)
    except ProfileUnavailableError:
        return "Profile information is temporarily unavailable. Please try again.", 503
    except ProfileConsistencyError:
        return "We could not display this page. Please try again later.", 500
    user_email = g.auth.user_email
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    # Flask exposes g to Jinja implicitly. Hide authority during eager rendering;
    # restore it for the surrounding auth scope's cleanup and nesting contract.
    auth = g.pop('auth')
    try:
        return render_template("user/index.html", profile=profile, user_email=user_email,
                               first_name=profile.first_name or '' if profile else '',
                               last_name=profile.last_name or '' if profile else '', csrf=csrf, field_errors={},
                               ui_scope=personal_scope(auth.user_id), ui_authenticated=True)
    finally:
        g.auth = auth


@app.route("/user/profile/edit", methods=["GET", "POST"])
@login_required
def user_profile_edit():
    dependencies = get_normal_auth_dependencies()
    message = ""
    status = 200
    field_errors = {}
    if request.method == "POST":
        tokens = request.form.getlist("csrf_token")
        if (len(tokens) != 1 or not tokens[0].strip()
                or not dependencies.coordinator.validate_csrf(g.auth.auth_session_id, tokens[0])):
            return "Please reload this page and try again.", 403
        if request.headers.get("Origin") not in (None, request.host_url.rstrip("/")):
            return "Please reload this page and try again.", 403
        fields = {"csrf_token", "first_name", "last_name"}
        if (request.files or set(request.form) != fields
                or any(len(request.form.getlist(field)) != 1 for field in fields)):
            return "Invalid profile form. Please reload this page and try again.", 400
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        for key, value in (('first_name', first_name), ('last_name', last_name)):
            if not value.strip():
                field_errors[key] = 'Enter your first name.' if key == 'first_name' else 'Enter your last name.'
            elif len(value.strip()) > 100 or any(unicodedata.category(c) in ('Cc', 'Cs') for c in value):
                field_errors[key] = 'Use up to 100 characters without control characters.'
        try:
            if field_errors:
                raise ProfileValidationError()
            update_own_profile(g.auth, first_name=first_name, last_name=last_name)
        except ProfileValidationError:
            if not field_errors:
                field_errors = {'first_name': 'Check your name.', 'last_name': 'Check your name.'}
            status = 400
        except ProfileNotFoundError:
            return "Your profile is currently unavailable for editing.", 404
        except ProfileUnavailableError:
            return "Your save could not be confirmed. Please check your profile before trying again.", 503
        except ProfileConsistencyError:
            return "We could not display this page. Please try again later.", 500
        else:
            flash("Profile updated successfully.", "profile_success")
            return redirect(url_for("user_index"), code=303)
    else:
        try:
            profile = get_own_profile(g.auth)
        except ProfileUnavailableError:
            return "Your profile could not be loaded. Please try again later.", 503
        except ProfileConsistencyError:
            return "We could not display this page. Please try again later.", 500
        if profile is None:
            return "Your profile is currently unavailable for editing.", 404
        first_name, last_name = profile.first_name or "", profile.last_name or ""

    record = dependencies.store.resolve(g.auth.auth_session_id)
    if record is None:
        return "Please reload this page and try again.", 403
    csrf = record.csrf
    del record
    user_email = g.auth.user_email
    # Match /user isolation for both GET and validation-error rendering.
    auth = g.pop('auth')
    try:
        return render_template("user/profile_edit.html", first_name=first_name,
                               last_name=last_name, user_email=user_email,
                               field_errors=field_errors,
                               csrf=csrf, message=message, ui_scope=personal_scope(auth.user_id), ui_authenticated=True), status
    finally:
        g.auth = auth


def _render_trip_page(template, **values):
    """Keep request authority out of Jinja, including inherited templates."""
    auth = g.pop('auth')
    try:
        values.setdefault('ui_scope', personal_scope(auth.user_id))
        values.setdefault('ui_authenticated', True)
        values.setdefault('user_email', auth.user_email)
        return render_template(template, **values)
    finally:
        g.auth = auth


def _trip_csrf():
    record = get_normal_auth_dependencies().store.resolve(g.auth.auth_session_id)
    return record.csrf if record is not None else None


def _trip_post_check(fields, *, repeated=()):
    tokens = request.form.getlist('csrf_token')
    if (len(tokens) != 1 or not tokens[0].strip()
            or not get_normal_auth_dependencies().coordinator.validate_csrf(
                g.auth.auth_session_id, tokens[0])):
        return 'Please reload this page and try again.', 403
    if request.headers.get('Origin') not in (None, request.host_url.rstrip('/')):
        return 'Please reload this page and try again.', 403
    if (request.files or set(request.form) != fields
            or any(len(request.form.getlist(field)) != 1 for field in fields if field not in repeated)):
        return 'Invalid trip form. Please reload this page and try again.', 400
    return None


def _trip_date(value):
    if value == '':
        return None
    if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            if parsed.isoformat() == value:
                return parsed
    raise TripValidationError() from None


def _trip_page_number(key, maximum):
    values = request.args.getlist(key)
    if not values:
        return 0
    if (len(values) != 1 or not re.fullmatch(r'[0-9]{1,10}', values[0])
            or int(values[0]) > maximum):
        raise TripValidationError()
    return int(values[0])


def _trip_failure(error, *, mutation=False):
    if isinstance(error, TripNotFoundError):
        return 'Trip not found.', 404
    if isinstance(error, TripValidationError):
        return 'Invalid trip input.', 400
    if isinstance(error, TripOperationRejectedError):
        return 'Trip operation was rejected.', 400
    if isinstance(error, TripUnavailableError):
        return (('Your change could not be confirmed. Check your trips before trying again.'
                 if mutation else 'Trips are temporarily unavailable. Please try again later.'), 503)
    if isinstance(error, TripConsistencyError):
        return 'We could not display this page. Please try again later.', 500
    raise error


def _trip_form(template, *, trip_id=None, name='', visit_date='', message='', status=200, add_place_slug=None):
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    return _render_trip_page(template, trip_id=trip_id, name=name, visit_date=visit_date,
                             csrf=csrf, message=message, add_place_slug=add_place_slug), status


def _draft_failure(error, *, mutation=False):
    if isinstance(error, DraftValidationError):
        return 'Invalid itinerary preferences. Please check your entries.', 400
    if isinstance(error, DraftRejectedError):
        return 'This draft cannot be updated. Reload it before trying again.', 409
    if isinstance(error, DraftUnavailableError):
        return (('Your change could not be confirmed. Check your draft before trying again.'
                 if mutation else 'Draft information is temporarily unavailable.'), 503)
    if isinstance(error, DraftConsistencyError):
        return 'We could not display this draft. Please try again later.', 500
    raise error


def _editable_draft(draft_id):
    draft = get_itinerary_draft(g.auth, str(draft_id))
    if draft is None:
        return None, ('Draft not found.', 404)
    if draft.state != 'editing' or draft.expires_at <= datetime.now(timezone.utc):
        return None, ('This draft is no longer editable. Start a new draft from Planner.', 409)
    return draft, None


def _quiz_form(draft, values, revision, *, message='', status=200):
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    return _render_trip_page('itinerary/preferences.html', draft_id=draft.draft_id,
                             revision=revision, values=values, csrf=csrf, message=message,
                             profile_defaults_eligible=request.method == 'GET' and draft.preferences is None,
                             interests=sorted(CATEGORIES), companions=COMPANIONS,
                             transportation=TRANSPORTATION, trip_paces=TRIP_PACES,
                             activities=ACTIVITIES, environments=ENVIRONMENTS), status


@app.route('/user/itinerary/start', methods=['POST'])
@login_required
def itinerary_start():
    failure = _trip_post_check({'csrf_token'})
    if failure:
        return failure
    try:
        draft = create_itinerary_draft(g.auth)
    except DraftError as error:
        return _draft_failure(error, mutation=True)
    return redirect(url_for('itinerary_preferences', draft_id=draft.draft_id), code=303)


@app.route('/user/itinerary/<uuid:draft_id>/preferences', methods=['GET', 'POST'])
@login_required
def itinerary_preferences(draft_id):
    if request.method == 'POST':
        # Only the two controlled checkbox lists may repeat.
        failure = _trip_post_check(set(request.form), repeated=REPEATED_FIELDS)
        if failure:
            return failure
        if (set(request.form) - FORM_FIELDS or FORM_FIELDS - REPEATED_FIELDS - set(request.form)):
            return 'Invalid preference form. Please reload this page and try again.', 400
        try:
            revision = quiz_expected_revision(request.form['expected_revision'])
        except DraftValidationError:
            return 'Invalid draft revision. Please reload this page and try again.', 400
    try:
        draft, failure = _editable_draft(draft_id)
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure
    if request.method == 'GET':
        return _quiz_form(draft, form_values(draft.preferences), draft.revision)
    try:
        revision, preferences = parse_quiz_form(request.form)
    except QuizTimeWindowError:
        return _quiz_form(draft, submitted_values(request.form), revision, status=400,
                          message='End Time must be later than Start Time on the same day. '
                                  'Check AM/PM if your time picker displays it. '
                                  'Overnight daily windows are not supported.')
    except DraftValidationError:
        return _quiz_form(draft, submitted_values(request.form), revision, status=400,
                          message='Check all fields: select 1–6 different interests, a companion type and transport; '
                                  'select pace, environment and 1–6 different activities; limit other interests to 200 '
                                  'characters and additional preferences to 500; use a budget up to PHP 100,000, '
                                  'dates within 7 days, and an end time after the start.')
    try:
        update_itinerary_draft_preferences(g.auth, str(draft_id), revision, preferences)
    except DraftError as error:
        return _draft_failure(error, mutation=True)
    return redirect(url_for('itinerary_review', draft_id=draft_id), code=303)


@app.route('/user/itinerary/<uuid:draft_id>/review', methods=['GET'])
@login_required
def itinerary_review(draft_id):
    try:
        draft, failure = _editable_draft(draft_id)
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure
    if draft.preferences is None:
        return redirect(url_for('itinerary_preferences', draft_id=draft_id), code=303)
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    return _render_trip_page('itinerary/review.html', draft_id=draft.draft_id,
                             revision=draft.revision, values=form_values(draft.preferences), csrf=csrf,
                             no_matches=request.args.getlist('notice') == ['no_matches'])


def _recommendation_data(draft):
    """Reconstruct current eligibility for display and transient selection alike."""
    try:
        preferences = validate_complete_preferences(draft.preferences)
    except DraftValidationError:
        return None, None, None, redirect(url_for('itinerary_preferences', draft_id=draft.draft_id), code=303)
    try:
        places = current_app.extensions['rosago_places'].list_published(limit=MAX_CANDIDATES, offset=0)
        # One bounded query: a short page proves exhaustion for that read. A full
        # page cannot establish completeness, even if there are exactly 100 rows.
        if len(places) >= MAX_CANDIDATES:
            return None, None, None, (_render_trip_page('itinerary/recommendations.html', draft_id=draft.draft_id,
                message='The published catalog has reached the current recommendation limit. '
                        'We cannot show a complete shortlist. Please explore places instead.'), 503)
        result = rank_candidates(preferences, places)
    except (PlacesUnavailableError, PlacesConsistencyError, RecommendationInputError):
        return None, None, None, (_render_trip_page('itinerary/recommendations.html', draft_id=draft.draft_id,
            message='Recommendations are temporarily unavailable. Please try again later.'), 503)
    return places, result, preferences, None


def _recommendation_cards(draft):
    places, result, preferences, failure = _recommendation_data(draft)
    if failure:
        return None, None, failure
    by_id = {place.id: place for place in places}
    cards = tuple(dict(place=by_id[candidate.place_id],
                       candidate=candidate,
                       evidence=tuple(signal.category for signal in candidate.matched_signals
                                      if signal.kind == CATEGORY_INTEREST_MATCH))
                  for candidate in result.matched)
    return cards, preferences, None


@app.route('/user/itinerary/<uuid:draft_id>/recommendations', methods=['GET', 'POST'])
@login_required
def itinerary_recommendations(draft_id):
    if request.method == 'POST':
        failure = _trip_post_check({'csrf_token'})
        if failure:
            return failure
    try:
        draft, failure = _editable_draft(draft_id)
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure
    cards, preferences, failure = _recommendation_cards(draft)
    if failure:
        return failure
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    return _render_recommendations(draft, cards, preferences, csrf)


def _render_recommendations(draft, cards, preferences, csrf, *, assistance=None, ai_error=None):
    counts = request.args.getlist('stops')
    if len(counts) > 1 or (counts and (not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})', counts[0])
                                      or int(counts[0]) > 100)):
        return 'Choose a suggested stop count from 1 to 100, or Auto.', 400
    requested_count = int(counts[0]) if counts else 0
    recommended = select_destinations(preferences, tuple(card['candidate'] for card in cards),
                                      place_count=requested_count or None,
                                      places=tuple(card['place'] for card in cards))
    selected_ids = {candidate.place_id for candidate in recommended}
    by_id = {card['place'].id: card for card in cards}
    primary = tuple(by_id[candidate.place_id] for candidate in recommended)
    alternatives = tuple(card for card in cards if card['place'].id not in selected_ids)[:6]
    return _render_trip_page('itinerary/recommendations.html', draft_id=draft.draft_id,
        message=None, cards=primary, alternatives=alternatives, interests=preferences['interests'],
        trip_pace=preferences['trip_pace'], requested_count=requested_count,
        selected_count=len(primary),
        csrf=csrf, revision=draft.revision,
        pace_count=DESTINATIONS_PER_DAY[preferences['trip_pace']] * (
            (date.fromisoformat(preferences['end_date']) - date.fromisoformat(preferences['start_date'])).days + 1),
        ai_available=current_app.extensions['rosago_gemini'].configured,
        ai_assistance=assistance, ai_error=ai_error,
        has_test_records=any(card['place'].slug.startswith('rosago-test-v1-') for card in cards))


@app.route('/user/itinerary/<uuid:draft_id>/recommendations/explain', methods=['POST'])
@login_required
def itinerary_ai_explain(draft_id):
    failure = _trip_post_check({'csrf_token', 'expected_revision'})
    if failure:
        return failure
    try:
        revision = quiz_expected_revision(request.form['expected_revision'])
        draft, failure = _editable_draft(draft_id)
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure
    if draft.revision != revision:
        return 'Your preferences changed. Reload recommendations before requesting an explanation.', 409
    cards, preferences, failure = _recommendation_cards(draft)
    if failure:
        return failure
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    assistance = current_app.extensions['rosago_gemini'].explain(recommendation_context(preferences, cards))
    return _render_recommendations(draft, cards, preferences, csrf, assistance=assistance,
        ai_error=None if assistance else 'AI explanation is unavailable. Your RosaGo catalog recommendations remain available below.')


def _selection_input():
    """Same strict transient input for Selection Ready and Build Itinerary."""
    # Unchecked checkbox groups submit no field; validate their minimum below.
    fields = {'csrf_token', 'expected_revision'}
    if 'selected_place_ids' in request.form:
        fields.add('selected_place_ids')
    failure = _trip_post_check(fields,
                               repeated={'selected_place_ids'})
    if failure:
        return None, None, failure
    try:
        revision = quiz_expected_revision(request.form['expected_revision'])
    except DraftValidationError:
        return None, None, ('Invalid draft revision. Please reload this page and try again.', 400)
    selected = request.form.getlist('selected_place_ids')
    if not 1 <= len(selected) <= MAX_CANDIDATES or len(set(selected)) != len(selected):
        return None, None, ('Select between 1 and 100 different recommended destinations.', 400)
    for identity in selected:
        try:
            canonical = str(UUID(identity))
        except ValueError:
            return None, None, ('Invalid destination selection. Reload recommendations and try again.', 400)
        if canonical != identity:
            return None, None, ('Invalid destination selection. Reload recommendations and try again.', 400)
    return revision, set(selected), None


def _selected_places(draft, selected_ids):
    cards, preferences, failure = _recommendation_cards(draft)
    if failure:
        return None, None, failure
    if not selected_ids <= {card['place'].id for card in cards}:
        return None, None, ('Your selection is not in the current recommendations. Return to Review and reload recommendations.', 409)
    return order_places(tuple(card['place'] for card in cards if card['place'].id in selected_ids)), preferences, None


@app.route('/user/itinerary/<uuid:draft_id>/selection', methods=['POST'])
@login_required
def itinerary_selection(draft_id):
    revision, selected_ids, failure = _selection_input()
    if failure:
        return failure
    try:
        draft, failure = _editable_draft(draft_id)
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure
    if revision != draft.revision:
        return 'Your preferences have changed. Return to Review and reload recommendations.', 409
    places, _, failure = _selected_places(draft, selected_ids)
    if failure:
        return failure
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    return _render_trip_page('itinerary/selection.html', draft_id=draft.draft_id,
                             places=places, csrf=csrf, revision=draft.revision)


def _preview_draft(draft_id, required_state):
    # The service enforces ownership and parses the stored versioned contract.
    draft = get_itinerary_preview_draft(g.auth, str(draft_id))
    if draft is None:
        return None, ('Draft not found.', 404)
    if draft.expires_at <= datetime.now(timezone.utc) or draft.state != required_state:
        return None, ('This draft is not available for this action. Return to Planner or reload your draft.', 409)
    return draft, None


@app.route('/user/itinerary/<uuid:draft_id>/preview', methods=['POST'])
@login_required
def itinerary_preview_build(draft_id):
    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return 'Please reload this page and try again.', 403
    revision, selected_ids, failure = _selection_input()
    if failure:
        return failure
    try:
        draft, failure = _preview_draft(draft_id, 'editing')
        if failure:
            return failure
        if revision != draft.revision:
            return 'Your draft has changed. Reload recommendations before building a preview.', 409
        places, preferences, failure = _selected_places(draft, selected_ids)
        if failure:
            return failure
    except DraftError as error:
        return _draft_failure(error)
    return _store_preview_response(draft, revision, places, preferences)


def _store_preview_response(draft, revision, places, preferences):
    """One existing adapter/store pipeline for automatic and legacy selection."""
    try:
        candidate = build_personalized_preview(
            preferences=preferences, selected_places=places,
            selected_place_ids=tuple(place.id for place in places),
            draft_id=draft.draft_id, draft_revision=draft.revision,
            publication_confirmed=True).to_document()
        store_itinerary_draft_preview(g.auth, draft.draft_id, revision, candidate)
    except PreviewContractError:
        return 'We could not prepare this preview. Return to Review and try again.', 409
    except DraftValidationError:
        return 'This preview could not be stored. Return to Review and try again.', 400
    except DraftError as error:
        return _draft_failure(error, mutation=True)
    return redirect(url_for('itinerary_preview_page', draft_id=draft.draft_id), code=303)


@app.route('/user/itinerary/<uuid:draft_id>/generate', methods=['POST'])
@login_required
def itinerary_generate(draft_id):
    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return 'Please reload this page and try again.', 403
    failure = _trip_post_check({'csrf_token', 'expected_revision'})
    if failure:
        return failure
    try:
        revision = quiz_expected_revision(request.form['expected_revision'])
    except DraftValidationError:
        return 'Invalid draft revision. Please reload this page and try again.', 400
    try:
        draft, failure = _preview_draft(draft_id, 'editing')
        if failure:
            return failure
        if revision != draft.revision:
            return 'Your preferences have changed. Return to Review before generating a preview.', 409
        catalog, result, preferences, failure = _recommendation_data(draft)
        if failure:
            return failure
        selected = select_destinations(preferences, result.matched, places=catalog)
        if not selected:
            return redirect(url_for('itinerary_review', draft_id=draft_id, notice='no_matches'), code=303)
        by_id = {place.id: place for place in catalog}
        places = tuple(by_id[candidate.place_id] for candidate in selected)
    except SelectionPolicyError:
        return 'We could not select destinations. Please return to Review and try again.', 409
    except DraftError as error:
        return _draft_failure(error)
    return _store_preview_response(draft, revision, places, preferences)


@app.route('/user/itinerary/<uuid:draft_id>/preview', methods=['GET'])
@login_required
def itinerary_preview_page(draft_id):
    try:
        draft, failure = _preview_draft(draft_id, 'preview_ready')
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure
    return _render_personalized_preview(draft)


@app.route('/user/itinerary/<uuid:draft_id>/preview/explain', methods=['POST'])
@login_required
def itinerary_preview_explain(draft_id):
    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return 'Please reload this page and try again.', 403
    request.max_content_length = 4096
    failure = _trip_post_check({'csrf_token', 'expected_revision'})
    if failure:
        return failure
    try:
        revision = quiz_expected_revision(request.form['expected_revision'])
        draft, failure = _preview_draft(draft_id, 'preview_ready')
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure
    if revision != draft.revision:
        return _render_personalized_preview(draft, response_status=409,
            ai_error='Your preview changed. Review the current preview before requesting an explanation.')
    return _render_personalized_preview(draft, request_explanation=True)


@app.route('/user/itinerary/<uuid:draft_id>/preview/adjust', methods=['POST'])
@login_required
def itinerary_preview_adjust(draft_id):
    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return 'Please reload this page and try again.', 403
    request.max_content_length = 8192
    failure = _trip_post_check({'csrf_token', 'expected_revision', 'message'})
    if failure:
        return failure
    try:
        revision = quiz_expected_revision(request.form['expected_revision'])
        adjustment_message = validate_message(request.form['message'])
    except (DraftValidationError, ValueError):
        return 'Enter a message of 1–1000 characters and a valid draft revision.', 400
    try:
        draft, failure = _preview_draft(draft_id, 'preview_ready')
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure

    def unchanged(text, status=200):
        return _render_personalized_preview(draft, adjustment_status=text, response_status=status)

    if revision != draft.revision:
        return unchanged('Your preview changed. Review it before submitting another adjustment.', 409)
    try:
        draft.preview.to_document()
        catalog = current_app.extensions['rosago_places'].list_published(limit=MAX_CANDIDATES, offset=0)
        if len(catalog) >= MAX_CANDIDATES:
            return unchanged('The complete published catalog cannot be verified. No adjustment was made.', 503)
        by_id = {place.id: place for place in catalog}
        ids = draft.preview.source.selected_place_ids
        selected = tuple(by_id[identity] for identity in ids if identity in by_id)
        if (len(selected) != len(ids) or compute_catalog_fingerprint(
                selected, publication_confirmed=True) != draft.preview.source.catalog_fingerprint):
            return unchanged('Selected destination information changed. Edit Preferences to regenerate.', 409)
        provider = current_app.extensions['rosago_gemini']
        interpretation = provider.interpret_adjustment(adjustment_message) if provider.configured else None
        if interpretation is None:
            return unchanged('The adjustment service is unavailable. Your itinerary has not changed. Try again later.')
        try:
            interpretation = validate_adjustment(interpretation)
        except ValueError:
            return unchanged('The request could not be safely interpreted. Please specify category interests, pace or destination count.')
        disclosure = ' '.join(UNSUPPORTED[key] for key in interpretation['unsupported_requests'])
        if interpretation['intent'] == 'clarify':
            return unchanged('Please be more specific about the category interests, pace or destination count to change. ' + disclosure)
        changes = interpretation['changes']
        if not any((changes['set_interests'], changes['add_interests'], changes['remove_interests'],
                    changes['pace'] is not None, changes['place_count'] is not None)):
            return unchanged((disclosure or 'No supported change was requested.') + ' Your itinerary has not changed.')
        try:
            preferences = adjusted_preferences(draft.preferences, interpretation)
        except DraftValidationError:
            return unchanged('Keep at least one and at most six category interests. Your itinerary has not changed. ' + disclosure)
        result = rank_candidates(preferences, catalog)
        # Category changes retain the current total count. An explicit pace resets
        # to the established per-day policy; an explicit total count takes priority.
        count = changes['place_count']
        if count is None and changes['pace'] is None:
            count = len(ids)
        candidates = select_destinations(preferences, result.matched, place_count=count, places=catalog)
        if not candidates:
            return unchanged('No matching published destinations were found. Your itinerary has not changed. ' + disclosure)
        places = tuple(by_id[candidate.place_id] for candidate in candidates)
        candidate = build_personalized_preview(preferences=preferences, selected_places=places,
            selected_place_ids=tuple(place.id for place in places), draft_id=draft.draft_id,
            draft_revision=revision, publication_confirmed=True)
    except (PlacesUnavailableError, PlacesConsistencyError, PreviewContractError,
            RecommendationInputError, SelectionPolicyError):
        return unchanged('Destination information could not be verified. No adjustment was made.', 503)
    try:
        adjust_itinerary_draft_preview(g.auth, draft.draft_id, revision, preferences, candidate.to_document())
    except DraftError as error:
        return _draft_failure(error, mutation=True)
    # Read the committed revision, never construct an authoritative draft in HTTP.
    try:
        revised, failure = _preview_draft(draft_id, 'preview_ready')
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure
    text = f"Updated to {len(places)} {'destination' if len(places) == 1 else 'destinations'}."
    if changes['set_interests'] is not None or changes['add_interests'] or changes['remove_interests']:
        text += ' Category interests: ' + ', '.join(preferences['interests']) + '.'
    if changes['pace'] is not None:
        text += ' Pace: ' + preferences['trip_pace'] + '.'
    if changes['place_count'] is not None and len(places) < changes['place_count']:
        text += ' Fewer matching published destinations were available than requested.'
    return _render_personalized_preview(revised, adjustment_status=text + ' ' + disclosure)


def _render_personalized_preview(draft, *, request_explanation=False, ai_error=None, response_status=200,
                               adjustment_status=None, suppress_weather_proposal=False):
    # Reader already validated the contract. Revalidation catches inconsistent
    # models without generating a new candidate or changing the stored plan.
    try:
        draft.preview.to_document()
    except (PreviewContractError, AttributeError):
        return 'We could not display this preview. Please reload your draft.', 500
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    message, status = None, response_status
    assistance = None
    days = ()
    try:
        catalog = current_app.extensions['rosago_places'].list_published(limit=MAX_CANDIDATES, offset=0)
        if len(catalog) >= MAX_CANDIDATES:
            message, status = 'We cannot verify the complete destination catalog right now. Your preview has not changed.', 503
        else:
            by_id = {place.id: place for place in catalog}
            ids = draft.preview.source.selected_place_ids
            selected = tuple(by_id[identity] for identity in ids if identity in by_id)
            if (len(selected) != len(ids) or compute_catalog_fingerprint(
                    selected, publication_confirmed=True) != draft.preview.source.catalog_fingerprint):
                message, status = 'A selected destination has changed or is no longer available. Edit Preferences, then generate a new preview.', 409
            else:
                days = tuple(dict(date=day.date, stops=tuple(
                    dict(order=stop.order, place=by_id[stop.place_id]) for stop in day.stops))
                    for day in draft.preview.plan.days)
    except (PlacesUnavailableError, PlacesConsistencyError, PreviewContractError):
        message, status = 'Destination information is temporarily unavailable. Your preview has not changed.', 503
    provider = current_app.extensions['rosago_gemini']
    if request_explanation and message is None:
        if provider.configured:
            # Stored selection order is authoritative. Never rank, select, build,
            # or write a draft while explaining it; the browser supplies no IDs.
            cards = tuple(dict(place=place) for place in selected)
            context = recommendation_context(draft.preferences, cards)
            context['selection_scope'] = 'Only the stored preview destinations, in their existing order.'
            context['selection_method'] = ('Deterministic category-interest matches with a pace-based '
                'destination count. Pace does not establish time feasibility. '
                'Costs, hours, travel feasibility and transport compatibility were not evaluated.')
            assistance = provider.explain(context, per_destination=True)
        if assistance is None:
            ai_error = 'AI explanation is currently unavailable. Your itinerary remains unchanged and usable.'
    weather_review, weather_metadata, weather_proposal, weather_token = (None, None, None, None)
    if message is None:
        weather_review, weather_metadata, weather_proposal, weather_token = _weather_preview_state(draft, catalog, days)
    return _render_trip_page('itinerary/preview.html', draft_id=draft.draft_id,
        preview_interests=draft.preferences.get('interests', ()),
        revision=draft.revision, csrf=csrf, days=days, message=message,
        ai_available=provider.configured, ai_error=ai_error,
        ai_requested=request_explanation,
        adjustment_status=adjustment_status,
        itinerary_weather=weather_review,
        weather_metadata_verified=bool(weather_metadata and any(
            weather_metadata.for_place(place).exposure != 'unknown' for place in catalog)),
        weather_proposal=weather_proposal if not suppress_weather_proposal else None,
        weather_proposal_token=weather_token if not suppress_weather_proposal else None,
        ai_explanations={entry['place_id']: entry['reason']
                         for entry in assistance['explanations']} if assistance else {},
        constraints=draft.preview.plan.constraints, day_count=len(draft.preview.plan.days),
        destination_count=len(draft.preview.source.selected_place_ids),
        has_test_records=any(stop['place'].slug.startswith('rosago-test-v1-')
                             for day in days for stop in day['stops'])), status


def _preview_weather_review(draft, days):
    if not get_settings(session).show_weather:
        return None
    now = manila_now()
    if not before_requested_start(draft.preview.plan.constraints, now):
        return ForecastReview(pretrip=False)
    dates = tuple(day['date'] for day in days if day['stops'])
    weather = current_app.extensions['rosago_weather'].get_weather()
    return forecast_review(weather, dates, now=now)


WEATHER_PROPOSAL_MAX_AGE = 600


def _weather_signer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='rosago-weather-proposal-v1')


def _weather_owner_binding():
    return hmac.new(current_app.config['SECRET_KEY'].encode('utf-8'),
                    g.auth.user_id.encode('utf-8'), hashlib.sha256).hexdigest()


def _weather_preview_state(draft, catalog, days):
    review = _preview_weather_review(draft, days)
    metadata = load_weather_catalog()
    proposal = build_weather_proposal(draft.preferences, days, catalog, review, metadata)
    token = None
    if proposal and proposal.replacements:
        token = _weather_signer().dumps(dict(owner=_weather_owner_binding(),
            binding=proposal_binding(draft, catalog, metadata, review, proposal)))
    return review, metadata, proposal, token


@app.route('/user/itinerary/<uuid:draft_id>/preview/weather', methods=['POST'])
@login_required
def itinerary_preview_weather(draft_id):
    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return 'Please reload this page and try again.', 403
    request.max_content_length = 4096
    failure = _trip_post_check({'csrf_token', 'expected_revision', 'proposal_token', 'decision'})
    if failure:
        return failure
    try:
        revision = quiz_expected_revision(request.form['expected_revision'])
    except DraftValidationError:
        return 'Invalid draft revision. Please reload this page.', 400
    if request.form['decision'] not in ('keep', 'accept') or not 1 <= len(request.form['proposal_token']) <= 2000:
        return 'Invalid weather proposal. Please reload this page.', 400
    try:
        draft, failure = _preview_draft(draft_id, 'preview_ready')
    except DraftError as error:
        return _draft_failure(error)
    if failure:
        return failure

    def rejected():
        return _render_personalized_preview(draft, response_status=409,
            adjustment_status='This weather suggestion is stale or no longer valid. Review the latest Preview before deciding.')

    if draft.revision != revision:
        return rejected()
    try:
        approved = _weather_signer().loads(request.form['proposal_token'], max_age=WEATHER_PROPOSAL_MAX_AGE)
        if (type(approved) is not dict or set(approved) != {'owner', 'binding'}
                or type(approved['owner']) is not str or type(approved['binding']) is not str
                or not secrets.compare_digest(approved['owner'], _weather_owner_binding())):
            return rejected()
    except (BadSignature, SignatureExpired):
        return rejected()
    if request.form['decision'] == 'keep':
        return _render_personalized_preview(draft, adjustment_status='Current itinerary kept. No destinations were changed.',
                                           suppress_weather_proposal=True)
    try:
        draft.preview.to_document()
        catalog = current_app.extensions['rosago_places'].list_published(limit=MAX_CANDIDATES, offset=0)
        if len(catalog) >= MAX_CANDIDATES:
            return rejected()
        by_id = {place.id: place for place in catalog}
        ids = draft.preview.source.selected_place_ids
        selected = tuple(by_id[identity] for identity in ids if identity in by_id)
        if (len(selected) != len(ids) or compute_catalog_fingerprint(selected, publication_confirmed=True)
                != draft.preview.source.catalog_fingerprint):
            return rejected()
        days = tuple(dict(date=day.date, stops=tuple(dict(order=stop.order, place=by_id[stop.place_id])
            for stop in day.stops)) for day in draft.preview.plan.days)
        review, metadata, proposal, _ = _weather_preview_state(draft, catalog, days)
        if not proposal or not proposal.replacements:
            return rejected()
        expected = proposal_binding(draft, catalog, metadata, review, proposal)
        if not secrets.compare_digest(approved['binding'], expected):
            return rejected()
        # Acceptance rebuilds only the recomputed, approved server proposal. The
        # browser sends no destination IDs and preferences remain identical.
        candidate = build_personalized_preview(preferences=draft.preferences,
            selected_places=proposal.places, selected_place_ids=tuple(place.id for place in proposal.places),
            draft_id=draft.draft_id, draft_revision=revision, publication_confirmed=True)
    except (PlacesUnavailableError, PlacesConsistencyError, PreviewContractError, RecommendationInputError, ValueError):
        return rejected()
    try:
        adjust_itinerary_draft_preview(g.auth, draft.draft_id, revision, draft.preferences, candidate.to_document())
        revised, failure = _preview_draft(draft_id, 'preview_ready')
    except DraftError as error:
        return _draft_failure(error, mutation=True)
    if failure:
        return failure
    return _render_personalized_preview(revised, adjustment_status=
        'Weather suggestion applied after your approval. Review the revised destinations; '
        'costs, opening hours, routes and travel feasibility were not evaluated. Request Explain with AI again if wanted.')


@app.route('/user/itinerary/<uuid:draft_id>/preview/edit', methods=['POST'])
@login_required
def itinerary_preview_edit(draft_id):
    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return 'Please reload this page and try again.', 403
    failure = _trip_post_check({'csrf_token', 'expected_revision'})
    if failure:
        return failure
    try:
        revision = quiz_expected_revision(request.form['expected_revision'])
    except DraftValidationError:
        return 'Invalid draft revision. Please reload this page and try again.', 400
    try:
        draft, failure = _preview_draft(draft_id, 'preview_ready')
        if failure:
            return failure
        if revision != draft.revision:
            return 'Your draft has changed. Reload the preview before returning to edit.', 409
        return_itinerary_draft_to_editing(g.auth, draft.draft_id, revision)
    except DraftError as error:
        return _draft_failure(error, mutation=True)
    return redirect(url_for('itinerary_preferences', draft_id=draft_id), code=303)


@app.route('/user/trips', methods=['GET'])
@login_required
def trips_list():
    try:
        offset = _trip_page_number('offset', 2147483647 - 49)
        trips = list_user_trips(g.auth, limit=50, offset=offset)
    except TripServiceError as error:
        return _trip_failure(error)
    next_offset = offset + len(trips) if len(trips) == 50 and offset + 50 <= 2147483647 - 49 else None
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    return _render_trip_page('trips/list.html', trips=trips, offset=offset, next_offset=next_offset, csrf=csrf)


@app.route('/user/trips/add-place/<slug>', methods=['GET', 'POST'])
@login_required
def trips_add_place(slug):
    dialog_request = request.accept_mimetypes.best == 'application/json'
    if request.method == 'POST':
        failure = _trip_post_check({'csrf_token', 'trip_id'})
        if failure is not None:
            return failure
        supplied_id = request.form['trip_id']
        try:
            trip_id = str(UUID(supplied_id))
        except ValueError:
            return _trip_failure(TripValidationError())
        if supplied_id.lower() != trip_id:
            return _trip_failure(TripValidationError())
    else:
        try:
            offset = _trip_page_number('offset', 2147483647 - 49)
        except TripValidationError as error:
            return _trip_failure(error)

    try:
        place = current_app.extensions['rosago_places'].get_published_by_slug(slug)
    except PlacesValidationError:
        return 'Place not found.', 404
    except PlacesUnavailableError:
        return 'Places are temporarily unavailable.', 503
    except PlacesConsistencyError:
        return 'Unable to display places.', 500
    if place is None:
        return 'Place not found.', 404

    if request.method == 'POST':
        try:
            detail = get_user_trip(g.auth, trip_id) if dialog_request else None
            if dialog_request and detail is None:
                return _trip_failure(TripNotFoundError())
            add_place(g.auth, trip_id, place.id)
        except TripOperationRejectedError as error:
            if dialog_request:
                # Confirm a duplicate from owned membership data, never from
                # a provider error string. The atomic RPC remains authoritative.
                try:
                    while detail is not None:
                        if any(member.place_id == place.id for member in detail.memberships):
                            return jsonify(message=f'This destination is already in {detail.trip.name}.'), 409
                        if detail.next_after_position is None:
                            break
                        detail = get_user_trip(g.auth, trip_id, after_position=detail.next_after_position)
                except TripServiceError:
                    pass
            return _trip_failure(error, mutation=True)
        except TripServiceError as error:
            return _trip_failure(error, mutation=True)
        if dialog_request:
            return jsonify(message=f'Added {place.name} to {detail.trip.name}.', trip_id=trip_id)
        return redirect(url_for('trips_detail', trip_id=trip_id), code=303)

    try:
        trips = list_user_trips(g.auth, limit=50, offset=offset)
    except TripServiceError as error:
        return _trip_failure(error)
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    next_offset = offset + len(trips) if len(trips) == 50 and offset + 50 <= 2147483647 - 49 else None
    if dialog_request:
        return jsonify(csrf_token=csrf, place=dict(name=place.name, category=place.category, address=place.address),
            trips=[dict(id=trip.id, name=trip.name,
                date_label=trip.visit_date.strftime('%b %d, %Y') if trip.visit_date else 'Date not set') for trip in trips],
            next_url=url_for('trips_add_place', slug=place.slug, offset=next_offset) if next_offset is not None else None,
            create_url=url_for('trips_create'), new_url=url_for('trips_new', add_place=place.slug))
    return _render_trip_page('trips/add_place.html', place=place, trips=trips,
                             csrf=csrf, offset=offset, next_offset=next_offset)


@app.route('/user/trips/new', methods=['GET'])
@login_required
def trips_new():
    return _trip_form('trips/new.html', add_place_slug=_login_trip_destination())


@app.route('/user/planner', methods=['GET'])
@login_required
def planner():
    return _trip_form('user/planner.html')


@app.route('/user/transport', methods=['GET'])
@login_required
def transport():
    return redirect(url_for('map_index'), code=302)


@app.route('/user/alerts', methods=['GET'])
@login_required
def alerts():
    now = manila_now()
    today = now.date()
    preferences = get_settings(session)
    upcoming, trips_unavailable = (), False
    if preferences.show_trips:
        try:
            upcoming = list_upcoming_trips(g.auth, today=today, days=TRIP_HORIZON_DAYS, limit=51)
        except TripServiceError:
            trips_unavailable = True
    weather = current_app.extensions['rosago_weather'].get_weather() if preferences.show_weather else None
    weather_metadata = load_weather_catalog() if preferences.show_weather else None
    return _render_trip_page('user/alerts.html', weather=weather,
        notifications=alerts_notification_cards(weather, upcoming[:50], now=now),
        weather_metadata_verified=bool(weather_metadata and any(
            row[3].exposure != 'unknown' for row in weather_metadata.records.values())),
        trip_weather_reviews=tuple(dict(trip=trip, review=forecast_review(weather, (trip.visit_date,), now=now))
            for trip in upcoming[:50] if trip.visit_date > today)
            if preferences.show_weather and preferences.show_trips else (),
        show_weather=preferences.show_weather, show_trip_reminders=preferences.show_trips,
        weather_reminders=weather_alerts(weather),
        trip_reminders=trip_alerts(upcoming[:50], today=today), trips_unavailable=trips_unavailable,
        more_trips=len(upcoming) > 50, reminder_start=today,
        reminder_end=date.fromordinal(min(date.max.toordinal(), today.toordinal() + TRIP_HORIZON_DAYS)))


def _assistant_key():
    return (g.auth.user_id, g.auth.auth_session_id)


def _assistant_page(*, message='', error=None, status=200):
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    history = current_app.extensions['rosago_assistant'].snapshot(_assistant_key())
    return _render_trip_page('user/assistant.html', history=history, csrf=csrf,
        message=message, error=error, ai_available=current_app.extensions['rosago_gemini'].configured), status


@app.route('/user/assistant', methods=['GET', 'POST'])
@login_required
def assistant():
    if request.method == 'GET':
        return _assistant_page()
    from werkzeug.exceptions import RequestEntityTooLarge
    request.max_content_length = 16_384
    try:
        failure = _trip_post_check({'csrf_token', 'message'})
    except RequestEntityTooLarge:
        return _assistant_page(error='Your message is too large. Use at most 1000 characters.', status=400)
    if failure:
        return failure
    try:
        message = validate_message(request.form['message'])
    except ValueError:
        return _assistant_page(error='Enter a message of 1–1000 characters.', status=400)
    provider = current_app.extensions['rosago_gemini']
    if not provider.configured:
        return _assistant_page(message=message, error='The AI assistant is unavailable until Gemini is configured. Explore and Planner remain available.', status=503)
    store, key = current_app.extensions['rosago_assistant'], _assistant_key()
    try:
        token, history = store.begin(key)
    except ChatBusy:
        return _assistant_page(message=message, error='A reply is already in progress. Please wait and try again.', status=429)
    try:
        try:
            places = current_app.extensions['rosago_places'].list_published(limit=50, offset=0)
        except (PlacesUnavailableError, PlacesConsistencyError):
            return _assistant_page(message=message, error='The destination catalog is temporarily unavailable. Please try again later.', status=503)
        include_weather = weather_requested(message, history)
        weather = current_app.extensions['rosago_weather'].get_weather() if include_weather else None
        try:
            context = chat_context(message, history, places, current_app.extensions['rosago_routing'],
                                   weather, include_weather=include_weather)
        except ValueError:
            return _assistant_page(message=message, error='This conversation is too large. Clear it and try a shorter question.', status=400)
        result = provider.chat(context)
        if result is None:
            return _assistant_page(message=message, error='The AI assistant could not reply right now. Please try again later; Explore and Planner remain available.', status=503)
        by_id = {place.id: place for place in places}
        sources = tuple((by_id[identity].name, by_id[identity].slug) for identity in result['destination_ids'])
        store.complete(key, token, message, result['answer'], sources)
        return redirect(url_for('assistant'), code=303)
    finally:
        store.cancel(key, token)


@app.route('/user/assistant/clear', methods=['POST'])
@login_required
def assistant_clear():
    failure = _trip_post_check({'csrf_token'})
    if failure:
        return failure
    current_app.extensions['rosago_assistant'].clear(_assistant_key())
    return redirect(url_for('assistant'), code=303)


def _settings_page(*, error=None, status=200):
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    return _render_trip_page('user/settings.html', preferences=get_settings(session),
        display_options=ALERT_DISPLAY_OPTIONS, csrf=csrf, error=error), status


@app.route('/user/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'GET':
        return _settings_page()
    from werkzeug.exceptions import RequestEntityTooLarge
    request.max_content_length = 4096
    try:
        modern = set(request.form) == {'csrf_token', 'alerts_display', 'personalized', 'location_enabled'}
        failure = _trip_post_check({'csrf_token', 'alerts_display', 'personalized', 'location_enabled'} if modern else {'csrf_token', 'alerts_display'})
    except RequestEntityTooLarge:
        return _settings_page(error='Invalid or oversized settings form.', status=400)
    if failure:
        if failure[1] == 400:
            return _settings_page(error='Unsupported or invalid settings form.', status=400)
        return failure
    try:
        previous = get_settings(session)
        values = {'alerts_display': request.form['alerts_display'], 'personalized': previous.personalized, 'location_enabled': previous.location_enabled}
        if modern:
            if any(request.form[key] not in ('true', 'false') for key in ('personalized', 'location_enabled')):
                raise SettingsValidationError()
            values.update({key: request.form[key] == 'true' for key in ('personalized', 'location_enabled')})
        preferences = validate_settings(values)
    except SettingsValidationError:
        return _settings_page(error='Choose a supported Alerts display option.', status=400)
    session[SETTINGS_SESSION_KEY] = {'alerts_display': preferences.alerts_display, 'personalized': preferences.personalized, 'location_enabled': preferences.location_enabled}
    flash('Settings updated successfully.', 'settings_success')
    return redirect(url_for('settings'), code=303)


@app.route('/user/trips', methods=['POST'])
@login_required
def trips_create():
    failure = _trip_post_check({'csrf_token', 'name', 'visit_date'})
    if failure is not None:
        return failure
    continuation = request.args.getlist('add_place')
    add_place_slug = continuation[0] if (len(continuation) == 1 and len(continuation[0]) <= 120
        and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', continuation[0])) else None
    try:
        visit_date = _trip_date(request.form['visit_date'])
        trip = create_trip(g.auth, name=request.form['name'], visit_date=visit_date)
    except TripValidationError:
        return _trip_form('trips/new.html', name=request.form['name'], visit_date=request.form['visit_date'],
                          message='Use a name of 1–100 characters without control characters and an optional date in YYYY-MM-DD format.', status=400,
                          add_place_slug=add_place_slug)
    except TripServiceError as error:
        return _trip_failure(error, mutation=True)
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(trip=dict(id=trip.id, name=trip.name,
            date_label=trip.visit_date.strftime('%b %d, %Y') if trip.visit_date else 'Date not set')), 201
    return redirect(url_for('trips_add_place', slug=add_place_slug) if add_place_slug
                    else url_for('trips_detail', trip_id=trip.id), code=303)


@app.route('/user/trips/<uuid:trip_id>', methods=['GET'])
@login_required
def trips_detail(trip_id):
    try:
        after = _trip_page_number('after_position', 2147483647)
        detail = get_user_trip(g.auth, str(trip_id), membership_limit=50, after_position=after)
    except TripServiceError as error:
        return _trip_failure(error)
    if detail is None:
        return 'Trip not found.', 404
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    return _render_trip_page('trips/detail.html', detail=detail, csrf=csrf, after_position=after)


@app.route('/user/trips/<uuid:trip_id>/edit', methods=['GET'])
@login_required
def trips_edit(trip_id):
    try:
        detail = get_user_trip(g.auth, str(trip_id))
    except TripServiceError as error:
        return _trip_failure(error)
    if detail is None:
        return 'Trip not found.', 404
    trip = detail.trip
    return _trip_form('trips/edit.html', trip_id=trip.id, name=trip.name,
                      visit_date=trip.visit_date.isoformat() if trip.visit_date else '')


@app.route('/user/trips/<uuid:trip_id>/edit', methods=['POST'])
@login_required
def trips_update(trip_id):
    failure = _trip_post_check({'csrf_token', 'name', 'visit_date'})
    if failure is not None:
        return failure
    try:
        visit_date = _trip_date(request.form['visit_date'])
        update_trip(g.auth, str(trip_id), name=request.form['name'], visit_date=visit_date)
    except TripValidationError:
        return _trip_form('trips/edit.html', trip_id=str(trip_id), name=request.form['name'],
                          visit_date=request.form['visit_date'],
                          message='Use a name of 1–100 characters without control characters and an optional date in YYYY-MM-DD format.', status=400)
    except TripServiceError as error:
        return _trip_failure(error, mutation=True)
    return redirect(url_for('trips_detail', trip_id=str(trip_id)), code=303)


@app.route('/user/trips/<uuid:trip_id>/delete', methods=['POST'])
@login_required
def trips_delete(trip_id):
    failure = _trip_post_check({'csrf_token'})
    if failure is not None:
        return failure
    try:
        delete_trip(g.auth, str(trip_id))
    except TripServiceError as error:
        return _trip_failure(error, mutation=True)
    return redirect(url_for('trips_list'), code=303)


@app.route("/logout", methods=["POST"])
def logout():
    if not validate_user_logout_csrf():
        response = app.make_response(('Please reload this page and try again.', 403))
        response.headers['Cache-Control'] = 'no-store'
        return response
    try:
        confirmed = logout_normal_session()
        # Preserve the existing whole-application browser logout, including recovery.
        session.clear()
        if confirmed is False:
            return 'Signed out of RosaGo. Provider session revocation is not yet confirmed.', 503, {'Cache-Control':'no-store'}
    except Exception:
        response = app.make_response(("Logout could not be completed. Please try again.", 503))
        response.headers["Cache-Control"] = "no-store"
        return response
    response = redirect(url_for("login", logged_out="1"), code=303)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get('/auth/logout-token')
def user_logout_token():
    response = jsonify(csrf_token=user_logout_csrf(resolve=True))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


@app.route("/auth/status")
def auth_status():
    decision = normal_auth_state()
    if decision.state == "authenticated":
        response = jsonify(authenticated=True, email=decision.user_email)
    elif decision.state == "unauthenticated":
        response = jsonify(authenticated=False)
    else:
        response = jsonify(error="Authentication is temporarily unavailable. Please try again.")
        response.status_code = 503
        response.headers["Retry-After"] = "1"
    response.headers["Cache-Control"] = "no-store"
    return response


def registration_pending_response(email):
    handle = current_app.extensions['rosago_email_pending'].create(email)
    if handle is None:
        return 'Verification is temporarily unavailable. Please try again later.', 503
    session['pending_email_verification'] = handle
    return redirect(url_for('verify_email'), code=303)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == 'POST' and not email_form_origin_allowed():
        return 'Please reload this page and try again.', 403
    response = normal_auth_page_check("auth/register.html")
    if response is not None:
        return response

    form_data = {}
    field_errors = {}
    message = ""
    state = ""
    status = 200

    if request.method == "POST":
        form_data = {
            "first_name": request.form.get("first_name", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "terms": request.form.getlist("terms") == ["accepted"],
        }
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        for field, label in (("first_name", "first name"), ("last_name", "last name")):
            if not form_data[field]:
                field_errors[field] = f"Please enter your {label}."
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", form_data["email"]):
            field_errors['email'] = "Please enter a valid email address."
        if not password.strip():
            field_errors['password'] = "Please enter a password."
        else:
            policy_error = password_error(password)
            if policy_error:
                field_errors['password'] = policy_error
        if not confirm_password.strip():
            field_errors['confirm_password'] = "Please confirm your password."
        elif password != confirm_password:
            field_errors['confirm_password'] = "Passwords do not match."
        if not form_data["terms"]:
            field_errors['terms'] = "Please agree to the Terms and Privacy Policy."

        state = "error"
        if field_errors:
            status = 400
        else:
            if not email_attempt_allowed('registration'):
                return 'Too many requests. Please wait before trying again.', 429, {'Retry-After': '60'}
            try:
                # Only these two metadata fields are accepted from public registration.
                supabase.auth.sign_up({
                    "email": form_data["email"],
                    "password": password,
                    "options": {
                        "data": {
                            "first_name": form_data["first_name"],
                            "last_name": form_data["last_name"],
                        },
                        "email_redirect_to": PUBLIC_ORIGIN + '/auth/callback',
                    },
                })
            except AuthApiError as error:
                if error.code in ('user_already_exists', 'email_exists'):
                    # Match accepted registration navigation; don't disclose existence.
                    return registration_pending_response(form_data['email'])
                messages = {
                    "email_address_invalid": "Please enter a valid email address.",
                    "email_address_not_authorized": "We cannot send a verification email to this address right now. Please contact support.",
                    "weak_password": "Please choose a stronger password with a mix of letters, numbers, and symbols.",
                    "over_email_send_rate_limit": "Too many verification emails have been requested. Please wait before trying again.",
                    "over_request_rate_limit": "Too many attempts. Please wait before trying again.",
                    "signup_disabled": "Registration is temporarily unavailable. Please try again later.",
                    "email_provider_disabled": "Email registration is temporarily unavailable. Please try again later.",
                }
                message = messages.get(error.code, "We could not complete registration. Please try again later.")
                status = 429 if error.status == 429 else 400
            except Exception:
                # Never render or log raw provider errors, which may contain sensitive data.
                message = "We could not reach the registration service. Please try again later."
                status = 503
            else:
                return registration_pending_response(form_data['email'])

    return render_template(
        "auth/register.html", form_data=form_data, message=message, state=state,
        field_errors=field_errors
    ), status


def _email_verification_page(*, message='', status=200, retry_after=None):
    store = current_app.extensions['rosago_email_pending']
    record = store.get(session.get('pending_email_verification'))
    response = current_app.make_response((render_template('auth/verify_email.html',
        pending=record is not None, verified=bool(record and record.verified),
        csrf=record.csrf if record else '', cooldown=store.seconds(record) if record else 0,
        message=message), status))
    if retry_after:
        response.headers['Retry-After'] = str(retry_after)
    return response


@app.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    return _email_verification_action('verify') if request.method == 'POST' else _email_verification_page()


@app.route('/verify-email/resend', methods=['POST'])
def resend_verification():
    return _email_verification_action('resend')


def _email_verification_action(action):
    request.max_content_length = 4096
    store = current_app.extensions['rosago_email_pending']
    handle = session.get('pending_email_verification')
    record = store.get(handle)
    if record is None:
        return _email_verification_page(message='This verification session ended. Return to registration to begin again.', status=400)
    tokens = request.form.getlist('csrf_token')
    if (request.headers.get('Origin') != request.host_url.rstrip('/') or len(tokens) != 1
            or not secrets.compare_digest(tokens[0].encode('utf-8'), record.csrf.encode('utf-8'))):
        return _email_verification_page(message='Please reload this page and try again.', status=403)
    fields = {'csrf_token', 'code'} if action == 'verify' else {'csrf_token'}
    if request.files or set(request.form) != fields or any(len(request.form.getlist(f)) != 1 for f in fields):
        return _email_verification_page(message='Invalid verification form. Please reload and try again.', status=400)
    if record.verified:
        return redirect(url_for('verify_email'), code=303)
    if action == 'verify' and not re.fullmatch(r'[0-9]{6,10}', request.form['code']):
        return _email_verification_page(message='Enter the numeric verification code from your email.', status=400)
    reserved, wait = store.reserve(handle, action)
    if reserved is None:
        return _email_verification_page(message='Please wait before trying again.', status=429, retry_after=wait or 1)
    verified, resent, limited, uncertain = False, False, False, False
    error_message, error_status = '', 200
    try:
        provider = current_app.extensions['rosago_email_verification']
        if action == 'resend':
            provider.resend(reserved.email)
            resent = True
        else:
            verified = provider.verify(reserved.email, request.form['code'])
    except AuthApiError as error:
        if error.status == 429 or error.code in ('over_email_send_rate_limit', 'over_request_rate_limit'):
            limited = True
            error_message, error_status = 'Too many requests. Please wait before trying again.', 429
        else:
            error_message = ('We could not send a code right now. Please try again later.' if action == 'resend'
                else 'The verification code is invalid or expired. Check the code or request a new one.')
            error_status = 400
    except Exception:
        error_message, error_status = 'Verification is temporarily unavailable. Please try again later.', 503
        uncertain = 'rosago_shared_sessions' in current_app.extensions
        if uncertain:
            error_message = 'We could not confirm verification. Return to registration to start a new verification session.'
    finally:
        store.finish(handle, verified=verified, resent=resent, limited=limited, uncertain=uncertain)
    if error_message:
        return _email_verification_page(message=error_message, status=error_status, retry_after=60 if limited else None)
    if action == 'verify' and not verified:
        return _email_verification_page(message='The verification code is invalid or expired. Check the code or request a new one.', status=400)
    return redirect(url_for('verify_email'), code=303)


@app.route('/terms')
def terms():
    return render_template('auth/terms.html')


@app.route('/privacy')
def privacy():
    return render_template('auth/privacy.html')


init_user_features(app, globals())


@app.errorhandler(404)
def user_not_found(error):
    if request.path == '/admin' or request.path.startswith('/admin/'):
        return 'Not found.', 404
    return render_template('library/not_found.html'), 404


from catalog_preview import install_catalog_preview
install_catalog_preview(app)


if __name__ == "__main__":
    app.run()
