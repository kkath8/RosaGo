"""Local, network-blocked tests with ONE cookie jar and two verified actors."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import time
import unittest
from unittest.mock import patch

import httpx
from flask import Flask, session

from normal_auth_coordinator import VerifiedLoginCredentials
from session_realms import (AdminWebStore, LoginChallenges, RealmSessionInterface,
                            AdminBrowserSession, init_session_realms)
import test_registration
from test_public_layout import Document


A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
ORIGIN = {'Origin': 'http://localhost'}


class IndependentSessionTests(unittest.TestCase):
    setUp_base = test_registration.RegistrationTests.setUp

    def setUp(self):
        self.setUp_base()
        self.user = self.app.extensions['rosago_normal_auth']
        self.admin = self.app.extensions['rosago_admin_auth']
        self.requests, self.clients, self.mutations = [], [], []
        self.member = True
        self.addCleanup(patch.stopall)
        patch.dict('os.environ', ROSAGO_DESTINATION_ENVIRONMENT_ENABLED='true').start()

        def respond(request):
            self.requests.append(request)
            token = request.headers.get('authorization')
            if request.url.path.endswith('/rosago_is_admin'):
                return httpx.Response(200, json=self.member and token == 'Bearer admin-access')
            if request.url.path.endswith('/rosago_admin_mutate_destination'):
                values = json.loads(request.content)
                self.mutations.append((token, values))
                return httpx.Response(200, json={'slug': 'local-disposable', 'status': 'draft'})
            if request.url.path.endswith('/profiles'):
                return httpx.Response(200, json=[])
            raise AssertionError('Unexpected local request: ' + request.url.path)

        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
            self.clients.append(client)
            return client
        for dependencies in (self.user, self.admin):
            dependencies.adapters._http_factory = factory
            dependencies.coordinator._clients = dependencies.adapters.database_client
        self.addCleanup(lambda: self.assertTrue(all(c.is_closed for c in self.clients)))
        self.user_credentials = VerifiedLoginCredentials(A, 'user-a@example.invalid', 'user-access',
            'user-refresh', time.time() + 3600, 'provider-user-session')
        self.admin_credentials = VerifiedLoginCredentials(B, 'admin-b@example.invalid', 'admin-access',
            'admin-refresh', time.time() + 3600, 'provider-admin-session')

    def login_user(self):
        # Exercise the rendered login form in the same real cookie jar.
        page = self.client.get('/login')
        self.assertEqual(page.status_code, 200)
        csrf = Document(page.get_data(as_text=True)).find('input', name='csrf_token')[0].attrs['value']
        with patch.object(self.user.adapters, 'password_login', return_value=self.user_credentials):
            response = self.client.post('/login', data={'email': 'user-a@example.invalid',
                'password': 'fixture-only', 'csrf_token': csrf}, headers=ORIGIN)
        self.assertEqual(response.status_code, 303)
        self.assertFalse(any('rosago_admin' in x for x in response.headers.getlist('Set-Cookie')))
        return response

    def login_admin(self, *, expected=303):
        page = self.client.get('/admin/login')
        self.assertEqual(page.status_code, 200)
        csrf = Document(page.get_data(as_text=True)).find('input', name='csrf_token')[0].attrs['value']
        with patch.object(self.admin.adapters, 'password_login', return_value=self.admin_credentials):
            response = self.client.post('/admin/login', data={'email': 'admin-b@example.invalid',
                'password': 'fixture-only', 'csrf_token': csrf}, headers=ORIGIN)
        self.assertEqual(response.status_code, expected)
        self.assertFalse(any(x.startswith('session=') for x in response.headers.getlist('Set-Cookie')))
        return response

    def handles(self):
        with self.client.session_transaction() as s:
            user_handle = s.get('auth_session_id')
        with self.client.session_transaction(path='/admin') as s:
            admin_handle = s.get('auth_session_id')
        return user_handle, admin_handle

    def assert_both(self):
        self.assertEqual(self.client.get('/auth/status').json,
                         {'authenticated': True, 'email': 'user-a@example.invalid'})
        page = self.client.get('/admin/account')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'admin-b@example.invalid', page.data)
        self.assertNotIn(b'user-a@example.invalid', page.data)

    def test_user_then_admin_same_cookie_jar(self):
        self.login_user()
        user_cookie = self.client.get_cookie('session').value
        self.login_admin()
        self.assertEqual(self.client.get_cookie('session').value, user_cookie)
        self.assert_both()
        u, a = self.handles()
        self.assertIsNotNone(self.user.store.resolve(u))
        self.assertIsNotNone(self.admin.store.resolve(a))
        self.assertIsNone(self.user.store.resolve(a))
        self.assertIsNone(self.admin.store.resolve(u))

    def test_admin_then_user_same_cookie_jar(self):
        self.login_admin()
        name = self.app.session_interface.cookie_name
        cookie = self.client.get_cookie(name, path='/admin').value
        self.login_user()
        self.assertEqual(self.client.get_cookie(name, path='/admin').value, cookie)
        self.assert_both()

    def test_user_logout_preserves_admin_and_admin_csrf(self):
        self.login_user(); self.login_admin()
        u, a = self.handles()
        before = self.admin.store.resolve(a)
        result = test_registration.post_user_logout(self)
        self.assertEqual(result.status_code, 303)
        self.assertIsNone(self.user.store.resolve(u))
        self.assertEqual(self.admin.store.resolve(a), before)
        self.assertEqual(self.client.get('/admin/help').status_code, 200)
        self.assertFalse(self.client.get('/auth/status').json['authenticated'])

    def test_admin_logout_preserves_user_and_recovery(self):
        self.login_user(); self.login_admin()
        u, a = self.handles()
        with self.client.session_transaction() as s:
            s['pending_recovery_id'] = 'opaque-pending-fixture'
        csrf = self.admin.store.resolve(a).csrf
        result = self.client.post('/admin/logout', data={'csrf_token': csrf}, headers=ORIGIN)
        self.assertEqual(result.status_code, 303)
        self.assertIsNone(self.admin.store.resolve(a))
        self.assertIsNotNone(self.user.store.resolve(u))
        self.assertTrue(self.client.get('/auth/status').json['authenticated'])
        with self.client.session_transaction() as s:
            self.assertEqual(s['pending_recovery_id'], 'opaque-pending-fixture')

    def test_independent_expiry_and_revocation(self):
        self.login_user(); self.login_admin()
        u, a = self.handles()
        record = self.admin.store.resolve(a)
        with patch.object(self.admin.store, '_clock', return_value=record.created_at + 28801):
            self.assertEqual(self.client.get('/admin/help').status_code, 302)
            self.assertTrue(self.client.get('/auth/status').json['authenticated'])
        self.login_admin()
        u, a = self.handles()
        self.user.store.revoke(u)
        self.assertFalse(self.client.get('/auth/status').json['authenticated'])
        self.assertEqual(self.client.get('/admin/help').status_code, 200)
        self.admin.store.revoke(a)
        self.assertEqual(self.client.get('/admin/help').status_code, 302)

    def test_user_expiry_does_not_touch_admin(self):
        self.login_user(); self.login_admin()
        u, _ = self.handles()
        record = self.user.store.resolve(u)
        with patch.object(self.user.store, '_clock', return_value=record.last_activity_at + 1801):
            self.assertFalse(self.client.get('/auth/status').json['authenticated'])
            self.assertEqual(self.client.get('/admin/help').status_code, 200)

    def test_nonmember_candidate_installs_no_admin_authority(self):
        self.login_user()
        self.member = False
        self.login_admin(expected=403)
        self.assertEqual(self.admin.store._records, {})
        self.assertTrue(self.client.get('/auth/status').json['authenticated'])
        self.assertEqual(self.client.get('/admin/help').status_code, 302)

    def test_user_cookie_never_grants_admin_even_for_admin_account(self):
        self.user_credentials = replace(self.user_credentials, user_id=B, access_token='admin-access')
        self.login_user()
        self.assertEqual(self.client.get('/admin/help').status_code, 302)
        self.assertEqual(self.client.get('/admin/login').status_code, 200)
        self.assertEqual(self.requests, [])

    def test_admin_cookie_never_grants_user(self):
        self.login_admin()
        self.assertFalse(self.client.get('/auth/status').json['authenticated'])
        self.assertEqual(self.client.get('/user').status_code, 302)

    def test_cross_realm_authenticated_csrf_rejected(self):
        self.login_user(); self.login_admin()
        u, a = self.handles()
        user_csrf, admin_csrf = self.user.store.resolve(u).csrf, self.admin.store.resolve(a).csrf
        self.assertEqual(self.client.post('/admin/logout', data={'csrf_token': user_csrf}, headers=ORIGIN).status_code, 403)
        self.assertEqual(self.client.post('/logout', data={'csrf_token': admin_csrf}, headers=ORIGIN).status_code, 403)
        self.assert_both()

    def test_login_csrf_cross_realm_and_replay_rejected(self):
        user_page = self.client.get('/login')
        user_csrf = Document(user_page.get_data(as_text=True)).find('input', name='csrf_token')[0].attrs['value']
        admin_page = self.client.get('/admin/login')
        admin_csrf = Document(admin_page.get_data(as_text=True)).find('input', name='csrf_token')[0].attrs['value']
        data = {'email': 'fixture@example.invalid', 'password': 'fixture-only'}
        for path, token in (('/login', admin_csrf), ('/admin/login', user_csrf)):
            self.assertEqual(self.client.post(path, data=data | {'csrf_token': token}, headers=ORIGIN).status_code, 403)
        challenges = self.app.extensions['rosago_login_challenges']
        self.assertTrue(challenges.valid('user', user_csrf, consume=True))
        self.assertEqual(self.client.post('/login', data=data | {'csrf_token': user_csrf}, headers=ORIGIN).status_code, 403)

    def test_missing_and_foreign_origin_login_logout_rejected(self):
        for path in ('/login', '/logout', '/admin/login', '/admin/logout'):
            self.assertIn(self.client.post(path, data={}).status_code, (302, 403))
        self.login_user(); self.login_admin()
        u, a = self.handles()
        for path, token in (('/logout', self.user.store.resolve(u).csrf),
                            ('/admin/logout', self.admin.store.resolve(a).csrf)):
            self.assertEqual(self.client.post(path, data={'csrf_token': token},
                headers={'Origin': 'https://foreign.invalid'}).status_code, 403)
        self.assert_both()

    def test_session_fixation_rotation_and_old_cookie_rejection(self):
        self.client.get('/admin/login')
        name = self.app.session_interface.cookie_name
        old = self.client.get_cookie(name, path='/admin').value
        self.login_admin()
        new = self.client.get_cookie(name, path='/admin').value
        self.assertNotEqual(old, new)
        self.assertIsNone(self.app.session_interface.store.read(old))
        self.client.set_cookie(name, old, path='/admin')
        self.assertEqual(self.client.get('/admin/help').status_code, 302)

    def test_duplicate_and_malformed_admin_cookies_fail_closed(self):
        name = self.app.session_interface.cookie_name
        client = self.app.test_client(use_cookies=False)
        for cookie in (name + '=bad', name + '=' + 'a'*43 + '; ' + name + '=' + 'b'*43):
            response = client.get('/admin/login', headers={'Cookie': cookie})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.headers.getlist('Set-Cookie'), [])

    def test_admin_mutation_uses_b_not_a_and_no_client_actor_field(self):
        self.login_user(); self.login_admin()
        _, a = self.handles()
        csrf = self.admin.store.resolve(a).csrf
        data = {'name': 'Local-only fixture', 'category': 'nature', 'description': 'Local-only test.',
                'address': 'Local-only fixture address', 'latitude': '', 'longitude': '',
                'environment': 'Indoor', 'csrf_token': csrf}
        with patch.dict('os.environ', ROSAGO_TOURISM_METADATA_ENABLED='false'):
            response = self.client.post('/admin/places/new', data=data, headers=ORIGIN)
        self.assertEqual(response.status_code, 303)
        token, payload = self.mutations[0]
        self.assertEqual(token, 'Bearer admin-access')
        self.assertEqual(set(payload), {'p_action', 'p_slug', 'p_expected_updated_at', 'p_values'})
        self.assertEqual(payload['p_values']['environment'], 'Indoor')
        self.assertEqual(self.admin.store.resolve(a).user_id, B)
        self.assertTrue(self.client.get('/auth/status').json['authenticated'])

    def test_busy_admin_refresh_does_not_block_user(self):
        self.login_user(); self.login_admin()
        _, a = self.handles()
        record = self.admin.store.resolve(a)
        lease, _ = self.admin.store.reserve_refresh(a)
        try:
            with patch.object(self.admin.coordinator, '_clock', return_value=record.access_expires_at - 30):
                self.assertEqual(self.client.get('/admin/help').status_code, 503)
                self.assertTrue(self.client.get('/auth/status').json['authenticated'])
        finally:
            self.admin.store.release_refresh(a, lease)

    def test_admin_errors_and_flashes_never_write_user_cookie(self):
        self.login_user(); self.login_admin()
        before = self.client.get_cookie('session').value
        for path in ('/admin/help', '/admin/not-found', '/admin/logout'):
            response = self.client.get(path)
            self.assertFalse(any(x.startswith('session=') for x in response.headers.getlist('Set-Cookie')))
        self.assertEqual(self.client.get_cookie('session').value, before)

    def test_admin_logout_preserves_real_recovery_grant(self):
        self.login_user(); self.login_admin()
        grants = self.app.view_functions['reset_password'].__globals__['recovery_grants']
        grant = grants.issue(A, 'recovery-provider-session', time.time() + 600, 'recovery-fixture-access')
        with self.client.session_transaction() as state:
            state['password_recovery_id'] = grant
        self.assertEqual(self.client.get('/reset-password').status_code, 200)
        _, a = self.handles()
        self.client.post('/admin/logout', data={'csrf_token': self.admin.store.resolve(a).csrf}, headers=ORIGIN)
        self.assertTrue(grants.valid(grant))
        self.assertEqual(self.client.get('/reset-password').status_code, 200)
        self.assertTrue(self.client.get('/auth/status').json['authenticated'])

    def test_recovery_grant_cannot_be_promoted_to_admin(self):
        self.login_user()
        grants = self.app.view_functions['reset_password'].__globals__['recovery_grants']
        grant = grants.issue(A, 'recovery-provider-session', time.time() + 600, 'recovery-fixture-access')
        with self.client.session_transaction(path='/admin') as state:
            state['auth_session_id'] = grant
        self.assertEqual(self.client.get('/admin/help').status_code, 302)
        self.assertEqual(self.admin.store._records, {})
        self.assertTrue(self.client.get('/auth/status').json['authenticated'])

    def test_http_stale_save_is_visible_and_never_overwrites_authority(self):
        self.login_user(); self.login_admin()
        interface = self.app.session_interface
        handle = self.client.get_cookie(interface.cookie_name, path='/admin').value
        values, version = interface.store.read(handle)
        stale = AdminBrowserSession(values, handle=handle, version=version)
        stale['notice'] = 'stale notice'
        self.assertTrue(interface.store.save(handle, version, values | {'notice': 'new notice'}))
        response = self.app.response_class('local fixture', status=200)
        interface.save_session(self.app, stale, response)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        self.assertEqual(interface.store.read(handle)[0]['notice'], 'new notice')
        self.assert_both()

    def test_candidate_transport_failure_does_not_install_or_leak(self):
        self.login_user()
        page = self.client.get('/admin/login')
        token = Document(page.get_data(as_text=True)).find('input', name='csrf_token')[0].attrs['value']
        with patch.object(self.admin.adapters, 'password_login', return_value=self.admin_credentials), \
             patch.object(self.admin.adapters, 'database_client', side_effect=RuntimeError('private-provider-detail')):
            response = self.client.post('/admin/login', data={'email': 'admin-b@example.invalid',
                'password': 'fixture-only', 'csrf_token': token}, headers=ORIGIN)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private-provider-detail', response.data)
        self.assertEqual(self.admin.store._records, {})
        self.assertTrue(self.client.get('/auth/status').json['authenticated'])

    def test_partial_admin_rotation_preserves_old_authority(self):
        from flask import request
        from admin_session_flask import establish_admin_session
        from normal_auth_flask import SessionEstablishmentError
        self.login_user(); self.login_admin()
        interface = self.app.session_interface
        browser_handle = self.client.get_cookie(interface.cookie_name, path='/admin').value
        old_values, _ = interface.store.read(browser_handle)
        before = set(self.admin.store._records)
        with self.app.test_request_context('/admin', headers={'Cookie': interface.cookie_name + '=' + browser_handle}):
            request.environ['rosago.realm_interface'] = interface
            with patch.object(AdminBrowserSession, 'update', side_effect=RuntimeError('private-store-detail')):
                with self.assertRaises(SessionEstablishmentError) as caught:
                    establish_admin_session(self.admin_credentials)
            self.assertIsNone(caught.exception.__context__)
        self.assertEqual(set(self.admin.store._records), before)
        self.assertEqual(interface.store.read(browser_handle)[0], old_values)
        self.assert_both()


class RealmStorageTests(unittest.TestCase):
    def test_single_use_login_challenge_under_concurrency(self):
        challenges = LoginChallenges()
        token = challenges.issue('admin')
        with ThreadPoolExecutor(max_workers=8) as executor:
            outcomes = list(executor.map(lambda _: challenges.valid('admin', token, consume=True), range(20)))
        self.assertEqual(sum(outcomes), 1)

    def test_stale_save_cannot_overwrite_or_resurrect(self):
        store = AdminWebStore()
        handle = store.create({'auth_session_id': 'authority', 'notice': 'old'})
        _, version = store.read(handle)
        self.assertTrue(store.save(handle, version, {'auth_session_id': 'authority', 'notice': 'new'}))
        self.assertFalse(store.save(handle, version, {'auth_session_id': 'stale'}))
        store.revoke(handle)
        self.assertFalse(store.save(handle, version + 1, {'auth_session_id': 'resurrected'}))

    def test_secure_cookie_attributes_and_production_guard(self):
        app = Flask(__name__)
        app.session_interface = RealmSessionInterface(AdminWebStore(), secure=True)
        @app.get('/admin/login')
        def login():
            session['challenge'] = 'local-fixture'
            return 'local fixture'
        response = app.test_client().get('/admin/login', base_url='https://localhost')
        cookie = response.headers['Set-Cookie']
        self.assertTrue(cookie.startswith('__Secure-rosago_admin_session='))
        for flag in ('Secure', 'HttpOnly', 'Path=/admin', 'SameSite=Lax'):
            self.assertIn(flag, cookie)
        self.assertNotIn('Domain=', cookie)
        with self.assertRaisesRegex(RuntimeError, 'shared session backend'):
            init_session_realms(Flask('production-guard'), mode='production')

    def test_store_capacity_and_expiration_are_bounded(self):
        now = [1]
        store = AdminWebStore(clock=lambda: now[0], capacity=1)
        handle = store.create({'login': 'challenge'})
        with self.assertRaises(RuntimeError):
            store.create({})
        now[0] += 1801
        self.assertIsNone(store.read(handle))
        self.assertIsNotNone(store.create({}))

    def test_login_throttling_is_independent_by_realm_and_expires(self):
        now = [1]
        challenges = LoginChallenges(clock=lambda: now[0])
        self.assertTrue(all(challenges.allow_attempt('admin', 'local-fixture') for _ in range(20)))
        self.assertFalse(challenges.allow_attempt('admin', 'local-fixture'))
        self.assertTrue(challenges.allow_attempt('user', 'local-fixture'))
        now[0] += 61
        self.assertTrue(challenges.allow_attempt('admin', 'local-fixture'))
