"""Opt-in REAL loopback Redis tests. No real provider accounts or credentials.

Run with ROSAGO_TEST_REDIS_URL=redis://127.0.0.1:16379/0.
The unique namespace is removed afterward; never FLUSHDB/FLUSHALL.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
import base64
import json
import os
from pathlib import Path
import multiprocessing
import runpy
import secrets
import socket
import time
from threading import Event
import unittest
from unittest.mock import Mock, MagicMock, patch
from types import SimpleNamespace as NS

import httpx
import redis
from flask import Flask, session

from normal_auth_coordinator import VerifiedLoginCredentials, NormalAuthCoordinator, SessionBusy
from redis_session_store import (SessionCipher, RedisRealm, RedisModel, local_realms,
                                 )
from redis_session_flask import (SharedSessionInterface, begin_login, finish_login,
                                 shared_logout, validate_https_configuration)
from session_realms import SessionStorageUnavailable, init_session_realms
from protected_session_authority import ProtectedRevisionAuthority, AuthorityBinding
from protected_authority_fixture import TestMetadataService
from test_public_layout import Document


URL = os.environ.get('ROSAGO_TEST_REDIS_URL')
A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
ORIGIN = {'Origin': 'http://localhost'}


def process_probe(url, key, namespace, handle, output):
    client = redis.Redis.from_url(url, socket_timeout=2)
    try:
        realm = RedisRealm(client, SessionCipher({'test': key}, 'test'), namespace, 'user', 'test_epoch')
        record = RedisModel(realm, 'auth').resolve(handle)
        output.put(record.user_id if record else None)
    finally:
        client.close()


from redis_record_cases import RedisTests


@unittest.skipUnless(URL, 'Explicit local Redis integration URL required.')
class RedisApplicationTests(RedisTests):
    def setUp(self):
        super().setUp()
        self.workers = []
        self.requests = []
        self.member = True
        key = secrets.token_bytes(32)
        self.key_material = key
        environ = {
            'ROSAGO_AUTH_MODE': 'redis-local', 'ROSAGO_SESSION_NAMESPACE': self.namespace,
            'ROSAGO_SESSION_AUTHORITY_PATH': self.temp.name,
            'ROSAGO_SESSION_REDIS_USER_URL': URL, 'ROSAGO_SESSION_REDIS_ADMIN_URL': URL,
            'ROSAGO_USER_SESSION_EPOCH': 'test_epoch', 'ROSAGO_ADMIN_SESSION_EPOCH': 'test_epoch',
            'ROSAGO_SESSION_KEYRING': json.dumps({'current': 'test', 'keys': {'test': base64.b64encode(key).decode()}}),
            'FLASK_SECRET_KEY': secrets.token_hex(32), 'SUPABASE_URL': 'https://example.supabase.co',
            'SUPABASE_KEY': 'sb_publishable_synthetic_fixture',
        }
        self.cipher = SessionCipher({'test': key}, 'test')
        self.realms = {r: RedisRealm(self.client, self.cipher, self.namespace, r, 'test_epoch', authority=self.authority, unprotected_local_testing=True) for r in self.realms}
        self.metadata_fixture = TestMetadataService(self.temp.name,self.namespace,existing=self.authority)
        self.protected_authority = ProtectedRevisionAuthority(self.metadata_fixture,AuthorityBinding(**self.metadata_fixture.binding()))
        for _ in range(2):
            # Test-only service injection; normal factory has no configured service.
            with patch('dotenv.load_dotenv'), patch.dict(os.environ, environ), patch('supabase.create_client', return_value=Mock()), patch('redis_session_store.local_realms', side_effect=lambda env: local_realms(env,authority=self.protected_authority)):
                namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'app.py'))
            app = namespace['app']
            app.testing = True
            for realm in ('user', 'admin'):
                deps = app.extensions['rosago_normal_auth' if realm == 'user' else 'rosago_admin_auth']
                deps.adapters._http_factory = lambda **kw: httpx.Client(transport=httpx.MockTransport(self.respond), **kw)
                deps.coordinator._clients = deps.adapters.database_client
                deps.adapters.password_login = lambda email, password, r=realm: self.credentials(r)
            self.workers.append(app)
            self.addCleanup(lambda a=app: [r.client.close() for r in a.extensions['rosago_shared_sessions'].values()])
        self.browser = self.workers[0].test_client()
        self.other = self.workers[1].test_client()

    def respond(self, request):
        self.requests.append(request)
        if request.url.path.endswith('/rosago_is_admin'):
            return httpx.Response(200, json=self.member and request.headers.get('authorization') == 'Bearer admin-access')
        if request.url.path.endswith('/profiles'):
            return httpx.Response(200, json=[])
        if request.url.path.endswith('/rosago_admin_mutate_destination'):
            return httpx.Response(200, json={'slug': 'local-disposable', 'status': 'draft'})
        raise AssertionError('Unexpected provider request in isolated fixture.')

    def sync(self, source, target):
        for name, path in (('rosago_user_session_dev', '/'), ('rosago_admin_session_dev', '/admin')):
            cookie = source.get_cookie(name, path=path)
            if cookie:
                target.set_cookie(name, cookie.value, path=path)
            else:
                target.delete_cookie(name, path=path)

    def login(self, realm, browser=None):
        browser = browser or self.browser
        path = '/admin/login' if realm == 'admin' else '/login'
        page = browser.get(path)
        self.assertEqual(page.status_code, 200)
        token = Document(page.text).find('input', name='csrf_token')[0].attrs['value']
        response = browser.post(path, data={'email': realm + '@example.invalid', 'password': 'fixture-only', 'csrf_token': token}, headers=ORIGIN)
        self.assertEqual(response.status_code, 303, response.text)
        return response

    def assert_both(self, browser):
        self.assertEqual(browser.get('/auth/status').json, {'authenticated': True, 'email': 'user@example.invalid'})
        response = browser.get('/admin/account')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'admin@example.invalid', response.data)

    def test_both_orders_two_workers_independent_logout(self):
        for order in (('user', 'admin'), ('admin', 'user')):
            self.browser = self.workers[0].test_client()
            for realm in order:
                self.login(realm)
            self.sync(self.browser, self.other)
            self.assert_both(self.other)
            token = self.other.get('/auth/logout-token').json['csrf_token']
            response = self.other.post('/logout', data={'csrf_token': token}, headers=ORIGIN)
            self.assertIn(response.status_code, (302, 303))
            self.sync(self.other, self.browser)
            self.assertFalse(self.browser.get('/auth/status').json['authenticated'])
            self.assertEqual(self.browser.get('/admin/account').status_code, 200)

    def test_admin_logout_keeps_user_and_replay_denied(self):
        self.login('user')
        self.login('admin')
        old = self.browser.get_cookie('rosago_admin_session_dev', path='/admin').value
        page = self.browser.get('/admin/account')
        token = Document(page.text).find('input', name='csrf_token')[0].attrs['value']
        response = self.browser.post('/admin/logout', data={'csrf_token': token}, headers=ORIGIN)
        self.assertIn(response.status_code, (302, 303))
        self.assertTrue(self.browser.get('/auth/status').json['authenticated'])
        self.other.set_cookie('rosago_admin_session_dev', old, path='/admin')
        self.assertEqual(self.other.get('/admin/account').status_code, 302)

    def test_cross_realm_csrf_nonmember_and_actor_identity(self):
        self.login('user')
        token = self.browser.get('/auth/logout-token').json['csrf_token']
        self.assertEqual(self.browser.post('/admin/login', data={'email':'fixture', 'password':'fixture', 'csrf_token':token}, headers=ORIGIN).status_code, 403)
        self.member = False
        page = self.browser.get('/admin/login')
        token = Document(page.text).find('input', name='csrf_token')[0].attrs['value']
        self.assertEqual(self.browser.post('/admin/login', data={'email':'fixture', 'password':'fixture', 'csrf_token':token}, headers=ORIGIN).status_code, 403)
        self.member = True
        self.login('admin')
        self.sync(self.browser, self.other)
        self.assert_both(self.other)
        admin_requests = [r for r in self.requests if r.url.path.endswith('/rosago_is_admin')]
        self.assertTrue(admin_requests)
        self.assertTrue(all(r.headers['authorization'] == 'Bearer admin-access' for r in admin_requests))

    def test_http_outage_keeps_cookies_and_reconnect(self):
        self.login('user')
        cookie = self.browser.get_cookie('rosago_user_session_dev').value
        realm = self.workers[0].extensions['rosago_shared_sessions']['user']
        with patch.object(realm, 'now', side_effect=SessionStorageUnavailable('synthetic outage')):
            response = self.browser.get('/auth/status')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.headers.getlist('Set-Cookie'))
        self.assertEqual(self.browser.get_cookie('rosago_user_session_dev').value, cookie)
        self.assertTrue(self.browser.get('/auth/status').json['authenticated'])

    def test_secure_cookie_headers_and_no_routine_cookie_write(self):
        for app in self.workers:
            app.session_interface.secure = True
        page = self.browser.get('/login', base_url='https://localhost')
        header = page.headers['Set-Cookie']
        for value in ('__Host-rosago_user_session=', 'Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/'):
            self.assertIn(value, header)
        self.assertNotIn('Domain=', header)
        page = self.browser.get('/admin/login', base_url='https://localhost')
        self.assertIn('__Secure-rosago_admin_session=', page.headers['Set-Cookie'])
        self.assertIn('Path=/admin', page.headers['Set-Cookie'])

    def test_logout_wins_inflight_login_and_stale_browser_save(self):
        self.login('user')
        interface = self.workers[0].session_interface
        cookie = self.browser.get_cookie('rosago_user_session_dev').value
        store = self.store(kind='web')
        values, version = store.read(cookie)
        token = self.workers[0].extensions['rosago_login_challenges'].issue('user')
        values['user_login_csrf'] = token
        self.assertTrue(store.save(cookie, version, values))
        with self.workers[0].test_request_context('/login', headers={'Cookie': 'rosago_user_session_dev=' + cookie}):
            self.assertTrue(begin_login('user', token))
            with self.workers[1].test_request_context('/logout', headers={'Cookie': 'rosago_user_session_dev=' + cookie}):
                shared_logout()
            with self.assertRaises(SessionStorageUnavailable):
                finish_login(self.credentials())
        self.assertIsNone(store.read(cookie))
        self.assertFalse(store.save(cookie, version, values))

    def test_recovery_callback_reset_and_verification_across_workers(self):
        self.login('admin')
        first = self.workers[0].view_functions['reset_callback'].__globals__
        second = self.workers[1].view_functions['reset_callback'].__globals__
        handle = first['pending_recoveries'].create()
        with self.browser.session_transaction() as state:
            state['pending_recovery_id'] = handle
        self.sync(self.browser, self.other)
        user = NS(id=A, email='user@example.invalid')
        result = NS(user=user, session=NS(user=user, access_token='recovery-only', refresh_token='not-retained'))
        provider = MagicMock()
        provider.auth.exchange_code_for_session.return_value = result
        provider.auth.get_claims.return_value = {'claims': {
            'sub': A, 'iss': 'https://example.supabase.co/auth/v1', 'aud':'authenticated',
            'session_id':'local-recovery-session', 'exp':time.time()+600,
            'amr':[{'method':'recovery', 'timestamp':time.time()}]}}
        provider.auth.get_user.return_value = NS(user=user)
        provider.auth.set_session.return_value = result
        provider.auth.update_user.return_value = NS(user=user)
        with patch.dict(second, create_client=Mock(return_value=provider)):
            response = self.other.get('/auth/reset-callback?code=synthetic-only')
        self.assertEqual(response.status_code, 303)
        self.sync(self.other, self.browser)
        page = self.browser.get('/reset-password')
        self.assertEqual(page.status_code, 200)
        token = Document(page.text).find('input', name='csrf_token')[0].attrs['value']
        with patch.dict(first, create_client=Mock(return_value=provider)):
            response = self.browser.post('/reset-password', data={'csrf_token':token,
                'new_password':'Local-password-123!', 'confirm_password':'Local-password-123!'}, headers=ORIGIN)
        self.assertEqual(response.status_code, 303)
        provider.auth.update_user.assert_called_once()
        self.assertEqual(self.browser.get('/reset-password').status_code, 403)
        self.assertEqual(self.browser.get('/admin/account').status_code, 200)
        store = self.workers[0].extensions['rosago_email_pending']
        handle = store.create('new-user@example.invalid')
        with self.browser.session_transaction() as state:
            state['pending_email_verification'] = handle
        self.sync(self.browser, self.other)
        token = store.get(handle).csrf
        service = self.workers[1].extensions['rosago_email_verification']
        with patch.object(service, 'verify', return_value=True) as verify:
            response = self.other.post('/verify-email', data={'csrf_token':token, 'code':'123456'}, headers=ORIGIN)
        self.assertEqual(response.status_code, 303)
        verify.assert_called_once()
        self.assertTrue(store.get(handle).verified)
        self.assertFalse(self.other.get('/auth/status').json['authenticated'])

    def test_admin_mutation_uses_b_credentials_while_a_remains_user(self):
        self.login('user')
        self.login('admin')
        with self.browser.session_transaction(path='/admin') as state:
            auth_handle = state['auth_session_id']
        dependencies = self.workers[0].extensions['rosago_admin_auth']
        token = dependencies.store.resolve(auth_handle).csrf
        with patch.dict(os.environ, ROSAGO_TOURISM_METADATA_ENABLED='false', ROSAGO_DESTINATION_ENVIRONMENT_ENABLED='true'):
            response = self.browser.post('/admin/places/new', headers=ORIGIN, data={
                'name':'Synthetic fixture', 'category':'nature', 'description':'Local-only test.',
                'address':'Local fixture', 'latitude':'', 'longitude':'', 'environment':'Indoor', 'csrf_token':token})
        self.assertEqual(response.status_code, 303)
        mutations = [r for r in self.requests if r.url.path.endswith('/rosago_admin_mutate_destination')]
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0].headers['authorization'], 'Bearer admin-access')
        self.assertEqual(set(json.loads(mutations[0].content)), {'p_action','p_slug','p_expected_updated_at','p_values'})
        self.assertEqual(dependencies.store.resolve(auth_handle).user_id, B)
        self.assertTrue(self.browser.get('/auth/status').json['authenticated'])

    def test_browser_field_cas_merges_disjoint_changes_rejects_conflicts(self):
        self.login('user')
        app = self.workers[0]
        cookie = self.browser.get_cookie('rosago_user_session_dev').value
        headers = {'Cookie':'rosago_user_session_dev=' + cookie}
        with app.test_request_context('/user', headers=headers):
            session['first'] = 'one'
            with self.workers[1].test_request_context('/user', headers=headers):
                session['second'] = 'two'
                app.session_interface.save_session(app, session, app.response_class())
            response = app.response_class()
            app.session_interface.save_session(app, session, response)
            self.assertEqual(response.status_code, 200)
        values, _ = self.store(kind='web').read(cookie)
        self.assertEqual((values['first'], values['second']), ('one', 'two'))
        with app.test_request_context('/user', headers=headers):
            session['first'] = 'stale'
            with self.workers[1].test_request_context('/user', headers=headers):
                session['first'] = 'newer'
                app.session_interface.save_session(app, session, app.response_class())
            response = app.response_class()
            app.session_interface.save_session(app, session, response)
            self.assertEqual(response.status_code, 409)
        self.assertEqual(self.store(kind='web').read(cookie)[0]['first'], 'newer')

    def test_cross_realm_logout_helpers_cannot_revoke_other_realm(self):
        from normal_auth_flask import logout_normal_session, LocalLogoutError
        from admin_session_flask import logout_admin_session
        self.login('user')
        self.login('admin')
        for path, function in (('/admin/logout', logout_normal_session), ('/logout', logout_admin_session)):
            with self.workers[0].test_request_context(path):
                with self.assertRaises(LocalLogoutError):
                    function()
        self.assert_both(self.browser)

    def test_swapped_malformed_duplicate_and_legacy_cookies_grant_nothing(self):
        self.login('user')
        self.login('admin')
        user = self.browser.get_cookie('rosago_user_session_dev').value
        admin = self.browser.get_cookie('rosago_admin_session_dev', path='/admin').value
        raw = self.workers[1].test_client(use_cookies=False)
        self.assertFalse(raw.get('/auth/status', headers={'Cookie':'rosago_user_session_dev=' + admin}).json['authenticated'])
        self.assertEqual(raw.get('/admin/account', headers={'Cookie':'rosago_admin_session_dev=' + user}).status_code, 302)
        self.assertFalse(raw.get('/auth/status', headers={'Cookie':'session=legacy-cookie'}).json['authenticated'])
        for value in ('bad', user + '; rosago_user_session_dev=' + admin):
            response = raw.get('/auth/status', headers={'Cookie':'rosago_user_session_dev=' + value})
            self.assertEqual(response.status_code, 403)
            self.assertFalse(response.headers.getlist('Set-Cookie'))
        self.assertFalse(self.browser.get('/auth/status').headers.getlist('Set-Cookie'))

    def test_both_authenticated_cross_realm_csrf_rejected(self):
        self.login('user')
        self.login('admin')
        user_token = self.browser.get('/auth/logout-token').json['csrf_token']
        with self.browser.session_transaction(path='/admin') as state:
            admin_token = self.store('admin').resolve(state['auth_session_id']).csrf
        for path, token in (('/logout', admin_token), ('/admin/logout', user_token)):
            self.assertEqual(self.browser.post(path, data={'csrf_token':token}, headers=ORIGIN).status_code, 403)
        self.assert_both(self.browser)

    def test_http_expiry_does_not_expire_other_realm(self):
        self.login('user')
        self.login('admin')
        with self.browser.session_transaction() as state:
            handle = state['auth_session_id']
        self.short_expiry('auth', handle)
        time.sleep(.2)
        response = self.browser.get('/auth/status')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['authenticated'])
        self.assertEqual(self.browser.get('/admin/account').status_code, 200)

    def test_static_requests_never_consult_or_write_authority(self):
        self.login('user')
        realm=self.workers[0].extensions['rosago_shared_sessions']['user']
        with patch.object(realm,'snapshot',side_effect=AssertionError('Static request consulted authority.')):
            response=self.browser.get('/static/css/site.css')
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.headers.getlist('Set-Cookie'))

    def test_fresh_login_recovers_uncertain_credentials_without_touching_admin(self):
        self.login('user')
        self.login('admin')
        with self.browser.session_transaction() as state:
            handle=state['auth_session_id']
        store=self.workers[0].extensions['rosago_normal_auth'].store
        lease,_=store.reserve_refresh(handle)
        backend=store.backend
        with patch.object(backend.client,'eval',side_effect=redis.ConnectionError('Synthetic lost publish.')):
            with self.assertRaises(SessionStorageUnavailable):
                store.replace_credentials(handle,lease,**asdict(self.credentials()))
        page=self.browser.get('/login')
        self.assertEqual(page.status_code,503)
        token=Document(page.text).find('input',name='csrf_token')[0].attrs['value']
        response=self.browser.post('/login',data={'email':'user@example.invalid','password':'fixture-only','csrf_token':token},headers=ORIGIN)
        self.assertEqual(response.status_code,303)
        self.assert_both(self.browser)
