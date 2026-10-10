"""Offline tests for the normal-auth SDK boundary; no Flask/recovery integration."""
import base64
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import socket
import traceback
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import httpx
from supabase_auth import SyncGoTrueClient

from normal_auth_coordinator import AuthenticationRequired, SupabaseAdapters, VerifiedRefresh


class CountingTransport(httpx.MockTransport):
    def __init__(self, handler):
        super().__init__(handler)
        self.closes = 0

    def close(self):
        self.closes += 1
        super().close()


class NormalAuthAdapterTests(unittest.TestCase):
    url = 'https://adapter.example.invalid'
    public_key = 'sb_publishable_synthetic_public_fixture'

    def setUp(self):
        self.guards = []
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname',
                      'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Live network forbidden.'))
                self.guards.append(guard.start())
                self.addCleanup(guard.stop)
        self.owned = []
        self.requests = []

    def tearDown(self):
        for guard in self.guards:
            self.assertEqual(guard.call_count, 0, 'Real network was attempted.')
        for http, transport in self.owned:
            self.assertTrue(http.is_closed, 'Owned HTTP resource was not closed.')
            self.assertEqual(transport.closes, 1, 'HTTP transport must close exactly once.')

    @staticmethod
    def legacy_key(role):
        def encode(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
        # Structural key classification only, not a real provider-signed credential.
        return encode({'alg': 'HS256', 'typ': 'JWT'}) + '.' + encode({'role': role}) + '.c3ludGhldGlj'

    def http_factory(self, **kwargs):
        def provider(request):
            self.requests.append(request)
            return httpx.Response(200, json=[])
        transport = CountingTransport(provider)
        http = httpx.Client(transport=transport, **kwargs)
        self.owned.append((http, transport))
        return http

    def fake_sdk(self):
        user = NS(id='adapter-user', email='response@example.invalid')
        session = NS(user=user, access_token='adapter-new-access-secret',
                     refresh_token='adapter-new-refresh-secret', expires_at=2_000_003_600)
        confirmed = NS(id=user.id, email='verified@example.invalid', email_confirmed_at='verified')
        claims = {'sub': user.id, 'iss': self.url + '/auth/v1', 'aud': 'authenticated',
                  'role': 'authenticated', 'session_id': 'adapter-session',
                  'exp': session.expires_at,
                  'amr': [{'method': 'password', 'timestamp': 2_000_000_000}]}
        auth = Mock(spec=['refresh_session', 'get_claims', 'get_user', 'get_session', 'set_session'])
        auth.refresh_session.return_value = NS(session=session, user=user)
        auth.get_claims.return_value = {'claims': claims}
        auth.get_user.return_value = NS(user=confirmed)
        auth.get_session.side_effect = AssertionError('Implicit session forbidden.')
        auth.set_session.side_effect = AssertionError('Session restoration forbidden.')
        return NS(auth=auth), session, confirmed, claims

    def test_accepts_publishable_and_legacy_anon_configuration(self):
        for key in (self.public_key, self.legacy_key('anon')):
            with self.subTest(kind='publishable' if key.startswith('sb_') else 'anon'):
                adapter = SupabaseAdapters(self.url + '/', key, http_factory=self.http_factory)
                self.assertEqual(adapter.issuer, self.url + '/auth/v1')
                with adapter.database_client('accepted-user-token') as client:
                    self.assertTrue(client.supabase_key == key, 'Wrong public project key.')
                    self.assertTrue(client.options.headers['Authorization'] == 'Bearer accepted-user-token',
                                    'Missing user authorization.')
        self.assertEqual(len(self.requests), 0)

    def test_rejects_privileged_keys_before_client_creation(self):
        for key in (self.legacy_key('service_role'), 'sb_secret_synthetic_privileged_fixture'):
            sdk, http = Mock(), Mock()
            with self.assertRaises(ValueError) as raised:
                SupabaseAdapters(self.url, key, sdk_factory=sdk, http_factory=http)
            self.assertTrue(str(raised.exception) == 'Invalid normal-auth public configuration.')
            self.assertTrue(key not in str(raised.exception) + repr(raised.exception), 'Key leaked.')
            self.assertEqual(sdk.call_count, 0)
            self.assertEqual(http.call_count, 0)

    def test_refresh_uses_explicit_token_and_verifies_new_access_on_owned_clients(self):
        fixtures = [self.fake_sdk(), self.fake_sdk()]
        sdk = Mock(side_effect=[fixture[0] for fixture in fixtures])
        adapter = SupabaseAdapters(self.url, self.public_key, sdk_factory=sdk,
                                   http_factory=self.http_factory)
        for index, (client, session, confirmed, claims) in enumerate(fixtures):
            old_refresh = 'server-stored-refresh-' + str(index)
            result = adapter.refresh(old_refresh)
            self.assertIsInstance(result, VerifiedRefresh)
            self.assertTrue(client.auth.refresh_session.call_args.args == (old_refresh,), 'Wrong refresh input.')
            self.assertEqual(client.auth.refresh_session.call_count, 1)
            for method in (client.auth.get_claims, client.auth.get_user):
                self.assertEqual(method.call_count, 1)
                self.assertTrue(method.call_args.args == (session.access_token,), 'Wrong verification token.')
            self.assertEqual(client.auth.get_session.call_count, 0)
            self.assertEqual(client.auth.set_session.call_count, 0)
            self.assertTrue((result.user_id, result.user_email) == (confirmed.id, confirmed.email),
                            'Identity must come from verified user lookup.')
            self.assertTrue((result.response_user_id, result.session_user_id) ==
                            (client.auth.refresh_session.return_value.user.id, session.user.id))
            self.assertTrue((result.access_token, result.refresh_token, result.expires_at, result.claims) ==
                            (session.access_token, session.refresh_token, session.expires_at, claims))
            options = sdk.call_args_list[index].kwargs['options']
            self.assertIs(options.httpx_client, self.owned[index][0])
            self.assertFalse(options.persist_session)
            self.assertFalse(options.auto_refresh_token)
            self.assertTrue(self.owned[index][0].is_closed)
        self.assertEqual(sdk.call_count, 2)
        self.assertIsNot(self.owned[0][0], self.owned[1][0])
        self.assertEqual(len(self.requests), 0)

    def test_malformed_or_unverified_refresh_results_are_rejected(self):
        for case in ('missing_session', 'unconfirmed_user', 'missing_verified_claims',
                     'missing_claims', 'empty_claims', 'non_dictionary_claims'):
            with self.subTest(case=case):
                client, _, _, _ = self.fake_sdk()
                if case == 'missing_session':
                    client.auth.refresh_session.return_value.session = None
                elif case == 'unconfirmed_user':
                    client.auth.get_user.return_value.user.email_confirmed_at = None
                elif case == 'missing_verified_claims':
                    client.auth.get_claims.return_value = None
                else:
                    client.auth.get_claims.return_value = {
                        'missing_claims': {}, 'empty_claims': {'claims': {}},
                        'non_dictionary_claims': {'claims': []},
                    }[case]
                adapter = SupabaseAdapters(self.url, self.public_key,
                    sdk_factory=Mock(return_value=client), http_factory=self.http_factory)
                with self.assertRaises(AuthenticationRequired):
                    adapter.refresh('server-stored-refresh-secret')

    def test_direct_refresh_failures_have_no_sensitive_exception_chain(self):
        for stage in ('refresh_session', 'get_claims', 'get_user'):
            with self.subTest(stage=stage):
                client, session, _, _ = self.fake_sdk()
                protected = (session.access_token, session.refresh_token,
                             'server-stored-refresh-secret', 'private-provider-diagnostic')
                getattr(client.auth, stage).side_effect = RuntimeError(' | '.join(protected))
                adapter = SupabaseAdapters(self.url, self.public_key,
                    sdk_factory=Mock(return_value=client), http_factory=self.http_factory)
                output, rendered = io.StringIO(), []
                with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level='DEBUG'):
                    with self.assertRaises(AuthenticationRequired) as raised:
                        try:
                            adapter.refresh(protected[2])
                        except AuthenticationRequired as error:
                            rendered.append(traceback.format_exc())
                            pending, seen = [error], set()
                            while pending:
                                current = pending.pop()
                                if current is None or id(current) in seen:
                                    continue
                                seen.add(id(current))
                                rendered.append(str(current) + repr(current))
                                pending.extend((current.__cause__, current.__context__))
                            raise
                self.assertTrue(str(raised.exception) == 'Normal authentication required.')
                self.assertTrue(output.getvalue() == '', 'Unexpected output.')
                for value in protected:
                    self.assertTrue(value not in ''.join(rendered), 'Sensitive exception detail leaked.')
                self.assertTrue(raised.exception.__cause__ is None, 'Exception cause retained.')
                self.assertTrue(raised.exception.__context__ is None, 'Exception context retained.')
                self.assertEqual(client.auth.refresh_session.call_count, 1)

    def test_real_sdk_clients_isolate_user_authorization_before_database_use(self):
        adapter = SupabaseAdapters(self.url, self.public_key, http_factory=self.http_factory)
        with (
            patch.object(SyncGoTrueClient, 'get_session', side_effect=AssertionError('Implicit auth forbidden.')) as implicit,
            patch.object(SyncGoTrueClient, 'refresh_session', side_effect=AssertionError('Refresh forbidden.')) as refresh,
        ):
            with adapter.database_client('user-a-access') as a, adapter.database_client('user-b-access') as b:
                self.assertIsNot(a, b)
                self.assertIsNot(a.auth, b.auth)
                self.assertIsNot(a.options.headers, b.options.headers)
                self.assertIsNot(a.postgrest.session, b.postgrest.session)
                for index, (client, token, other) in enumerate(((a, 'user-a-access', 'user-b-access'),
                                                               (b, 'user-b-access', 'user-a-access'))):
                    self.assertTrue(client.options.headers['Authorization'] == 'Bearer ' + token)
                    self.assertTrue(client.postgrest.headers['Authorization'] == 'Bearer ' + token)
                    self.assertTrue(other not in repr(client.options.headers) + repr(client.postgrest.headers))
                    self.assertFalse(client.options.persist_session)
                    self.assertFalse(client.options.auto_refresh_token)
                    self.assertFalse(client.auth._persist_session)
                    self.assertFalse(client.auth._auto_refresh_token)
                    self.assertIsNone(client.auth._in_memory_session)
                    self.assertIsNone(client.auth._refresh_token_timer)
                    self.assertIs(client.auth._http_client, self.owned[index][0])
                    self.assertIs(client.postgrest.session, self.owned[index][0])
                    self.assertEqual(len(self.requests), index)
                    # Only an in-memory fake response; no database or SQL is contacted.
                    client.table('offline_fixture').select('*').execute()
                    request = self.requests[-1]
                    self.assertTrue(request.headers['Authorization'] == 'Bearer ' + token)
                    self.assertTrue(request.headers['apikey'] == self.public_key)
                self.assertEqual(implicit.call_count, 0)
                self.assertEqual(refresh.call_count, 0)
        self.assertEqual(len(self.requests), 2)

    def test_sdk_construction_failure_closes_owned_http_resource(self):
        failure = RuntimeError('Synthetic construction failure.')
        sdk = Mock(side_effect=failure)
        adapter = SupabaseAdapters(self.url, self.public_key, sdk_factory=sdk, http_factory=self.http_factory)
        with self.assertRaises(RuntimeError) as raised:
            with adapter.database_client('synthetic-user-token'):
                self.fail('Construction failure yielded a client.')
        self.assertIs(raised.exception, failure)
        self.assertEqual(sdk.call_count, 1)
        self.assertEqual(len(self.owned), 1)

    def test_database_teardown_failure_propagates_without_retry_or_relabeling(self):
        failure = RuntimeError('Synthetic teardown failure.')
        def http_factory(**kwargs):
            http = self.http_factory(**kwargs)
            transport = self.owned[-1][1]
            close = transport.close
            def fail_close():
                close()
                raise failure
            transport.close = fail_close
            return http
        adapter = SupabaseAdapters(self.url, self.public_key, http_factory=http_factory)
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level='DEBUG'):
            with self.assertRaises(RuntimeError) as raised:
                with adapter.database_client('synthetic-user-token'):
                    pass
        self.assertIs(raised.exception, failure)
        self.assertTrue(output.getvalue() == '')
        self.assertEqual(len(self.owned), 1)


if __name__ == '__main__':
    unittest.main()
