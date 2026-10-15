import os
import re
import logging
import time
import httpx
import secrets
from datetime import date

from dotenv import load_dotenv
from flask import Flask, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
from supabase import Client, ClientOptions, create_client
from supabase_auth.errors import AuthApiError, AuthError

from auth_helpers import login_required
from trip_service import (
    list_user_trips, get_user_trip, create_trip, update_trip, delete_trip,
    TripServiceError, TripValidationError, TripNotFoundError,
    TripOperationRejectedError, TripUnavailableError, TripConsistencyError,
)
from normal_auth_flask import (
    init_normal_auth, get_normal_auth_dependencies, establish_normal_session,
    SessionEstablishmentError, normal_auth_redirect_decision, AuthRedirectDecision,
    normal_auth_state, logout_normal_session,
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
    if request.path == '/user/trips' or request.path.startswith('/user/trips/'):
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
    return render_template("index.html")


def places_error(message, status):
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


def _trip_post_check(fields):
    tokens = request.form.getlist('csrf_token')
    if (len(tokens) != 1 or not tokens[0].strip()
            or not get_normal_auth_dependencies().coordinator.validate_csrf(
                g.auth.auth_session_id, tokens[0])):
        return 'Please reload this page and try again.', 403
    if request.headers.get('Origin') not in (None, request.host_url.rstrip('/')):
        return 'Please reload this page and try again.', 403
    if (request.files or set(request.form) != fields
            or any(len(request.form.getlist(field)) != 1 for field in fields)):
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
