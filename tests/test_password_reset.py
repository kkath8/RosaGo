import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock, patch

from supabase_auth.errors import AuthApiError
import test_registration
from test_recovery_callback import FormElements


class PasswordResetTests(unittest.TestCase):
    def setUp(self):
        test_registration.RegistrationTests.setUp(self)
        self.globals = self.app.view_functions['reset_password'].__globals__
        self.store = self.globals['recovery_grants']
        self.handle = self.store.issue('recovered', 'recovery-session', time.time()+600, 'private-access')
        with self.client.session_transaction() as current:
            current['password_recovery_id'] = self.handle
        self.csrf = self.store.csrf(self.handle)
        self.isolated = MagicMock()
        user = NS(id='recovered', email='test@example.com')
        self.isolated.auth.set_session.return_value = NS(user=user, session=NS(user=user))
        self.isolated.auth.update_user.return_value = NS(user=user)
        self.factory = Mock(return_value=self.isolated)
        replacement = patch.dict(self.globals, create_client=self.factory)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.data = {'new_password':'private-password-123', 'confirm_password':'private-password-123', 'csrf_token':self.csrf}

    def submit(self, client=None, **changes):
        return (client or self.client).post('/reset-password', data=self.data | changes)

    def test_get_requires_grant_and_never_exposes_credentials(self):
        page = self.client.get('/reset-password')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="new_password"', page.data)
        self.assertIn(b'name="confirm_password"', page.data)
        self.assertNotIn(b'private-access', page.data)
        self.assertNotIn(b'Preview only', page.data)
        self.assertEqual(self.app.test_client().get('/reset-password').status_code, 403)
        self.assertEqual(self.submit(client=self.app.test_client()).status_code, 403)
        self.factory.assert_not_called()

    def test_expired_grant_cannot_get_or_post(self):
        with patch('recovery_helpers.time.time', return_value=time.time()+601):
            self.assertEqual(self.submit().status_code, 403)
            self.assertEqual(self.client.get('/reset-password').status_code, 403)
        self.factory.assert_not_called()

    def test_backend_validation_never_calls_supabase(self):
        for changes in ({'new_password':''}, {'new_password':'        '}, {'new_password':'short'},
                        {'confirm_password':''}, {'confirm_password':'mismatch'}):
            response = self.submit(**changes)
            self.assertEqual(response.status_code, 400)
            self.assertNotIn(b'private-password', response.data)
            self.assertTrue(self.store.valid(self.handle))
        self.factory.assert_not_called()

    def test_csrf_and_origin_are_required(self):
        self.assertEqual(self.submit(csrf_token='').status_code, 403)
        self.assertEqual(self.submit(csrf_token='wrong').status_code, 403)
        response = self.client.post('/reset-password', data=self.data, headers={'Origin':'https://other.example'})
        self.assertEqual(response.status_code, 403)
        self.factory.assert_not_called()

    def test_csrf_rejection_message_is_post_only_and_fresh_get_is_clean(self):
        response = self.submit(csrf_token='')
        self.assertEqual(response.status_code, 403)
        self.assertIn(b'Please reload this page and try again.', response.data)
        page = self.client.get('/reset-password')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'Please reload this page and try again.', page.data)
        self.assertEqual(self.store.csrf(self.handle), self.csrf)
        self.assertTrue(self.store.valid(self.handle))
        self.factory.assert_not_called()

    def test_post_rejection_diagnostics_are_fixed_and_do_not_expose_data(self):
        cases = [
            ({}, {}, 'RESET_PASSWORD_CSRF_MISSING', 403),
            ({'csrf_token': ''}, {}, 'RESET_PASSWORD_CSRF_MISSING', 403),
            (self.data | {'csrf_token': 'private-wrong-token'}, {}, 'RESET_PASSWORD_CSRF_MISMATCH', 403),
            (self.data, {'Origin': 'null'}, 'RESET_PASSWORD_ORIGIN_REJECTED', 403),
            (self.data | {'new_password': ''}, {}, 'RESET_PASSWORD_VALIDATION_REJECTED', 400),
        ]
        for data, headers, label, status in cases:
            with self.subTest(label=label), self.assertLogs('rosago.recovery', level='WARNING') as logs:
                response = self.client.post('/reset-password', data=data, headers=headers)
            self.assertEqual(response.status_code, status)
            self.assertEqual([r.getMessage() for r in logs.records], [
                '[RosaGO recovery] RESET_PASSWORD_POST_RECEIVED', '[RosaGO recovery] ' + label])
            self.assertTrue(all(r.exc_info is None for r in logs.records))
        self.factory.assert_not_called()

    def test_local_origin_matching_is_exact(self):
        base = 'http://127.0.0.1:5000'
        client = self.app.test_client()
        with client.session_transaction(base_url=base) as current:
            current['password_recovery_id'] = self.handle
        # Empty passwords stop before any provider call after security checks pass.
        for origin in (None, base, 'null', 'http://localhost:5000',
                       'https://127.0.0.1:5000', 'http://127.0.0.1:5001', base + '/'):
            accepted = origin in (None, base)
            with self.subTest(origin=origin), self.assertLogs('rosago.recovery', level='WARNING') as logs:
                response = client.post('/reset-password', base_url=base,
                    data={'csrf_token': self.csrf}, headers={} if origin is None else {'Origin': origin})
            self.assertEqual(response.status_code, 400 if accepted else 403)
            label = 'RESET_PASSWORD_VALIDATION_REJECTED' if accepted else 'RESET_PASSWORD_ORIGIN_REJECTED'
            self.assertEqual(logs.records[-1].getMessage(), '[RosaGO recovery] ' + label)
        self.factory.assert_not_called()

    def test_every_accepted_origin_still_requires_valid_csrf(self):
        base = 'http://127.0.0.1:5000'
        client = self.app.test_client()
        with client.session_transaction(base_url=base) as current:
            current['password_recovery_id'] = self.handle
        for origin in (None, base):
            headers = {} if origin is None else {'Origin': origin}
            for token in (None, '', 'wrong-token', self.csrf):
                with self.subTest(origin=origin, valid_csrf=token == self.csrf):
                    data = {} if token is None else {'csrf_token': token}
                    # Valid CSRF reaches password validation; no provider call.
                    response = client.post('/reset-password', base_url=base, data=data, headers=headers)
                    self.assertEqual(response.status_code, 400 if token == self.csrf else 403)
                    if token == self.csrf:
                        self.assertIn(b'Please enter a new password.', response.data)
        self.factory.assert_not_called()

    def test_reset_form_policy_preserves_native_post_origin_on_get_and_errors(self):
        pages = [self.client.get('/reset-password'), self.submit(csrf_token=''),
                 self.submit(new_password='')]
        self.assertEqual([page.status_code for page in pages], [200, 403, 400])
        for page in pages:
            self.assertEqual(page.headers['Referrer-Policy'], 'same-origin')
            self.assertEqual(page.headers['Cache-Control'], 'no-store')
            self.assertIn("form-action 'self'", page.headers['Content-Security-Policy'])
            parser = FormElements()
            parser.feed(page.get_data(as_text=True))
            policies = [e['attrs']['content'] for e in parser.elements
                        if e['tag'] == 'meta' and e['attrs'].get('name') == 'referrer']
            self.assertEqual(policies, ['same-origin'])
        self.factory.assert_not_called()

    def test_rendered_native_controls_include_stable_csrf_after_52_seconds(self):
        parser = FormElements()
        parser.feed(self.client.get('/reset-password').get_data(as_text=True))
        form = next(e for e in parser.elements if e['attrs'].get('id') == 'reset-password-form')
        self.assertEqual(form['attrs']['method'], 'post')
        self.assertEqual(form['attrs']['action'], '/reset-password')
        buttons = [e['attrs'] for e in parser.elements if e['tag'] == 'button']
        self.assertEqual([b['type'] for b in buttons], ['button', 'button', 'submit'])
        # Serialize the rendered enabled, named inputs as a native form would.
        inputs = [e['attrs'] for e in parser.elements if e['tag'] == 'input']
        data = {a['name']: a.get('value', '') for a in inputs if 'name' in a and 'disabled' not in a}
        self.assertEqual(data['csrf_token'], self.csrf)
        with patch('recovery_helpers.time.time', return_value=time.time() + 52):
            self.assertEqual(self.store.csrf(self.handle), self.csrf)
            self.assertEqual(self.client.get('/reset-password').status_code, 200)
            response = self.client.post('/reset-password', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Please enter a new password.', response.data)
        self.assertEqual(self.store.csrf(self.handle), self.csrf)
        self.factory.assert_not_called()

    def test_grant_disappearing_between_valid_and_csrf_fails_closed(self):
        with patch.object(self.store, 'csrf', return_value=None):
            with self.assertLogs('rosago.recovery', level='WARNING') as logs:
                self.assertEqual(self.submit().status_code, 403)
        self.assertEqual(logs.records[-1].getMessage(), '[RosaGO recovery] RESET_PASSWORD_CSRF_MISSING')
        self.factory.assert_not_called()

    def test_success_authenticated_update_consumes_grant_and_redirects(self):
        response = self.submit()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.location, '/login?password_updated=1')
        self.isolated.auth.set_session.assert_called_once_with('private-access', '')
        self.isolated.auth.update_user.assert_called_once_with({'password':self.data['new_password']})
        self.isolated.auth.__exit__.assert_called_once()
        options = self.factory.call_args.kwargs['options']
        self.assertFalse(options.persist_session)
        self.assertFalse(options.auto_refresh_token)
        self.assertFalse(self.store.valid(self.handle))
        self.assertNotIn(self.handle, self.store._grants)
        with self.client.session_transaction() as current:
            self.assertEqual(dict(current), {})
        self.assertEqual(self.client.get('/auth/status').json, {'authenticated':False})
        page = self.client.get(response.location)
        self.assertIn(b'Your password has been updated successfully. You can now log in.', page.data)
        self.assertEqual(self.client.get('/reset-password').status_code, 403)
        self.assertEqual(self.submit().status_code, 403)
        self.assertEqual(self.supabase.mock_calls, [])

    def test_cookie_has_only_opaque_reference_and_normal_login_preserved(self):
        with self.client.session_transaction() as current:
            current.update(user_id='normal', user_email='normal@example.com')
        decoded = self.app.session_interface.get_signing_serializer(self.app).loads(self.client.get_cookie('session').value)
        self.assertEqual(decoded, {'password_recovery_id':self.handle, 'user_id':'normal', 'user_email':'normal@example.com'})
        self.submit()
        with self.client.session_transaction() as current:
            self.assertEqual(dict(current), {'user_id':'normal', 'user_email':'normal@example.com'})

    def test_wrong_recovered_user_is_rejected_before_update(self):
        self.isolated.auth.set_session.return_value.user = NS(id='other')
        self.assertEqual(self.submit().status_code, 403)
        self.isolated.auth.update_user.assert_not_called()
        self.assertFalse(self.store.valid(self.handle))

    def test_expiry_during_session_restoration_blocks_update(self):
        def restore(*args):
            self.store.revoke(self.handle)
            return NS(user=NS(id='recovered'), session=NS(user=NS(id='recovered')))
        self.isolated.auth.set_session.side_effect = restore
        self.assertEqual(self.submit().status_code, 403)
        self.isolated.auth.update_user.assert_not_called()

    def test_explicit_provider_rejection_allows_retry_without_echoing_password(self):
        for status, code in ((422,'weak_password'), (429,'over_request_rate_limit')):
            self.isolated.auth.update_user.side_effect = AuthApiError('private-error-password', status, code)
            response = self.submit()
            self.assertEqual(response.status_code, 400)
            self.assertNotIn(b'private-', response.data)
            self.assertTrue(self.store.valid(self.handle))
            self.assertEqual(self.store._busy, {})
        self.isolated.auth.update_user.side_effect = None
        self.assertEqual(self.submit().status_code, 303)

    def test_network_uncertainty_revokes_grant_and_prevents_retry(self):
        self.isolated.auth.update_user.side_effect = RuntimeError('private-error-password')
        response = self.submit()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private-', response.data)
        self.assertFalse(self.store.valid(self.handle))
        self.assertEqual(self.submit().status_code, 403)
        self.isolated.auth.update_user.assert_called_once()

    def test_auth_failure_revokes_grant(self):
        self.isolated.auth.set_session.side_effect = AuthApiError('private-detail', 401, 'bad_jwt')
        self.submit()
        self.assertFalse(self.store.valid(self.handle))
        self.isolated.auth.update_user.assert_not_called()

    def test_server_error_or_request_timeout_does_not_allow_ambiguous_retry(self):
        for status in (408, 500, 503):
            handle = self.store.issue('recovered', 'session-' + str(status), time.time()+600, 'private-access')
            with self.client.session_transaction() as current:
                current['password_recovery_id'] = handle
            self.data['csrf_token'] = self.store.csrf(handle)
            self.isolated.auth.update_user.side_effect = AuthApiError('private-error', status, 'unexpected_failure')
            self.submit()
            self.assertFalse(self.store.valid(handle))
            self.assertEqual(self.submit().status_code, 403)

    def test_unexpected_update_result_is_consumed(self):
        self.isolated.auth.update_user.return_value = NS(user=NS(id='other'))
        self.assertEqual(self.submit().status_code, 503)
        self.assertFalse(self.store.valid(self.handle))

    def test_concurrent_and_replayed_update_cannot_both_succeed(self):
        other = self.app.test_client()
        other.set_cookie('session', self.client.get_cookie('session').value)
        started, finish = Event(), Event()
        def update(attributes):
            started.set()
            if not finish.wait(5):
                raise RuntimeError('test-timeout')
            return NS(user=NS(id='recovered'))
        self.isolated.auth.update_user.side_effect = update
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.submit)
            try:
                self.assertTrue(started.wait(5))
                self.assertEqual(self.submit(client=other).status_code, 409)
            finally:
                finish.set()
            self.assertEqual(pending.result().status_code, 303)
        self.assertEqual(self.submit(client=other).status_code, 403)
        self.isolated.auth.update_user.assert_called_once()

    def test_diagnostics_contain_only_fixed_labels(self):
        with self.assertLogs('rosago.recovery', level='WARNING') as logs:
            self.submit()
        self.assertEqual([r.getMessage() for r in logs.records], [
            '[RosaGO recovery] '+x for x in ('RESET_PASSWORD_POST_RECEIVED',
            'RECOVERY_PASSWORD_UPDATE_STARTED', 'RESET_PASSWORD_UPDATE_STARTED',
            'RECOVERY_GRANT_CONSUMED','RECOVERY_PASSWORD_UPDATE_SUCCEEDED',
            'RESET_PASSWORD_UPDATE_SUCCEEDED')])
        self.assertTrue(all(r.exc_info is None for r in logs.records))


if __name__ == '__main__':
    unittest.main()
