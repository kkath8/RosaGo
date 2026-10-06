import time
import os
import runpy
import unittest
from copy import deepcopy
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from supabase_auth.errors import AuthApiError
import test_registration


class LoginTests(unittest.TestCase):
    def setUp(self):
        test_registration.RegistrationTests.setUp(self)
        self.login_client = MagicMock()
        self.create_client = MagicMock(return_value=self.login_client)
        self.client_patch = patch.dict(
            self.app.view_functions["login"].__globals__,
            {"create_client": self.create_client},
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.credentials = {"email": "ana@example.com", "password": "private-password"}
        user = SimpleNamespace(id="user-123", email="ana@example.com", email_confirmed_at="2026-10-06T00:00:00Z")
        self.result = SimpleNamespace(user=user, session=SimpleNamespace(
            user=user, access_token="private-access-token",
            refresh_token="private-refresh-token", expires_at=time.time() + 3600,
        ))
        self.login_client.auth.sign_in_with_password.return_value = self.result

    def assert_safe_response(self, response, session_created=False):
        for secret in (b"private-password", b"private-access-token", b"private-refresh-token", b"private-provider-error"):
            self.assertNotIn(secret, response.data)
        if not session_created:
            self.assertFalse(response.headers.getlist("Set-Cookie"))
            self.assertEqual(self.client.get("/auth/status").json, {"authenticated": False})
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        if not session_created:
            self.assertNotIn("Location", response.headers)
        self.assertEqual(self.supabase.mock_calls, [])

    def test_get_does_not_authenticate(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="email"', response.data)
        self.assertIn(b'name="password"', response.data)
        self.assertNotIn(b"Preview only", response.data)
        self.create_client.assert_not_called()
        self.assert_safe_response(response)

    def test_invalid_input_never_contacts_supabase(self):
        for data in ({}, {"email": ""}, {"email": "a@b"}, {"email": "bad email@example.com"}, {"password": ""}, {"password": "   "}):
            with self.subTest(fields=list(data)):
                payload = self.credentials | data if data else {}
                response = self.client.post("/login", data=payload)
                self.assertEqual(response.status_code, 400)
                self.assert_safe_response(response)
        self.create_client.assert_not_called()

    def test_success_creates_minimal_session_and_uses_isolated_client(self):
        with self.client.session_transaction() as previous:
            previous["stale"] = "old-data"
            previous.permanent = True
        response = self.client.post("/login", data=self.credentials | {
            "email": "  ana@example.com  ", "remember_me": "on", "role": "admin",
        })
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/user")
        self.assertIn(b"Welcome to RosaGO", self.client.get("/user").data)
        self.login_client.auth.sign_in_with_password.assert_called_once_with(self.credentials)
        options = self.create_client.call_args.kwargs["options"]
        self.assertFalse(options.persist_session)
        self.assertFalse(options.auto_refresh_token)
        self.login_client.auth.__exit__.assert_called_once()
        self.assert_safe_response(response, session_created=True)
        with self.client.session_transaction() as current:
            self.assertEqual(dict(current), {"user_id": "user-123", "user_email": "ana@example.com"})
            self.assertFalse(current.permanent)
        cookie = SimpleCookie()
        cookie.load(response.headers["Set-Cookie"])
        session_cookie = cookie[self.app.config["SESSION_COOKIE_NAME"]]
        self.assertTrue(session_cookie["httponly"])
        self.assertEqual(session_cookie["samesite"], "Lax")
        self.assertFalse(session_cookie["secure"])
        self.assertEqual(session_cookie["expires"], "")
        self.assertEqual(session_cookie["max-age"], "")
        for _ in range(2):
            status = self.client.get("/auth/status")
            self.assertEqual(status.json, {"authenticated": True, "email": "ana@example.com"})
            self.assertEqual(status.headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get("/login").headers["Location"], "/user")
        self.assertEqual(self.app.test_client().get("/auth/status").json, {"authenticated": False})

    def test_logout_clears_entire_session_and_stays_logged_out(self):
        self.client.post("/login", data=self.credentials)
        with self.client.session_transaction() as current:
            current["stale"] = "must-be-removed"
        self.assertIn(b'method="post" action="/logout"', self.client.get("/user").data)

        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/login?logged_out=1")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        cookie = SimpleCookie()
        cookie.load(response.headers["Set-Cookie"])
        self.assertEqual(cookie[self.app.config["SESSION_COOKIE_NAME"]]["max-age"], "0")
        self.assertIsNone(self.client.get_cookie(self.app.config["SESSION_COOKIE_NAME"]))
        with self.client.session_transaction() as current:
            self.assertEqual(dict(current), {})

        for _ in range(2):
            page = self.client.get(response.headers["Location"])
            self.assertIn(b"You have been logged out successfully.", page.data)
            self.assertNotIn(b'action="/logout"', page.data)
            self.assertFalse(page.headers.getlist("Set-Cookie"))
            self.assertEqual(self.client.get("/auth/status").json, {"authenticated": False})
        self.login_client.auth.sign_out.assert_not_called()
        self.assertEqual(self.supabase.mock_calls, [])
        protected = self.client.get("/user", follow_redirects=True)
        self.assertIn(b"Please log in to continue.", protected.data)
        self.assertNotIn(b"Signed in as", protected.data)

    def test_user_requires_login(self):
        response = self.client.get("/user")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login?login_required=1")
        self.assertIn(b"Please log in to continue.", self.client.get(response.headers["Location"]).data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.create_client.assert_not_called()

    def test_authenticated_user_page_and_auth_page_redirects(self):
        self.client.post("/login", data=self.credentials)
        self.create_client.reset_mock()
        response = self.client.get("/user")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome to RosaGO", response.data)
        self.assertIn(b"ana@example.com", response.data)
        self.assertIn(b'method="post" action="/logout"', response.data)
        self.assertNotIn(b'href="/logout"', response.data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        for path in ("/login", "/register"):
            for method in ("GET", "POST"):
                response = self.client.open(path, method=method)
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["Location"], "/user")
        self.create_client.assert_not_called()
        self.assertEqual(self.supabase.mock_calls, [])

    def test_user_email_is_escaped(self):
        with self.client.session_transaction() as current:
            current["user_id"] = "user-123"
            current["user_email"] = "<script>alert(1)</script>"
        response = self.client.get("/user")
        self.assertIn(b"&lt;script&gt;", response.data)
        self.assertNotIn(b"<script>alert(1)</script>", response.data)

    def test_get_logout_does_not_log_out(self):
        self.client.post("/login", data=self.credentials)
        for method in ("GET", "HEAD"):
            response = self.client.open("/logout", method=method)
            self.assertEqual(response.status_code, 405)
        self.assertTrue(self.client.get("/auth/status").json["authenticated"])

    def test_logout_is_safe_when_already_logged_out(self):
        for _ in range(2):
            response = self.client.post("/logout", follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"You have been logged out successfully.", response.data)
            self.assertNotIn(b'action="/logout"', response.data)
            self.assertEqual(self.client.get("/auth/status").json, {"authenticated": False})
        self.create_client.assert_not_called()
        self.assertEqual(self.supabase.mock_calls, [])

    def test_logout_does_not_affect_another_browser(self):
        other = self.app.test_client()
        other.post("/login", data=self.credentials)
        self.client.post("/login", data=self.credentials)
        self.client.post("/logout")
        self.assertEqual(self.client.get("/auth/status").json, {"authenticated": False})
        self.assertTrue(other.get("/auth/status").json["authenticated"])

    def test_tampered_session_cookie_is_not_authenticated(self):
        self.client.post("/login", data=self.credentials)
        cookie_name = self.app.config["SESSION_COOKIE_NAME"]
        cookie = self.client.get_cookie(cookie_name)
        self.client.set_cookie(cookie_name, cookie.value + "tampered")
        self.assertEqual(self.client.get("/auth/status").json, {"authenticated": False})

    def test_partial_session_is_not_authenticated(self):
        for data in ({"user_id": "user-123"}, {"user_email": "ana@example.com"}):
            with self.client.session_transaction() as current:
                current.clear()
                current.update(data)
            self.assertEqual(self.client.get("/auth/status").json, {"authenticated": False})
            self.assertNotIn(b"You are currently signed in", self.client.get("/login").data)

    def test_missing_secret_fails_safely_before_client_initialization(self):
        for secret in (None, "", "   "):
            environment = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_KEY": "test-placeholder"}
            if secret is not None:
                environment["FLASK_SECRET_KEY"] = secret
            with patch("dotenv.load_dotenv"), patch.dict(os.environ, environment, clear=True), patch("supabase.create_client") as create:
                with self.assertRaises(RuntimeError) as error:
                    runpy.run_path(str(Path(__file__).resolve().parents[1] / "app.py"))
                self.assertEqual(str(error.exception), "Flask configuration error: FLASK_SECRET_KEY must be set.")
                create.assert_not_called()

    def test_incomplete_unverified_mismatched_or_expired_response_is_not_success(self):
        cases = [None, SimpleNamespace(user=None, session=None)]
        for field, value in (("session", None), ("user", None)):
            result = deepcopy(self.result)
            setattr(result, field, value)
            cases.append(result)
        for field, value in (("access_token", ""), ("refresh_token", ""), ("expires_at", time.time() - 60), ("user", SimpleNamespace(id="other-user"))):
            result = deepcopy(self.result)
            setattr(result.session, field, value)
            cases.append(result)
        result = deepcopy(self.result)
        result.user.email_confirmed_at = None
        cases.append(result)
        for result in cases:
            self.login_client.auth.sign_in_with_password.return_value = result
            response = self.client.post("/login", data=self.credentials)
            self.assertEqual(response.status_code, 401)
            self.assertNotIn(b"Login successful!", response.data)
            self.assert_safe_response(response)

    def test_authentication_errors_are_user_friendly_and_safe(self):
        cases = [
            (AuthApiError("private-provider-error", 400, "invalid_credentials"), 401, b"Invalid email or password."),
            (AuthApiError("private-provider-error", 400, "email_not_confirmed"), 403, b"Please verify your email"),
            (AuthApiError("private-provider-error", 429, "over_request_rate_limit"), 429, b"Too many login attempts"),
            (AuthApiError("private-provider-error", 500, "unexpected_failure"), 503, b"Please try again later"),
            (RuntimeError("private-provider-error"), 503, b"Please try again later"),
        ]
        for error, status, message in cases:
            self.login_client.auth.sign_in_with_password.side_effect = error
            response = self.client.post("/login", data=self.credentials)
            self.assertEqual(response.status_code, status)
            self.assertIn(message, response.data)
            self.assert_safe_response(response)


if __name__ == "__main__":
    unittest.main()
