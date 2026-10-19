import os
import re
import logging
import time
import httpx
import secrets
from contextlib import ExitStack
from datetime import date, datetime, timezone
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
from supabase import Client, ClientOptions, create_client
from supabase_auth.errors import AuthApiError, AuthError

from auth_helpers import login_required
from itinerary_draft_service import (
    create_itinerary_draft, get_itinerary_draft, update_itinerary_draft_preferences,
    DraftError, DraftValidationError, DraftRejectedError, DraftUnavailableError, DraftConsistencyError,
    validate_complete_preferences,
    get_itinerary_preview_draft, store_itinerary_draft_preview,
    return_itinerary_draft_to_editing,
)
from itinerary_preview import (
    build_personalized_preview, compute_catalog_fingerprint, PreviewContractError,
)
from recommendation_engine import (
    rank_candidates, MAX_CANDIDATES, CATEGORY_INTEREST_MATCH, RecommendationInputError,
)
from itinerary_selection_policy import select_destinations, SelectionPolicyError
from itinerary_quiz_form import (
    COMPANIONS, TRANSPORTATION, TRIP_PACES, ACTIVITIES, ENVIRONMENTS,
    FORM_FIELDS, REPEATED_FIELDS, parse_quiz_form, form_values,
    submitted_values, expected_revision as quiz_expected_revision, QuizTimeWindowError,
)
from trip_service import (
    list_user_trips, get_user_trip, create_trip, update_trip, delete_trip, add_place,
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
from places_service import (
    CATEGORIES, PlacesService, PlacesValidationError,
    PlacesUnavailableError, PlacesConsistencyError,
)
from profile_service import (
    get_own_profile, update_own_profile, ProfileUnavailableError,
    ProfileConsistencyError, ProfileValidationError, ProfileNotFoundError,
)
from recovery_helpers import RECOVERY_ERROR, RecoveryGrants, recovery_expiry, PendingRecoveries, pkce_s256_challenge
from recovery_diagnostics import recovery_diagnostic
from recovery_transport import send_pkce_recovery, RecoveryRequestRejected

load_dotenv()

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
app.extensions['rosago_places'] = PlacesService(
    PublicPlacesClient(SUPABASE_URL, SUPABASE_KEY).database_client
)
init_normal_auth(app, SUPABASE_URL, SUPABASE_KEY)
recovery_grants = RecoveryGrants()
pending_recoveries = PendingRecoveries()
app.config.update(
    SECRET_KEY=FLASK_SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Local HTTP only. Set this to True in production when HTTPS is used.
    SESSION_COOKIE_SECURE=False,
)


class CallbackLogFilter(logging.Filter):
    def filter(self, record):
        # Werkzeug otherwise includes callback query credentials in its access log.
        record.msg = re.sub(
            r'(/auth/(?:reset-callback|callback))\?[^\s"]*', r'\1?[redacted]', record.getMessage()
        )
        record.args = ()
        return True


logging.getLogger("werkzeug").addFilter(CallbackLogFilter())


@app.route("/auth/callback")
def auth_callback():
    # Completion page after Supabase confirmation; this grants no authentication.
    return render_template("auth/verified.html")


@app.after_request
def protect_auth_response(response):
    if (request.path == '/user/trips' or request.path.startswith('/user/trips/')
            or request.path.startswith('/user/itinerary/')):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'same-origin'
    if request.path in ("/auth/callback", "/auth/reset-callback", "/reset-password", "/login", "/register", "/user", "/user/profile/edit"):
        response.headers["Cache-Control"] = "no-store"
    if request.path in ("/auth/callback", "/auth/reset-callback"):
        response.headers["Referrer-Policy"] = "no-referrer"
    if request.path in ("/reset-password", "/user/profile/edit"):
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

    def form_error(message, status=400):
        return render_template("auth/reset_password.html", csrf=csrf, message=message), status

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
        return form_error("Please enter a new password.")
    if len(password) < 8:
        recovery_diagnostic("RESET_PASSWORD_VALIDATION_REJECTED")
        return form_error("Use at least 8 characters for your password.")
    if not confirmation:
        recovery_diagnostic("RESET_PASSWORD_VALIDATION_REJECTED")
        return form_error("Please confirm your new password.")
    if password != confirmation:
        recovery_diagnostic("RESET_PASSWORD_VALIDATION_REJECTED")
        return form_error("Passwords do not match. Enter the same password in both fields.")
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
                trip_state = 'ready'
                try:
                    trips = tuple(dict(name=trip.name, visit_date=trip.visit_date,
                                       detail_url=url_for('trips_detail', trip_id=trip.id))
                                  for trip in list_user_trips(auth, limit=3, offset=0))
                except (TripUnavailableError, TripConsistencyError):
                    trip_state = 'unavailable'
        # The scope has closed its client and removed g.auth before rendering.
    response = current_app.make_response(render_template(
        'index.html', dashboard_places=places, places_unavailable=places_unavailable,
        dashboard_trips=trips, trip_state=trip_state))
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
    try:
        places = current_app.extensions['rosago_places'].list_published(category=category)
    except PlacesValidationError:
        return places_error('Invalid place category.', 400)
    except PlacesUnavailableError:
        return places_error('Places are temporarily unavailable.', 503)
    except PlacesConsistencyError:
        return places_error('Unable to display places.', 500)
    return render_template('places/list.html', places=places,
                           categories=tuple(sorted(CATEGORIES)), selected_category=category)


@app.route('/map', methods=['GET'])
def map_index():
    try:
        places = current_app.extensions['rosago_places'].list_published(
            category=None, limit=50, offset=0)
    except PlacesUnavailableError:
        return places_error('Places are temporarily unavailable.', 503)
    except PlacesConsistencyError:
        return places_error('Unable to display places.', 500)
    markers = [dict(name=place.name,
                    detail_url=url_for('places_detail', slug=place.slug),
                    category=place.category, address=place.address,
                    latitude=place.latitude, longitude=place.longitude)
               for place in places]
    return render_template('map.html', markers=markers)


@app.route('/places/<slug>', methods=['GET'])
def places_detail(slug):
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
    return render_template('places/detail.html', place=place)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
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


@app.route("/login", methods=["GET", "POST"])
def login():
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
                return redirect(url_for("user_index"), code=303)
            except PasswordLoginError as error:
                status, message = {
                    "invalid_credentials": (401, "Invalid email or password."),
                    "unconfirmed_email": (403, "Please verify your email before logging in. Check your inbox for the verification link."),
                    "throttled": (429, "Too many login attempts. Please wait before trying again."),
                    "invalid_result": (401, "We could not confirm your login. Please try again."),
                    "service_failure": (503, "We could not complete your login. Please try again later."),
                }[error.reason]
            except SessionEstablishmentError:
                message = "We could not complete your login. Please try again later."
                status = 503

    response = app.make_response((render_template(
        "auth/login.html", email=email, message=message, state=state
    ), status))
    response.headers["Cache-Control"] = "no-store"
    return response


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
    # Flask exposes g to Jinja implicitly. Hide authority during eager rendering;
    # restore it for the surrounding auth scope's cleanup and nesting contract.
    auth = g.pop('auth')
    try:
        return render_template("user/index.html", profile=profile, user_email=user_email)
    finally:
        g.auth = auth


@app.route("/user/profile/edit", methods=["GET", "POST"])
@login_required
def user_profile_edit():
    dependencies = get_normal_auth_dependencies()
    message = ""
    status = 200
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
        try:
            update_own_profile(g.auth, first_name=first_name, last_name=last_name)
        except ProfileValidationError:
            message = "Use names of at most 100 characters without control characters. Names may be blank."
            status = 400
        except ProfileNotFoundError:
            return "Your profile is currently unavailable for editing.", 404
        except ProfileUnavailableError:
            return "Your save could not be confirmed. Please check your profile before trying again.", 503
        except ProfileConsistencyError:
            return "We could not display this page. Please try again later.", 500
        else:
            flash("Profile updated.", "profile_success")
            return redirect(url_for("user_profile_edit"), code=303)
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
                               csrf=csrf, message=message), status
    finally:
        g.auth = auth


