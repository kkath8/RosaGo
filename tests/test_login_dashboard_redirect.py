import test_registration
"""Default Dashboard landing preserves auth checkpoints and fixed continuations."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from werkzeug.datastructures import MultiDict

import test_login as login
from test_public_layout import Document


class DashboardLoginRedirectTests(unittest.TestCase):
    setUp = login.LoginTests.setUp

    def test_normal_login_lands_on_existing_authenticated_dashboard_and_profile_remains(self):
        self.app.extensions['rosago_places'] = Mock(list_published=Mock(return_value=()))
        response = test_registration.post_user_login(self, data=self.credentials)
        self.assertEqual((response.status_code, response.location), (303, '/'))
        self.assertNotEqual(response.location, '/user')
        self.assertEqual(self.app.url_map.bind('localhost').match('/')[0], 'index')
        namespace = self.app.view_functions['index'].__globals__
        upcoming = Mock(return_value=())
        # This login fixture isolates storage; the Dashboard now reads upcoming
        # trips through its dedicated reader rather than list_user_trips.
        with patch.dict(namespace, list_dashboard_upcoming_trips=upcoming):
            dashboard = self.client.get(response.location)
        upcoming.assert_called_once()
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'Plan your next trip to <em>Santa Rosa</em>', dashboard.data)
        self.assertTrue(Document(dashboard.get_data(as_text=True)).find('a', href='/user'))
        self.assertTrue(self.client.get('/auth/status').json['authenticated'])
        self.assertEqual(self.client.get('/user').status_code, 200)

    def test_other_protected_page_keeps_existing_no_continuation_design(self):
        response = self.client.get('/user/settings')
        self.assertEqual((response.status_code, response.location), (302, '/login?login_required=1'))
        self.assertEqual(self.client.get(response.location).status_code, 200)
        response = test_registration.post_user_login(self, data=self.credentials)
        self.assertEqual((response.status_code, response.location), (303, '/'))

    def test_only_existing_slug_continuation_is_supported_and_next_cannot_redirect(self):
        for next_value in ('https://attacker.invalid', '//attacker.invalid', '/user/settings',
                           '/admin', 'javascript:alert(1)'):
            response = test_registration.post_user_login(self, data=self.credentials | {'next': next_value})
            self.assertEqual((response.status_code, response.location), (303, '/'))
        response = test_registration.post_user_login(self, data=self.credentials | {
            'next': 'https://attacker.invalid', 'add_place': 'kanin-club'})
        self.assertEqual((response.status_code, response.location), (303, '/user/trips/add-place/kanin-club'))
        duplicated = MultiDict(self.credentials)
        duplicated.add('add_place', 'kanin-club'); duplicated.add('add_place', 'other')
        self.assertEqual(test_registration.post_user_login(self, data=duplicated).location, '/')

    def test_failed_login_stays_on_form_without_authority_or_redirect(self):
        self.login_client.auth.sign_in_with_password.side_effect = login.AuthApiError(
            'private-provider-message', 400, 'invalid_credentials')
        response = test_registration.post_user_login(self, data=self.credentials)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('Location', response.headers)
        self.assertIn(b'Invalid email or password.', response.data)
        self.assertNotIn(b'private-provider-message', response.data)
        with self.client.session_transaction() as session:
            self.assertNotIn('auth_session_id', session)

    def test_verified_email_still_requires_login_then_defaults_to_dashboard(self):
        provider = Mock(verify=Mock(return_value=True))
        self.app.extensions['rosago_email_verification'] = provider
        response = test_registration.post_public_form(self, '/register', data=self.valid)
        self.assertEqual((response.status_code, response.location), (303, '/verify-email'))
        with self.client.session_transaction() as session:
            pending = self.app.extensions['rosago_email_pending'].get(session['pending_email_verification'])
        response = self.client.post('/verify-email', data={'csrf_token': pending.csrf, 'code': '123456'},
                                    headers={'Origin': 'http://localhost'})
        self.assertEqual((response.status_code, response.location), (303, '/verify-email'))
        success = self.client.get(response.location)
        self.assertTrue(Document(success.get_data(as_text=True)).find('a', href='/login'))
        self.assertFalse(self.client.get('/auth/status').json['authenticated'])
        self.assertEqual(self.client.get('/login').status_code, 200)
        response = test_registration.post_user_login(self, data=self.credentials)
        self.assertEqual((response.status_code, response.location), (303, '/'))

    def test_password_reset_still_returns_to_login_then_dashboard(self):
        grants = self.app.view_functions['reset_password'].__globals__['recovery_grants']
        handle = grants.issue(self.result.user.id, 'recovery-session', time.time() + 600, 'recovery-access')
        with self.client.session_transaction() as session:
            session['password_recovery_id'] = handle
        self.login_client.auth.set_session.return_value = self.result
        self.login_client.auth.update_user.return_value = SimpleNamespace(user=self.result.user)
        response = self.client.post('/reset-password', data={
            'csrf_token': grants.csrf(handle), 'new_password': 'Abcdef1!', 'confirm_password': 'Abcdef1!'},
            headers={'Origin': 'http://localhost'})
        self.assertEqual((response.status_code, response.location), (303, '/login?password_updated=1'))
        self.assertFalse(grants.valid(handle))
        self.assertFalse(self.client.get('/auth/status').json['authenticated'])
        self.assertEqual(self.client.get(response.location).status_code, 200)
        response = test_registration.post_user_login(self, data=self.credentials)
        self.assertEqual((response.status_code, response.location), (303, '/'))
