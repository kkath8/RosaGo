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
from normal_auth_coordinator import SessionBusy, ClientUnavailable, VerifiedRefresh
from normal_auth_flask import NormalAuthEntryError
from flask import g
from flask.sessions import SecureCookieSession
import httpx
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
        dependencies = self.app.extensions['rosago_normal_auth']
        self.store = dependencies.store
        dependencies.adapters._sdk_factory = self.create_client
        dependencies.adapters._http_factory = lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError('Unexpected HTTP'))), **kwargs)
        self.login_client.auth.get_user.return_value = SimpleNamespace(user=user)
        self.login_client.auth.get_claims.return_value = {'claims': dict(
            sub=user.id, session_id='verified-login-session', iss=dependencies.adapters.issuer,
            aud='authenticated', role='authenticated', exp=self.result.session.expires_at,
            amr=[{'method': 'password', 'timestamp': int(time.time())}])}

    def test_legacy_and_recovery_cookies_do_not_grant_authority(self):
        for data in ({'user_id': 'legacy', 'user_email': 'legacy@example.invalid'},
                     {'pending_recovery_id': 'pending'}, {'password_recovery_id': 'grant'}):
            for path, expected in (('/user', 302), ('/auth/status', 200), ('/login', 200), ('/register', 200)):
                with self.subTest(data=data, path=path):
                    with self.client.session_transaction() as current:
                        current.clear()
                        current.update(data)
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, expected)
                    if path == '/auth/status':
                        self.assertEqual(response.json, {'authenticated': False})

    def test_opaque_authority_access_and_logout_revocation(self):
        response = self.client.post('/login', data=self.credentials)
        self.assertEqual(response.status_code, 303)
        with self.client.session_transaction() as current:
            self.assertEqual(set(current), {'auth_session_id'})
            handle = current['auth_session_id']
        self.assertIsNotNone(self.store.resolve(handle))
        self.assertEqual(self.client.get('/user').status_code, 200)
        self.assertTrue(self.client.get('/auth/status').json['authenticated'])
        self.client.post('/logout')
        self.assertIsNone(self.store.resolve(handle))
        self.assertEqual(self.client.get('/user').status_code, 302)
        self.assertEqual(self.client.get('/auth/status').json, {'authenticated': False})

    def test_seeded_opaque_session_accesses_user(self):
        test_registration.seed_normal_session(self)
        self.assertEqual(self.client.get('/user').status_code, 200)

    def test_refresh_reservation_blocks_routes_without_duplicate_refresh(self):
        handle = test_registration.seed_normal_session(self)
        record = self.store.resolve(handle)
        coordinator = self.app.extensions['rosago_normal_auth'].coordinator
        lease, _ = self.store.reserve_refresh(handle)
        try:
            with patch.object(coordinator, '_clock', return_value=record.access_expires_at - 30), \
                 patch.object(coordinator, '_refresh') as refresh:
                for path in ('/user', '/auth/status', '/login', '/register'):
                    with self.subTest(path=path):
                        response = self.client.get(path)
                        self.assertEqual(response.status_code, 503)
                        self.assertEqual(response.headers['Retry-After'], '1')
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
                        self.assertNotIn('Location', response.headers)
                        with self.client.session_transaction() as current:
                            self.assertEqual(current['auth_session_id'], handle)
                refresh.assert_not_called()
                self.assertEqual(self.normal_clients, [])
                self.assertEqual(self.store.resolve(handle).last_activity_at, record.last_activity_at)
        finally:
            self.store.release_refresh(handle, lease)
        self.assertEqual(self.client.get('/user').status_code, 200)

    def test_routes_use_rotated_credentials_and_verified_email(self):
        handle = test_registration.seed_normal_session(self)
        record = self.store.resolve(handle)
        dependencies = self.app.extensions['rosago_normal_auth']
        coordinator = dependencies.coordinator
        expires = record.access_expires_at + 3600
        refreshed = VerifiedRefresh(
            record.user_id, 'updated@example.invalid', record.user_id, record.user_id,
            'rotated-access', 'rotated-refresh', expires,
            dict(sub=record.user_id, session_id=record.session_id, iss=dependencies.adapters.issuer,
                 aud='authenticated', role='authenticated', exp=expires,
                 amr=[{'method': 'password', 'timestamp': int(time.time())}]))
        with patch.object(coordinator, '_clock', return_value=record.access_expires_at - 30), \
             patch.object(coordinator, '_refresh', return_value=refreshed) as refresh, \
             patch.object(coordinator, '_clients', wraps=coordinator._clients) as clients:
            self.assertEqual(self.client.get('/auth/status').json,
                             {'authenticated': True, 'email': refreshed.user_email})
            page = self.client.get('/user')
            self.assertEqual(page.status_code, 200)
            self.assertIn(refreshed.user_email.encode(), page.data)
            for path in ('/login', '/register'):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers['Location'], '/user')
            refresh.assert_called_once_with(record.refresh_token)
            self.assertEqual(clients.call_count, 4)
            for call in clients.call_args_list:
                self.assertEqual(call.args, ('rotated-access',))
        updated = self.store.resolve(handle)
        self.assertEqual(updated.generation, record.generation + 1)
        self.assertEqual(updated.refresh_token, 'rotated-refresh')
        with self.client.session_transaction() as current:
            self.assertEqual(dict(current), {'auth_session_id': handle})
        for client in self.normal_clients:
            client.close.assert_called_once_with()

    def test_failed_refresh_revokes_normal_authority_and_preserves_recovery(self):
        handle = test_registration.seed_normal_session(self)
        record = self.store.resolve(handle)
        coordinator = self.app.extensions['rosago_normal_auth'].coordinator
        with self.client.session_transaction() as current:
            current.update(pending_recovery_id='pending', password_recovery_id='grant')
        with patch.object(coordinator, '_clock', return_value=record.access_expires_at - 30), \
             patch.object(coordinator, '_refresh', side_effect=RuntimeError('private-provider-error')):
            response = self.client.get('/auth/status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'authenticated': False})
        self.assertIsNone(self.store.resolve(handle))
        self.assertEqual(self.normal_clients, [])
        with self.client.session_transaction() as current:
            self.assertEqual(dict(current),
                             {'pending_recovery_id': 'pending', 'password_recovery_id': 'grant'})
        self.assertEqual(self.client.get('/user').status_code, 302)

    def test_temporary_failures_preserve_authority_on_all_consumers(self):
        dependencies = self.app.extensions['rosago_normal_auth']
        for error in (SessionBusy(), ClientUnavailable()):
            for path in ('/user', '/auth/status', '/login', '/register'):
                with self.subTest(error=type(error).__name__, path=path):
                    with self.client.session_transaction() as current:
                        current['auth_session_id'] = 'candidate'
                    with patch.object(dependencies.coordinator, 'authenticated', side_effect=error):
                        response = self.client.get(path)
                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn('Location', response.headers)
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    if path == '/auth/status':
                        self.assertNotIn('authenticated', response.json)
                    with self.client.session_transaction() as current:
                        self.assertEqual(current['auth_session_id'], 'candidate')

    def test_missing_malformed_expired_and_revoked_handles_are_rejected(self):
        revoked = test_registration.seed_normal_session(self)
        self.store.revoke(revoked)
        expired = test_registration.seed_normal_session(self)
        record = self.store.resolve(expired)
        self.store._records[expired] = __import__('dataclasses').replace(record, created_at=record.created_at - 28801)
        for handle in (None, '', [], {}, 123, 'unknown', expired, revoked):
            for path in ('/user', '/auth/status', '/login', '/register'):
                with self.subTest(handle=handle, path=path):
                    with self.client.session_transaction() as current:
                        current['auth_session_id'] = handle
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 302 if path == '/user' else 200)
                    if path == '/auth/status':
                        self.assertEqual(response.json, {'authenticated': False})

    def test_post_login_replaces_handle_and_failure_rolls_back(self):
        old = test_registration.seed_normal_session(self)
        other = self.app.test_client()
        other.post('/login', data=self.credentials)
        with other.session_transaction() as current:
            unrelated = current['auth_session_id']
        response = self.client.post('/login', data=self.credentials)
        self.assertEqual(response.status_code, 303)
        with self.client.session_transaction() as current:
            new = current['auth_session_id']
        self.assertNotEqual(old, new)
        self.assertIsNone(self.store.resolve(old))
        self.assertIsNotNone(self.store.resolve(unrelated))
        before = set(self.store._records)
        original_pop = SecureCookieSession.pop
        failed = False
        def fail_mutation(current, key, *args):
            nonlocal failed
            result = original_pop(current, key, *args)
            if key == 'user_email' and not failed:
                failed = True
                raise RuntimeError('private-provider-error')
            return result
        with patch.object(SecureCookieSession, 'pop', fail_mutation):
            response = self.client.post('/login', data=self.credentials)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private-provider-error', response.data)
        self.assertEqual(set(self.store._records), before)
        with self.client.session_transaction() as current:
            self.assertEqual(current['auth_session_id'], new)
        self.assertIsNotNone(self.store.resolve(new))

    def test_cookie_secrecy_and_logout_recovery_policy_without_provider(self):
        self.client.post('/login', data=self.credentials)
        with self.client.session_transaction() as current:
            handle = current['auth_session_id']
            current.update(pending_recovery_id='pending', password_recovery_id='grant')
        record = self.store.resolve(handle)
        decoded = self.app.session_interface.get_signing_serializer(self.app).loads(self.client.get_cookie('session').value)
        self.assertEqual(set(decoded), {'auth_session_id', 'pending_recovery_id', 'password_recovery_id'})
        for secret in (record.access_token, record.refresh_token, record.csrf, record.session_id, self.credentials['password']):
            self.assertNotIn(secret, repr(decoded))
        dependencies = self.app.extensions['rosago_normal_auth']
        with patch.object(dependencies.coordinator, 'authenticated', side_effect=AssertionError('No coordinator')), \
             patch.object(dependencies.adapters, '_client', side_effect=AssertionError('No provider')):
            self.assertEqual(self.client.post('/logout').status_code, 303)
        self.assertIsNone(self.store.resolve(handle))
        with self.client.session_transaction() as current:
            self.assertEqual(dict(current), {})

    def test_protected_view_errors_are_not_auth_failures_and_context_closes(self):
        test_registration.seed_normal_session(self)
        sentinel = NormalAuthEntryError('busy')
        with self.app.app_context():
            with patch.dict(self.app.view_functions['user_index'].__wrapped__.__globals__,
                            {'render_template': MagicMock(side_effect=sentinel)}):
                with self.assertRaises(NormalAuthEntryError) as raised:
                    self.client.get('/user')
            self.assertIs(raised.exception, sentinel)
            self.assertNotIn('auth', g)
        self.normal_clients[-1].close.assert_called_once_with()

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
            previous["user_id"] = "legacy"
            previous["user_email"] = "legacy@example.invalid"
        response = self.client.post("/login", data=self.credentials | {
            "email": "  ana@example.com  ", "remember_me": "on", "role": "admin",
        })
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/user")
        self.assertIn(b"Welcome to RosaGo", self.client.get("/user").data)
        self.login_client.auth.sign_in_with_password.assert_called_once_with(self.credentials)
        options = self.create_client.call_args.kwargs["options"]
        self.assertFalse(options.persist_session)
        self.assertFalse(options.auto_refresh_token)
        self.assertTrue(options.httpx_client.is_closed)
        self.assert_safe_response(response, session_created=True)
        with self.client.session_transaction() as current:
            self.assertEqual(set(current), {"auth_session_id"})
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
        self.assertIn(b"Welcome to RosaGo", response.data)
        self.assertIn(b"ana@example.com", response.data)
        self.assertIn(b'method="post" action="/logout"', response.data)
        self.assertNotIn(b'href="/logout"', response.data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        for path in ("/login", "/register"):
            for method in (("GET",) if path == "/login" else ("GET", "POST")):
                response = self.client.open(path, method=method)
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["Location"], "/user")
        self.create_client.assert_not_called()
        self.assertEqual(self.supabase.mock_calls, [])

    def test_user_email_is_escaped(self):
        test_registration.seed_normal_session(self, "<script>alert(1)</script>")
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
