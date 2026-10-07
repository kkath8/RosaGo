import logging
import time
import unittest
import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock, patch

from supabase_auth.errors import AuthApiError
from recovery_diagnostics import CATEGORIES
import test_registration


class FormElements(HTMLParser):
    """Extract actual rendered controls for the Node initialization regression."""
    def __init__(self):
        super().__init__()
        self.elements = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        element = {'tag': tag, 'attrs': dict(attrs), 'textContent': ''}
        self.elements.append(element)
        if tag not in ('input', 'meta', 'link', 'br'):
            self.stack.append(element)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        for element in self.stack:
            element['textContent'] += data


class RecoveryCallbackTests(unittest.TestCase):
    def setUp(self):
        test_registration.RegistrationTests.setUp(self)
        self.globals = self.app.view_functions['reset_callback'].__globals__
        self.store = self.globals['pending_recoveries']
        self.isolated = MagicMock()
        self.factory = Mock(return_value=self.isolated)
        replacement = patch.dict(self.globals, create_client=self.factory)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.now = time.time()
        self.claims = {
            'sub': 'recovery-user', 'iss': 'https://example.supabase.co/auth/v1',
            'aud': 'authenticated', 'session_id': 'recovery-session',
            'exp': self.now + 3600, 'amr': [{'method': 'recovery', 'timestamp': self.now}],
        }
        self.user = NS(id='recovery-user', email='ana@example.com')
        self.result = NS(user=self.user, session=NS(
            user=self.user, access_token='private-access', refresh_token='private-refresh'))
        self.isolated.auth.exchange_code_for_session.return_value = self.result
        self.isolated.auth.get_claims.return_value = {'claims': self.claims}
        self.isolated.auth.get_user.return_value = NS(user=self.user)

    def pending(self):
        handle = self.store.create()
        with self.client.session_transaction() as current:
            current['pending_recovery_id'] = handle
        return handle

    def callback(self, query='code=private-code', client=None):
        return (client or self.client).get('/auth/reset-callback?' + query)

    def denied(self, response, status=400):
        self.assertEqual(response.status_code, status)
        self.assertIn(b'Recovery link unavailable', response.data)
        self.assertIn(b'href="/forgot-password"', response.data)
        self.assertNotIn(b'private-', response.data)
        self.assertEqual(self.client.get('/reset-password').status_code, 403)

    def test_success_exchange_uses_server_verifier_and_isolated_client(self):
        handle = self.pending()
        verifier = self.store.lookup(handle).verifier
        response = self.callback()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.location, '/reset-password')
        self.isolated.auth.exchange_code_for_session.assert_called_once_with({
            'auth_code': 'private-code', 'code_verifier': verifier})
        self.isolated.auth.get_claims.assert_called_once_with('private-access')
        self.isolated.auth.get_user.assert_called_once_with('private-access')
        self.isolated.auth.__exit__.assert_called_once()
        options = self.factory.call_args.kwargs['options']
        self.assertFalse(options.persist_session)
        self.assertFalse(options.auto_refresh_token)
        self.assertEqual(self.supabase.mock_calls, [])
        self.assertIsNone(self.store.lookup(handle))
        self.assertIsNone(self.store.reserve(handle))
        with self.client.session_transaction() as current:
            self.assertEqual(set(current), {'password_recovery_id'})
        cookie = self.app.session_interface.get_signing_serializer(self.app).loads(self.client.get_cookie('session').value)
        self.assertNotIn(verifier, str(cookie))
        self.assertNotIn('private-', str(cookie))
        page = self.client.get('/reset-password')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Create a new password', page.data)
        self.assertNotIn(verifier.encode(), page.data)
        self.assertNotIn(b'private-', page.data)
        self.assertEqual(self.client.get('/auth/status').json, {'authenticated': False})
        self.assertEqual(self.client.post('/reset-password').status_code, 403)
        self.isolated.auth.update_user.assert_not_called()

    def test_direct_access_denied_with_or_without_login(self):
        self.denied(self.client.get('/reset-password'), 403)
        with self.client.session_transaction() as current:
            current.update(user_id='normal', user_email='normal@example.com')
        self.denied(self.client.get('/reset-password'), 403)
        self.factory.assert_not_called()

    def test_callback_to_rendered_form_and_javascript_initialization_has_valid_csrf(self):
        self.pending()
        response = self.client.get('/auth/reset-callback?code=private-code', follow_redirects=True)
        self.assertEqual([item.status_code for item in response.history], [303])
        self.assertEqual(response.history[0].headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')
        self.assertEqual(response.request.method, 'GET')
        self.assertEqual(response.request.path, '/reset-password')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'Please reload this page and try again.', response.data)
        parser = FormElements()
        parser.feed(response.get_data(as_text=True))
        controls = [item for item in parser.elements if item['attrs'].get('name') == 'csrf_token']
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]['attrs']['type'], 'hidden')
        csrf = controls[0]['attrs']['value']
        with self.client.session_transaction() as current:
            self.assertEqual(set(current), {'password_recovery_id'})
            self.assertEqual(csrf, self.globals['recovery_grants'].csrf(current['password_recovery_id']))
        self.assertTrue(csrf)
        result = subprocess.run(
            ['node', str(Path(__file__).with_name('test_recovery_frontend.js')), '--initial-page'],
            input=json.dumps(parser.elements), text=True, capture_output=True, timeout=10,
        )
        # Do not echo HTML/CSRF values on a failed assertion.
        self.assertEqual(result.returncode, 0, 'Rendered-page JavaScript initialization regression failed.')
        self.isolated.auth.set_session.assert_not_called()
        self.isolated.auth.update_user.assert_not_called()
        self.assertEqual(self.supabase.mock_calls, [])

    def test_missing_duplicate_error_and_implicit_parameters_rejected(self):
        handle = self.pending()
        for query in ('', 'code=', 'code=a&code=b', 'code=private-code&error=private-error',
                      'error_description=private-detail', 'access_token=private-access&type=recovery',
                      'code=a&code_verifier=private-verifier', 'code=a&token_hash=private-hash'):
            self.denied(self.callback(query))
        self.assertIsNotNone(self.store.lookup(handle))
        self.factory.assert_not_called()

    def test_missing_unknown_expired_and_wrong_browser_pending_rejected(self):
        self.denied(self.callback())
        with self.client.session_transaction() as current:
            current['pending_recovery_id'] = 'unknown'
        self.denied(self.callback())
        self.store._clock = Mock(return_value=100)
        self.pending()
        self.assertEqual(self.callback(client=self.app.test_client()).status_code, 400)
        self.store._clock.return_value = 700
        self.denied(self.callback())
        self.factory.assert_not_called()

    def test_failed_exchange_retains_pending_and_releases_reservation(self):
        for code in ('bad_code_verifier', 'invalid_grant'):
            handle = self.pending()
            self.isolated.auth.exchange_code_for_session.side_effect = AuthApiError('private-detail', 400, code)
            self.denied(self.callback())
            self.assertIsNotNone(self.store.lookup(handle))
            reservation = self.store.reserve(handle)
            self.assertIsNotNone(reservation)
            self.store.release(handle, reservation[0])
        self.isolated.auth.exchange_code_for_session.side_effect = None
        self.assertEqual(self.callback().status_code, 303)

    def test_network_failure_is_safe_and_retryable(self):
        handle = self.pending()
        self.isolated.auth.exchange_code_for_session.side_effect = RuntimeError('private-error')
        self.denied(self.callback(), 503)
        self.assertIsNotNone(self.store.lookup(handle))
        self.assertEqual(self.store._reserved, {})

    def test_invalid_returned_session_or_user(self):
        for result in (None, NS(session=None, user=self.user), NS(session=self.result.session, user=None)):
            self.pending()
            self.isolated.auth.exchange_code_for_session.return_value = result
            self.denied(self.callback())
        self.isolated.auth.exchange_code_for_session.return_value = self.result
        for user in (None, NS(id='other', email='other@example.com'), NS(id='', email='')):
            handle = self.pending()
            self.isolated.auth.get_user.return_value = NS(user=user)
            self.denied(self.callback())
            self.assertIsNone(self.store.lookup(handle))

    def test_invalid_claims_and_non_recovery_methods_fail_closed(self):
        cases = [{'exp': self.now - 1}, {'sub': 'other'}, {'iss': 'https://other.example'},
                 {'aud': 'anon'}, {'session_id': ''}, {'amr': []},
                 {'amr': [{'method': 'recovery', 'timestamp': self.now - 601}]}]
        cases += [{'amr': [{'method': method, 'timestamp': self.now}]} for method in ('otp', 'password')]
        for changes in cases:
            handle = self.pending()
            self.isolated.auth.get_claims.return_value = {'claims': self.claims | changes}
            self.denied(self.callback())
            self.assertIsNone(self.store.lookup(handle))

    def test_validation_sdk_failure_after_exchange_consumes_pending(self):
        for method in ('get_claims', 'get_user'):
            handle = self.pending()
            getattr(self.isolated.auth, method).side_effect = AuthApiError('private-detail', 401, 'bad_jwt')
            self.denied(self.callback())
            self.assertIsNone(self.store.lookup(handle))
            getattr(self.isolated.auth, method).side_effect = None

    def test_replay_cannot_exchange_again_or_overwrite_login(self):
        with self.client.session_transaction() as current:
            current.update(user_id='normal', user_email='normal@example.com')
        handle = self.pending()
        self.assertEqual(self.callback().status_code, 303)
        self.assertEqual(self.callback().status_code, 400)
        with self.client.session_transaction() as current:
            current['pending_recovery_id'] = handle
        self.assertEqual(self.callback().status_code, 400)
        self.isolated.auth.exchange_code_for_session.assert_called_once()
        self.assertEqual(self.client.get('/auth/status').json, {'authenticated': True, 'email': 'normal@example.com'})

    def test_inflight_reservation_and_replacement_block_authorization(self):
        handle = self.pending()
        lease, _ = self.store.reserve(handle)
        self.denied(self.callback())
        self.factory.assert_not_called()
        self.store.release(handle, lease)
        def replace_during_exchange(_):
            self.store.consume(handle)
            return self.result
        self.isolated.auth.exchange_code_for_session.side_effect = replace_during_exchange
        self.denied(self.callback())

    def test_obsolete_post_and_cross_origin_cannot_authorize(self):
        self.pending()
        response = self.client.post('/auth/reset-callback', json={'access_token': 'private-access', 'type': 'recovery'})
        self.assertEqual(response.status_code, 405)
        self.denied(self.client.get('/auth/reset-callback?code=private-code', headers={'Origin': 'https://other.example'}), 403)
        self.factory.assert_not_called()

    def test_grant_expiry_and_logout(self):
        self.pending()
        self.callback()
        with patch('recovery_helpers.time.time', return_value=self.now + 601):
            self.denied(self.client.get('/reset-password'), 403)
        self.claims['session_id'] = 'second-session'
        self.pending()
        self.callback()
        self.client.post('/logout')
        self.denied(self.client.get('/reset-password'), 403)

    def test_diagnostics_and_query_logs_never_contain_credentials(self):
        self.pending()
        with self.assertLogs('rosago.recovery', level='WARNING') as captured:
            self.callback()
        for record in captured.records:
            self.assertIn(record.getMessage().removeprefix('[RosaGO recovery] '), CATEGORIES)
            self.assertIsNone(record.exc_info)
        self.assertNotIn('private-', ' '.join(captured.output))
        self.assertEqual(captured.records[-1].getMessage(), '[RosaGO recovery] RECOVERY_AUTHORIZED')
        record = logging.LogRecord('werkzeug', logging.INFO, '', 0, '%s',
            ('GET /auth/reset-callback?code=private-code HTTP/1.1',), None)
        logging.getLogger('werkzeug').filter(record)
        self.assertNotIn('private-', record.getMessage())

    def test_failure_page_has_no_browser_token_bridge(self):
        response = self.callback()
        self.assertNotIn(b'reset-callback.js', response.data)
        self.assertNotIn(b'Enable JavaScript', response.data)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertIn(b'<meta name="referrer" content="no-referrer">', response.data)
        self.assertEqual(self.client.get('/static/js/reset-callback.js').status_code, 404)


if __name__ == '__main__':
    unittest.main()