def _render_trip_page(template, **values):
    """Keep request authority out of Jinja, including inherited templates."""
    auth = g.pop('auth')
    try:
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


def _trip_form(template, *, trip_id=None, name='', visit_date='', message='', status=200):
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    return _render_trip_page(template, trip_id=trip_id, name=name, visit_date=visit_date,
                             csrf=csrf, message=message), status


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
    return _render_trip_page('itinerary/recommendations.html', draft_id=draft.draft_id,
        message=None, cards=cards, interests=preferences['interests'],
        csrf=csrf, revision=draft.revision,
        has_test_records=any(card['place'].slug.startswith('rosago-test-v1-') for card in cards))


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
    return tuple(card['place'] for card in cards if card['place'].id in selected_ids), preferences, None


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
        selected = select_destinations(preferences, result.matched)
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
    # Reader already validated the contract. Revalidation catches inconsistent
    # models without generating a new candidate or changing the stored plan.
    try:
        draft.preview.to_document()
    except (PreviewContractError, AttributeError):
        return 'We could not display this preview. Please reload your draft.', 500
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    message, status = None, 200
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
    return _render_trip_page('itinerary/preview.html', draft_id=draft.draft_id,
        revision=draft.revision, csrf=csrf, days=days, message=message,
        constraints=draft.preview.plan.constraints, day_count=len(draft.preview.plan.days),
        destination_count=len(draft.preview.source.selected_place_ids),
        has_test_records=any(stop['place'].slug.startswith('rosago-test-v1-')
                             for day in days for stop in day['stops'])), status


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
    return _render_trip_page('trips/list.html', trips=trips, offset=offset, next_offset=next_offset)


