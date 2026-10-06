import os
import re
import logging
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from supabase import Client, ClientOptions, create_client
from supabase_auth.errors import AuthApiError

from auth_helpers import login_required

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
            r'(/auth/callback)\?[^\s"]*', r'\1?[redacted]', record.getMessage()
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
    if request.path in ("/auth/callback", "/login", "/register", "/user"):
        response.headers["Cache-Control"] = "no-store"
    if request.path == "/auth/callback":
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("user_index"), code=303)

    email = ""
    message = ""
    state = ""
    status = 200

    if request.method == "GET" and request.args.get("logged_out") == "1":
        message = "You have been logged out successfully."
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
                # The SDK keeps in-memory auth state, so isolate each login attempt.
                supabase = create_client(
                    SUPABASE_URL, SUPABASE_KEY,
                    options=ClientOptions(persist_session=False, auto_refresh_token=False),
                )
                with supabase.auth:
                    result = supabase.auth.sign_in_with_password({
                        "email": email,
                        "password": password,
                    })
                    user = result.user if result else None
                    auth_session = result.session if result else None
                    authenticated = bool(
                        user and user.id and user.email and user.email_confirmed_at
                        and auth_session and auth_session.access_token
                        and auth_session.refresh_token and auth_session.user
                        and auth_session.user.id == user.id
                        and auth_session.expires_at
                        and auth_session.expires_at > time.time()
                    )
                if authenticated:
                    session.clear()
                    session["user_id"] = user.id
                    session["user_email"] = user.email
                    return redirect(url_for("user_index"), code=303)
                else:
                    message = "We could not confirm your login. Please try again."
                    status = 401
            except AuthApiError as error:
                if error.code == "invalid_credentials":
                    message = "Invalid email or password."
                    status = 401
                elif error.code == "email_not_confirmed":
                    message = "Please verify your email before logging in. Check your inbox for the verification link."
                    status = 403
                elif error.status == 429 or error.code == "over_request_rate_limit":
                    message = "Too many login attempts. Please wait before trying again."
                    status = 429
                else:
                    message = "We could not complete your login. Please try again later."
                    status = 503
            except Exception:
                # Never expose or log raw provider errors, passwords, or tokens.
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
    return render_template("user/index.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    # Login uses an isolated Supabase client and retains no tokens. There is no
    # user-bound Supabase client here to sign out; do not use the shared client.
    response = redirect(url_for("login", logged_out="1"), code=303)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/auth/status")
def auth_status():
    # Temporary development endpoint for checking RosaGO session persistence.
    if session.get("user_id") and session.get("user_email"):
        response = jsonify(authenticated=True, email=session["user_email"])
    else:
        response = jsonify(authenticated=False)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("user_index"), code=303)

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
