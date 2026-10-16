import os
import runpy
import secrets
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
from contextlib import contextmanager
import time
import socket

from supabase_auth.errors import AuthApiError


def seed_normal_session(test, email='ana@example.com'):
    handle = test.app.extensions['rosago_normal_auth'].store.create(
        user_id='user-123', user_email=email, access_token='fixture-access',
        refresh_token='fixture-refresh', access_expires_at=time.time() + 3600,
        session_id='fixture-session')
    with test.client.session_transaction() as current:
        current['auth_session_id'] = handle
    return handle


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Live network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        self.supabase = Mock()
        with (
            patch("dotenv.load_dotenv"),
            patch.dict(os.environ, {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "sb_publishable_synthetic_test_fixture",
                "FLASK_SECRET_KEY": secrets.token_hex(32),
            }),
            patch("supabase.create_client", return_value=self.supabase) as create,
        ):
            namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "app.py"))
        options = create.call_args.kwargs["options"]
        self.assertFalse(options.persist_session)
        self.assertFalse(options.auto_refresh_token)
        self.app = namespace["app"]
        self.app.testing = True
        self.normal_clients = []
        @contextmanager
        def normal_client(token):
            client = Mock(spec=['table', 'close'])
            # Default to a missing profile for auth-only fixtures. The real
            # profile service still builds and executes its read query.
            query = Mock(spec=['select', 'eq', 'limit', 'retry', 'execute'])
            client.table.return_value = query
            for method in ('select', 'eq', 'limit', 'retry'):
                getattr(query, method).return_value = query
            query.execute.return_value = SimpleNamespace(data=[])
            self.normal_clients.append(client)
            try:
                yield client
            finally:
                client.close()
        self.app.extensions['rosago_normal_auth'].coordinator._clients = normal_client
        self.client = self.app.test_client()
        self.valid = {
            "first_name": "Ana", "last_name": "Cruz",
            "email": "ana@example.com", "password": "Example-pass-123",
            "confirm_password": "Example-pass-123", "terms": "accepted",
        }

    def test_existing_routes_and_form(self):
        with patch.object(self.app.extensions['rosago_places'], 'list_published', return_value=()):
            self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'action="/register" method="post"', response.data)
        self.assertNotIn(b"Preview only", response.data)
        self.assertEqual(self.client.get("/auth/callback").status_code, 200)
        self.supabase.auth.sign_up.assert_not_called()

    def test_invalid_input_never_calls_supabase(self):
        cases = [{field: ""} for field in self.valid]
        cases += [
            {"first_name": "   "}, {"last_name": "   "},
            {"email": "invalid"}, {"email": "a@b"},
            {"password": "short", "confirm_password": "short"},
            {"password": "        ", "confirm_password": "        "},
            {"confirm_password": "different-password"},
            {"terms": "false"},
        ]
        for changes in cases:
            with self.subTest(changes=list(changes)):
                response = self.client.post("/register", data=self.valid | changes)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(self.valid["password"].encode(), response.data)
        self.supabase.auth.sign_up.assert_not_called()

    def test_signup_metadata_redirect_and_no_session(self):
        response = self.client.post("/register", data=self.valid | {
            "role": "admin", "is_admin": "true", "first_name": " Ana ",
            "email_redirect_to": "https://example.com/untrusted",
        })
        self.assertEqual(response.status_code, 200)
        self.supabase.auth.sign_up.assert_called_once_with({
            "email": "ana@example.com", "password": self.valid["password"],
            "options": {
                "data": {"first_name": "Ana", "last_name": "Cruz"},
                "email_redirect_to": "http://127.0.0.1:5000/auth/callback",
            },
        })
        self.assertIn(b"Account created!", response.data)
        self.assertNotIn(self.valid["password"].encode(), response.data)
        self.assertFalse(response.headers.getlist("Set-Cookie"))

    def test_errors_are_safe_and_passwords_are_not_repopulated(self):
        cases = [
            (AuthApiError("sensitive-provider-detail", 422, "user_already_exists"), 400, b"already exists"),
            (AuthApiError("sensitive-provider-detail", 422, "weak_password"), 400, b"stronger password"),
            (AuthApiError("sensitive-provider-detail", 429, "over_email_send_rate_limit"), 429, b"Please wait"),
            (AuthApiError("sensitive-provider-detail", 500, "unexpected_failure"), 400, b"try again later"),
            (RuntimeError("sensitive-provider-detail"), 503, b"try again later"),
        ]
        for error, status, message in cases:
            with self.subTest(error=type(error).__name__, status=status):
                self.supabase.auth.sign_up.side_effect = error
                response = self.client.post("/register", data=self.valid)
                self.assertEqual(response.status_code, status)
                self.assertIn(message, response.data)
                self.assertNotIn(b"sensitive-provider-detail", response.data)
                self.assertNotIn(self.valid["password"].encode(), response.data)
                self.assertIn(b'value="Ana"', response.data)
                self.assertFalse(response.headers.getlist("Set-Cookie"))

    def test_repopulated_values_are_escaped(self):
        response = self.client.post("/register", data=self.valid | {
            "first_name": '<script>alert("test")</script>', "terms": "",
        })
        self.assertNotIn(b'<script>alert("test")</script>', response.data)
        self.assertIn(b"&lt;script&gt;", response.data)


if __name__ == "__main__":
    unittest.main()
