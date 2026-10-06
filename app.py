import os
import re
import logging

from dotenv import load_dotenv
from flask import Flask, render_template, request
from supabase import Client, ClientOptions, create_client
from supabase_auth.errors import AuthApiError

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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
def protect_callback_response(response):
    if request.path == "/auth/callback":
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
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
