import json
import unittest
from unittest.mock import patch

import httpx
import test_registration
from recovery_helpers import pkce_s256_challenge


class ForgotPasswordTests(unittest.TestCase):
    def setUp(self):
        test_registration.RegistrationTests.setUp(self)
        self.store = self.app.view_functions['forgot_password'].__globals__['pending_recoveries']
        self.requests = []
        self.status = 200
        self.fail_network = False
        real_client = httpx.Client
        client_patch = patch('httpx.Client', side_effect=lambda: real_client(
            transport=httpx.MockTransport(self.transport)))
        client_patch.start()
        self.addCleanup(client_patch.stop)

    def transport(self, request):
        self.requests.append(request)
        if self.fail_network:
            raise httpx.ConnectError('private-provider-detail', request=request)
        return httpx.Response(self.status, json={'detail': 'private-provider-detail'})

    def submit(self, **data):
        return self.client.post('/forgot-password', data={'email': 'ana@example.com', **data})

    def pending_id(self):
        with self.client.session_transaction() as current:
            return current.get('pending_recovery_id')

    def test_page_and_links_without_authentication_calls(self):
        response = self.client.get('/forgot-password')
        self.assertEqual(response.status_code, 200)
        for text in (b'Forgot your password?', b'Send Reset Link', b'Enter the email address associated with your RosaGO account.', b'/static/css/auth.css', b'/static/js/forgot-password.js', b'href="/login">Back to Login</a>'):
            self.assertIn(text, response.data)
        self.assertIn(b'href="/forgot-password"', self.client.get('/login').data)
        self.assertFalse(response.headers.getlist('Set-Cookie'))
        self.assertEqual(self.requests, [])
        self.assertEqual(self.supabase.mock_calls, [])

    def test_pkce_request_and_only_opaque_id_in_session(self):
        response = self.submit(email='  ana@example.com  ', redirect_to='https://untrusted.example')
        self.assertEqual(response.status_code, 200)
        handle = self.pending_id()
        record = self.store.lookup(handle)
        self.assertIsNotNone(record)
        with self.client.session_transaction() as current:
            self.assertEqual(dict(current), {'pending_recovery_id': handle})
        cookie = self.client.get_cookie('session')
        decoded = self.app.session_interface.get_signing_serializer(self.app).loads(cookie.value)
        self.assertEqual(decoded, {'pending_recovery_id': handle})
        self.assertNotIn(record.verifier, json.dumps(decoded))
        self.assertNotIn(record.verifier.encode(), response.data)
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.url.path, '/auth/v1/recover')
        self.assertEqual(dict(request.url.params), {'redirect_to': 'http://127.0.0.1:5000/auth/reset-callback'})
        self.assertEqual(json.loads(request.content), {
            'email': 'ana@example.com', 'code_challenge': pkce_s256_challenge(record.verifier),
            'code_challenge_method': 'S256'})
        self.assertNotIn(record.verifier.encode(), request.content)
        self.assertEqual(self.supabase.mock_calls, [])
        self.assertEqual(self.client.get('/auth/status').json, {'authenticated': False})

    def test_existing_login_values_are_preserved(self):
        with self.client.session_transaction() as current:
            current.update(user_id='user-123', user_email='ana@example.com')
        self.submit()
        with self.client.session_transaction() as current:
            self.assertEqual(current['user_id'], 'user-123')
            self.assertEqual(current['user_email'], 'ana@example.com')

    def test_invalid_email_does_not_send_or_replace_pending_flow(self):
        self.submit()
        old = self.pending_id()
        self.requests.clear()
        for email in ('', '   ', 'invalid', 'a@b', 'a b@example.com'):
            response = self.submit(email=email)
            self.assertEqual(response.status_code, 400)
            self.assertIn(b'Please enter', response.data)
            self.assertEqual(self.pending_id(), old)
        self.assertIsNotNone(self.store.lookup(old))
        self.assertEqual(self.requests, [])

    def test_success_and_provider_errors_use_same_generic_response(self):
        for email in ('registered@example.com', 'unknown@example.com'):
            self.status = 200
            baseline = self.submit(email=email)
            self.assertIn(b'If an account exists for that email, a password reset link has been sent.', baseline.data)
            for status in (400, 401, 404, 429, 500):
                self.status = status
                response = self.submit(email=email)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, baseline.data)
                self.assertNotIn(b'private-provider-detail', response.data)
                self.assertIsNone(self.pending_id())
                self.assertEqual(self.store._records, {})

    def test_network_failure_cleans_new_and_old_pending_records(self):
        self.submit()
        old = self.pending_id()
        self.fail_network = True
        response = self.submit()
        self.assertEqual(response.status_code, 503)
        self.assertIn(b'Please try again later.', response.data)
        self.assertNotIn(b'private-provider-detail', response.data)
        self.assertNotIn(b'Traceback', response.data)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIsNone(self.pending_id())
        self.assertIsNone(self.store.lookup(old))
        self.assertEqual(self.store._records, {})

    def test_new_request_invalidates_previous_record(self):
        self.submit()
        old = self.pending_id()
        self.submit()
        new = self.pending_id()
        self.assertNotEqual(old, new)
        self.assertIsNone(self.store.lookup(old))
        self.assertIsNone(self.store.consume(old))
        self.assertIsNotNone(self.store.lookup(new))
        self.assertEqual(len(self.store._records), 1)

    def test_pre_transport_failure_cleans_record_without_login_changes(self):
        with self.client.session_transaction() as current:
            current.update(user_id='existing', user_email='ana@example.com')
        with patch('httpx.Client', side_effect=RuntimeError('private-detail')):
            response = self.submit()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.store._records, {})
        with self.client.session_transaction() as current:
            self.assertEqual(dict(current), {'user_id': 'existing', 'user_email': 'ana@example.com'})
        self.assertEqual(self.requests, [])

    def test_diagnostics_are_fixed_and_contain_no_credentials(self):
        with self.assertLogs('rosago.recovery', level='WARNING') as logs:
            self.submit()
        self.assertEqual([record.getMessage() for record in logs.records], [
            '[RosaGO recovery] ' + category for category in (
                'RECOVERY_PENDING_CREATED', 'RECOVERY_PKCE_CREATED', 'RECOVERY_REQUEST_ACCEPTED')])
        self.status = 429
        with self.assertLogs('rosago.recovery', level='WARNING') as logs:
            self.submit()
        self.assertEqual(logs.records[-2].getMessage(), '[RosaGO recovery] RECOVERY_TRANSPORT_HTTP_429')
        self.assertEqual(logs.records[-1].getMessage(), '[RosaGO recovery] RECOVERY_REQUEST_FAILED')


if __name__ == '__main__':
    unittest.main()
