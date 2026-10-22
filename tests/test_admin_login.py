"""Admin entry UI and auth lifecycle through offline request-owned clients."""
import time
import unittest
from unittest.mock import patch

from flask import before_render_template, g
from werkzeug.datastructures import MultiDict

from normal_auth_coordinator import VerifiedLoginCredentials, PasswordLoginError
from normal_auth_flask import SessionEstablishmentError
import test_admin_authorization as foundation
from test_public_layout import Document
import test_registration

ORIGIN = {'Origin': 'http://localhost'}


class AdminLoginTests(unittest.TestCase):
    setUp = foundation.AdminBoundaryTests.setUp
    tearDown = foundation.AdminBoundaryTests.tearDown
    protected = foundation.AdminBoundaryTests.protected

    def token(self):
        response = self.client.get('/admin/login')
        self.protected(response, 200)
        return Document(response.get_data(as_text=True)).find('input', name='csrf_token')[0].attrs['value']

    def payload(self):
        return MultiDict({'csrf_token': self.token(), 'email': 'admin@example.invalid', 'password': 'private-password'})

    def credentials(self):
        return VerifiedLoginCredentials('user-123', 'admin@example.invalid', 'fixture-access',
            'fixture-refresh', time.time() + 3600, 'fixture-session')

    def test_login_success_uses_normal_session_then_fresh_membership(self):
        data = self.payload()
        self.value = True
        with patch.object(self.dependencies.adapters, 'password_login', return_value=self.credentials()) as login:
            response = self.client.post('/admin/login', data=data, headers=ORIGIN)
        self.protected(response, 303)
        self.assertEqual(response.location, '/admin')
        login.assert_called_once_with('admin@example.invalid', 'private-password')
        with self.client.session_transaction() as session:
            self.assertEqual(set(session), {'auth_session_id'})
            self.assertIsNotNone(self.dependencies.store.resolve(session['auth_session_id']))
        self.protected(self.client.get('/admin'), 200)
        self.assertEqual(sum(r.url.path == '/rest/v1/rpc/rosago_is_admin' for r in self.requests), 2)

    def test_normal_user_login_retains_only_normal_authority(self):
        data = self.payload()
        with patch.object(self.dependencies.adapters, 'password_login', return_value=self.credentials()):
            response = self.client.post('/admin/login', data=data, headers=ORIGIN)
        self.protected(response, 403)
        self.assertIn(b'Admin access required', response.data)
        self.assertIn(b'Continue to User side', response.data)
        self.protected(self.client.get('/admin'), 403)

    def test_already_authenticated_states_and_template_isolation(self):
        test_registration.seed_normal_session(self)
        seen = []
        def inspect(sender, template, context, **kwargs):
            self.assertNotIn('auth', g)
            self.assertNotIn('admin', g)
            seen.append(template.name)
        with before_render_template.connected_to(inspect, self.app):
            self.protected(self.client.get('/admin/login'), 403)
        self.assertEqual(seen, ['admin/login.html'])
        self.value = True
        response = self.client.get('/admin/login')
        self.protected(response, 303)
        self.assertEqual(response.location, '/admin')
        self.status = 503
        self.protected(self.client.get('/admin/login'), 503)

    def test_form_csrf_origin_and_expiry_rejected_before_authentication(self):
        data = self.payload()
        cases = [(data, headers) for headers in ({}, {'Origin': 'null'}, {'Origin': 'https://foreign.invalid'})]
        for key in ('csrf_token', 'email', 'password'):
            missing = data.copy(); del missing[key]; cases.append((missing, ORIGIN))
            duplicate = data.copy(); duplicate.add(key, data[key]); cases.append((duplicate, ORIGIN))
        invalid = data.copy(); invalid['csrf_token'] = 'wrong'; cases.append((invalid, ORIGIN))
        extra = data.copy(); extra['role'] = 'admin'; cases.append((extra, ORIGIN))
        with patch.object(self.dependencies.adapters, 'password_login') as login:
            for form, headers in cases:
                self.protected(self.client.post('/admin/login', data=form, headers=headers), 403)
            with self.client.session_transaction() as session:
                session['admin_login_csrf_at'] = time.time() - 1801
            self.protected(self.client.post('/admin/login', data=data, headers=ORIGIN), 403)
            login.assert_not_called()
        self.assertEqual(self.requests, [])

    def test_sanitized_login_failures_do_not_query_membership(self):
        data = self.payload()
        for reason, status in [('invalid_credentials', 401), ('unconfirmed_email', 403),
                               ('throttled', 429), ('invalid_result', 401), ('service_failure', 503)]:
            error = PasswordLoginError(reason)
            error.args = ('private-provider-detail',)
            with patch.object(self.dependencies.adapters, 'password_login', side_effect=error):
                response = self.client.post('/admin/login', data=data, headers=ORIGIN)
            self.protected(response, status)
            self.assertNotIn(b'private-password', response.data)
            self.assertNotIn(b'Admin access required', response.data)
        self.assertEqual(self.requests, [])

    def test_membership_failure_after_login_and_establishment_failure(self):
        data = self.payload()
        self.status = 503
        with patch.object(self.dependencies.adapters, 'password_login', return_value=self.credentials()):
            self.protected(self.client.post('/admin/login', data=data, headers=ORIGIN), 503)
        self.protected(self.client.get('/admin'), 503)
        with self.client.session_transaction() as session:
            session.clear()
        data = self.payload()
        with patch.object(self.dependencies.adapters, 'password_login', return_value=self.credentials()), \
                patch('admin_routes.establish_normal_session', side_effect=SessionEstablishmentError()):
            self.protected(self.client.post('/admin/login', data=data, headers=ORIGIN), 503)

    def test_logout_requires_csrf_origin_and_revokes_normal_session(self):
        handle = test_registration.seed_normal_session(self)
        csrf = self.dependencies.store.resolve(handle).csrf
        self.protected(self.client.get('/admin/logout'), 405)
        for data, headers in [({}, ORIGIN), ({'csrf_token': 'wrong'}, ORIGIN),
                              ({'csrf_token': csrf}, {}), ({'csrf_token': csrf}, {'Origin': 'null'}),
                              ({'csrf_token': csrf, 'role': 'admin'}, ORIGIN)]:
            self.protected(self.client.post('/admin/logout', data=data, headers=headers), 403)
            self.assertIsNotNone(self.dependencies.store.resolve(handle))
        response = self.client.post('/admin/logout', data={'csrf_token': csrf}, headers=ORIGIN)
        self.protected(response, 303)
        self.assertEqual(response.location, '/admin/login')
        self.assertIsNone(self.dependencies.store.resolve(handle))
        self.protected(self.client.get('/admin'), 302)
        self.assertEqual(self.requests, [])  # Revoked membership cannot trap a user in a session.

    def test_dashboard_and_destinations_are_read_only(self):
        test_registration.seed_normal_session(self)
        self.value = True
        for path in ('/admin', '/admin/places'):
            response = self.client.get(path)
            self.protected(response, 200)
            page = Document(response.get_data(as_text=True))
            self.assertEqual(len(page.find('main')), 1)
            self.assertEqual(len(page.find('h1')), 1)
            self.assertTrue(page.find('nav', **{'aria-label': 'Admin navigation'}))
            self.assertTrue(page.find('form', action='/admin/logout'))
            self.assertEqual(page.stack, [])
            self.assertNotIn(b'AI usage', response.data)
        dashboard = self.client.get('/admin')
        self.assertNotIn(b'Destination counts are unavailable', dashboard.data)
        self.assertEqual(dashboard.data.count(b'class="metric-value">0'), 4)
        self.assertTrue(all(r.method in ('GET', 'HEAD') for r in self.requests if r.url.path == '/rest/v1/places'))