@app.route('/user/trips/add-place/<slug>', methods=['GET', 'POST'])
@login_required
def trips_add_place(slug):
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
            add_place(g.auth, trip_id, place.id)
        except TripServiceError as error:
            return _trip_failure(error, mutation=True)
        return redirect(url_for('trips_detail', trip_id=trip_id), code=303)

    try:
        trips = list_user_trips(g.auth, limit=50, offset=offset)
    except TripServiceError as error:
        return _trip_failure(error)
    csrf = _trip_csrf()
    if csrf is None:
        return 'Please reload this page and try again.', 403
    next_offset = offset + len(trips) if len(trips) == 50 and offset + 50 <= 2147483647 - 49 else None
    return _render_trip_page('trips/add_place.html', place=place, trips=trips,
                             csrf=csrf, offset=offset, next_offset=next_offset)


@app.route('/user/trips/new', methods=['GET'])
@login_required
def trips_new():
    return _trip_form('trips/new.html')


@app.route('/user/trips', methods=['POST'])
@login_required
def trips_create():
    failure = _trip_post_check({'csrf_token', 'name', 'visit_date'})
    if failure is not None:
        return failure
    try:
        visit_date = _trip_date(request.form['visit_date'])
        trip = create_trip(g.auth, name=request.form['name'], visit_date=visit_date)
    except TripValidationError:
        return _trip_form('trips/new.html', name=request.form['name'], visit_date=request.form['visit_date'],
                          message='Use a name of 1–100 characters without control characters and an optional date in YYYY-MM-DD format.', status=400)
    except TripServiceError as error:
        return _trip_failure(error, mutation=True)
    return redirect(url_for('trips_detail', trip_id=trip.id), code=303)


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
    try:
        logout_normal_session()
        # Preserve the existing whole-application browser logout, including recovery.
        session.clear()
    except Exception:
        response = app.make_response(("Logout could not be completed. Please try again.", 503))
        response.headers["Cache-Control"] = "no-store"
        return response
    response = redirect(url_for("login", logged_out="1"), code=303)
    response.headers["Cache-Control"] = "no-store"
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


@app.route("/register", methods=["GET", "POST"])
def register():
    response = normal_auth_page_check("auth/register.html")
    if response is not None:
        return response

    form_data = {}
    message = ""
    state = ""
    status = 200

    if request.method == "POST":
        form_data = {
            "first_name": request.form.get("first_name", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "terms": request.form.get("terms") == "accepted",
        }
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        errors = []
        for field, label in (("first_name", "first name"), ("last_name", "last name")):
            if not form_data[field]:
                errors.append(f"Please enter your {label}.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", form_data["email"]):
            errors.append("Please enter a valid email address.")
        if not password.strip():
            errors.append("Please enter a password.")
        elif len(password) < 8:
            errors.append("Use at least 8 characters for your password.")
        if not confirm_password.strip():
            errors.append("Please confirm your password.")
        elif password != confirm_password:
            errors.append("Passwords do not match.")
        if not form_data["terms"]:
            errors.append("Please agree to the Terms and Privacy Policy.")

        state = "error"
        if errors:
            message = " ".join(errors)
            status = 400
        else:
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
                        "email_redirect_to": "http://127.0.0.1:5000/auth/callback",
                    },
                })
            except AuthApiError as error:
                messages = {
                    "user_already_exists": "An account with this email already exists. Please check your inbox for a verification email.",
                    "email_exists": "An account with this email already exists. Please check your inbox for a verification email.",
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
                message = "Account created! We sent a verification link to your email. Please verify your email before logging in."
                state = "success"
                form_data = {}

    return render_template(
        "auth/register.html", form_data=form_data, message=message, state=state
    ), status


if __name__ == "__main__":
    app.run()
