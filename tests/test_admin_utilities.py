"""Own-account display and Admin utilities, with no profile or catalog mutations."""
import unittest

import httpx
from flask import before_render_template, g

import test_admin_authorization as foundation
import test_registration
from normal_auth_coordinator import AuthenticatedContext
from profile_service import UserProfile
from test_public_layout import Document

PATHS = ('/admin/account', '/admin/settings', '/admin/help', '/admin/about')
ORIGIN = {'Origin': 'http://localhost'}


class AdminUtilityTests(unittest.TestCase):
    setUp = foundation.AdminBoundaryTests.setUp
    tearDown = foundation.AdminBoundaryTests.tearDown
    protected = foundation.AdminBoundaryTests.protected

    def install_account(self, *, missing=False, failure=False, no_names=False):
        handle = test_registration.seed_normal_session(self)
        self.value = True
        self.profile_row = dict(id='user-123', first_name=None if no_names else 'Admin <Name>',
                                last_name=None if no_names else 'Fixture', created_at='2026-10-19T04:00:00Z')

        def respond(request):
            self.requests.append(request)
            self.assertEqual(request.headers['authorization'], 'Bearer fixture-access')
            if request.url.path.endswith('/rosago_is_admin'):
                return httpx.Response(200, json=self.value)
            self.assertEqual(request.url.path, '/rest/v1/profiles')
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.params['select'], 'id,first_name,last_name,created_at')
            self.assertEqual(request.url.params['id'], 'eq.user-123')
            self.assertEqual(request.url.params['limit'], '2')
            if failure:
                return httpx.Response(503, json={'message': 'private-provider-detail'})
            return httpx.Response(200, json=[] if missing else [self.profile_row])
        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
            self.clients.append(client)
            return client
        self.dependencies.adapters._http_factory = factory
        return handle

    def test_all_utilities_require_authentication_and_fresh_membership(self):
        for path in PATHS:
            self.protected(self.client.get(path), 302)
        self.assertEqual(self.requests, [])
        self.install_account()
        self.value = False
        self.requests.clear()
        for path in PATHS:
            self.protected(self.client.get(path), 403)
        self.assertTrue(all(r.url.path.endswith('/rosago_is_admin') for r in self.requests))

    def test_account_uses_only_own_profile_and_safe_display_values(self):
        self.install_account()
        seen = []
        def inspect(sender, template, context, **kwargs):
            self.assertNotIn('auth', g)
            self.assertFalse(any(isinstance(v, (AuthenticatedContext, UserProfile)) for v in context.values()))
            seen.append(template.name)
        with before_render_template.connected_to(inspect, self.app):
            response = self.client.get('/admin/account')
        self.protected(response, 200)
        self.assertEqual(seen, ['admin/account.html'])
        self.assertIn(b'Admin &lt;Name&gt; Fixture', response.data)
        self.assertIn(b'ana@example.com', response.data)
        self.assertIn(b'Administrator', response.data)
        self.assertIn(b'Account information is read-only', response.data)
        for secret in (b'fixture-access', b'fixture-refresh', b'fixture-session', b'user-123',
                       b'created_at', b'auth_session_id', b'password_hash', b'<Name>'):
            self.assertNotIn(secret, response.data)
        self.assertEqual(len([r for r in self.requests if r.url.path.endswith('/profiles')]), 1)
        page = Document(response.get_data(as_text=True))
        for form in page.find('form'):
            self.assertEqual(form.attrs['action'], '/admin/logout')
        self.assertTrue(page.find('a', href='/forgot-password'))
        self.assertEqual(page.stack, [])

    def test_account_missing_name_or_provider_failure_does_not_invent_identity(self):
        for options, message in (({'missing': True}, b'Not provided'), ({'no_names': True}, b'Not provided'),
                                 ({'failure': True}, b'Temporarily unavailable')):
            self.install_account(**options)
            response = self.client.get('/admin/account')
            self.protected(response, 200)
            self.assertIn(message, response.data)
            self.assertIn(b'data-account-email', response.data)
            self.assertNotIn(b'private-provider-detail', response.data)

    def test_utility_pages_reject_account_selection_and_mutation_methods(self):
        self.install_account()
        for path in PATHS:
            self.requests.clear()
            self.protected(self.client.get(path + '?user_id=someone-else'), 400)
            self.assertFalse(any(r.url.path.endswith('/profiles') for r in self.requests))
            for method in ('post', 'put', 'patch', 'delete'):
                self.protected(getattr(self.client, method)(path, data={'first_name': 'Changed'}), 405)
        self.assertFalse(any(r.method in ('PATCH', 'PUT', 'DELETE') for r in self.requests))

    def test_settings_reuses_shared_theme_and_has_no_travel_controls(self):
        self.install_account()
        response = self.client.get('/admin/settings')
        self.protected(response, 200)
        page = Document(response.get_data(as_text=True))
        for marker in (b'data-set-theme="light"', b'data-set-theme="dark"', b'js/theme.js', b'css/theme.css'):
            self.assertIn(marker, response.data)
        statuses = [n for n in page.find('p') if 'data-theme-status' in n.attrs]
        self.assertEqual(len(statuses), 1)
        self.assertIn('settings-theme-status', statuses[0].attrs['class'])
        self.assertEqual(page.find('input', type='text'), [])
        self.assertFalse(any(r.url.path.endswith('/profiles') for r in self.requests))
        for forbidden in (b'travel interests', b'Traveler Type', b'Budget Planner', b'itinerary pace',
                          b'personal-state.js', b'account-management.js', b'Compact table density'):
            self.assertNotIn(forbidden, response.data)

    def test_account_menu_links_valid_and_main_navigation_stays_focused(self):
        self.install_account()
        for path in PATHS:
            response = self.client.get(path)
            self.protected(response, 200)
            page = Document(response.get_data(as_text=True))
            menu = page.find('div', **{'class': 'admin-dropdown-panel admin-account-menu'})[0]
            menu_links = [n for n in page.find('a') if menu in n.ancestors]
            self.assertTrue(set(PATHS) <= {n.attrs['href'] for n in menu_links})
            self.assertTrue(any(n.attrs.get('href') == path and n.attrs.get('aria-current') == 'page' for n in menu_links))
            nav = page.find('nav', **{'aria-label': 'Admin navigation'})[0]
            self.assertEqual([n.attrs['href'] for n in page.find('a') if nav in n.ancestors],
                             ['/admin', '/admin/places', '/admin/users', '/admin/trips', '/admin/insights', '/admin/system'])
            self.assertTrue(page.find('nav', **{'aria-label': 'Mobile Admin navigation'}))

    def test_help_and_about_are_factual_and_do_not_expose_configuration(self):
        self.install_account()
        help_response = self.client.get('/admin/help')
        self.protected(help_response, 200)
        for phrase in (b'Published', b'Draft', b'Archived', b'Local', b'Common', b'Unclassified is not Common',
                       b'Unknown is not assumed to be Outdoor', b'Indoor', b'Covered', b'Mixed', b'Outdoor',
                       b'data-quality flags, not errors', b'Add Destination creates a Draft'):
            self.assertIn(phrase, help_response.data)
        about_response = self.client.get('/admin/about')
        self.protected(about_response, 200)
        for phrase in (b'RosaGo', b'Santa Rosa, Laguna', b'City Tourism', b'OpenStreetMap / Leaflet',
                       b'Open-Meteo', b'Gemini', b'does not define destination metadata'):
            self.assertIn(phrase, about_response.data)
        for response in (help_response, about_response):
            for secret in (b'SUPABASE_URL', b'GEMINI_API_KEY', b'FLASK_SECRET_KEY', b'example.supabase.co',
                           b'fixture-access', b'fixture-refresh', b'sb_publishable_'):
                self.assertNotIn(secret, response.data)
        self.assertFalse(any(r.url.path.endswith('/profiles') for r in self.requests))

    def test_logout_from_account_revokes_local_authority_and_protects_all_routes(self):
        handle = self.install_account()
        csrf = self.dependencies.store.resolve(handle).csrf
        response = self.client.post('/admin/logout', data={'csrf_token': csrf}, headers=ORIGIN)
        self.protected(response, 303)
        self.assertEqual(response.location, '/admin/login')
        self.assertIsNone(self.dependencies.store.resolve(handle))
        self.requests.clear()
        for path in (*PATHS, '/admin', '/admin/places', '/admin/insights'):
            self.protected(self.client.get(path), 302)
        self.assertEqual(self.requests, [])

    def test_user_logout_still_uses_its_existing_route_and_revokes_normal_session(self):
        handle = self.install_account()
        response = self.client.post('/logout', headers=ORIGIN)
        self.assertEqual(response.status_code, 303)
        self.assertIsNone(self.dependencies.store.resolve(handle))
        self.protected(self.client.get('/admin/account'), 302)
