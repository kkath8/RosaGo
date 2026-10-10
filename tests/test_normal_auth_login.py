"""Offline password-login trust contract; no Flask or store integration."""
from asyncio import CancelledError
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, fields
import io
import socket
import traceback
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import httpx
from supabase_auth.errors import AuthApiError, AuthInvalidJwtError

import normal_auth_coordinator as auth_module
from normal_auth_store import NormalAuthStore
from test_normal_auth_adapters import CountingTransport


class NormalAuthLoginTests(unittest.TestCase):
    now = 2_000_000_000
    url = 'https://login.example.invalid'
    email = 'submitted@example.invalid'
    password = 'synthetic-password-secret'

    def setUp(self):
        self.guards, self.owned = [], []
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname',
                      'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Live network forbidden.'))
                self.guards.append(guard.start())
                self.addCleanup(guard.stop)
        guard = patch.object(NormalAuthStore, 'create', side_effect=AssertionError('Store creation forbidden.'))
        self.create = guard.start()
        self.addCleanup(guard.stop)

    def tearDown(self):
        self.create.assert_not_called()
        for guard in self.guards:
            guard.assert_not_called()
        for http, transport in self.owned:
            self.assertTrue(http.is_closed)
            self.assertEqual(transport.closes, 1)

    def http_factory(self, **kwargs):
        transport = CountingTransport(Mock(side_effect=AssertionError('Unexpected HTTP request.')))
        http = httpx.Client(transport=transport, **kwargs)
        self.owned.append((http, transport))
        return http

    def fixture(self):
        session = NS(user=NS(id='verified-user'), access_token='returned-access-secret',
                     refresh_token='returned-refresh-secret', expires_at=self.now + 3600)
        response = NS(session=session, user=NS(id='verified-user'))
        user = NS(id='verified-user', email='verified@example.invalid', email_confirmed_at='confirmed')
        claims = dict(sub=user.id, session_id='verified-session', iss=self.url + '/auth/v1',
                      aud='authenticated', role='authenticated', exp=self.now + 1800,
                      amr=[{'method': 'password', 'timestamp': self.now}])
        auth = Mock(spec=['sign_in_with_password', 'get_claims', 'get_user', 'get_session', 'set_session'])
        auth.sign_in_with_password.return_value = response
        auth.get_claims.return_value = {'claims': claims}
        auth.get_user.return_value = NS(user=user)
        auth.get_session.side_effect = AssertionError('Implicit session forbidden.')
        auth.set_session.side_effect = AssertionError('Session restoration forbidden.')
        return NS(auth=auth), response, user, claims

    def adapter(self, client, **kwargs):
        return auth_module.SupabaseAdapters(
            self.url, 'sb_publishable_synthetic_fixture', sdk_factory=Mock(return_value=client),
            http_factory=self.http_factory, clock=lambda: self.now, **kwargs)

    def assert_rejected(self, adapter, reason):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level='DEBUG'):
            with self.assertRaises(auth_module.PasswordLoginError) as raised:
                adapter.password_login(self.email, self.password)
        error = raised.exception
        self.assertEqual(error.reason, reason)
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        rendered = str(error) + repr(error) + ''.join(traceback.format_exception(error))
        for secret in (self.password, 'returned-access-secret', 'returned-refresh-secret', 'private-provider-detail'):
            self.assertNotIn(secret, rendered)
        self.assertEqual(output.getvalue(), '')

    def test_success_exact_token_identity_expiry_and_frozen_redacted_result(self):
        fixtures = [self.fixture(), self.fixture()]
        fixtures[1][1].session.expires_at = self.now + 900
        sdk = Mock(side_effect=[fixture[0] for fixture in fixtures])
        adapter = auth_module.SupabaseAdapters(
            self.url, 'sb_publishable_synthetic_fixture', sdk_factory=sdk,
            http_factory=self.http_factory, clock=lambda: self.now)
        for index, (client, response, user, claims) in enumerate(fixtures):
            token = response.session.access_token
            # A changing SDK session must not change which token is verified/returned.
            def verify(access_token):
                response.session.access_token = 'different-implicit-token'
                return {'claims': claims}
            client.auth.get_claims.side_effect = verify
            with self.assertNoLogs(level='DEBUG'), redirect_stdout(io.StringIO()) as output:
                result = adapter.password_login(self.email, self.password)
            self.assertEqual(output.getvalue(), '')
            client.auth.sign_in_with_password.assert_called_once_with({'email': self.email, 'password': self.password})
            client.auth.get_claims.assert_called_once_with(token)
            client.auth.get_user.assert_called_once_with(token)
            client.auth.get_session.assert_not_called()
            client.auth.set_session.assert_not_called()
            self.assertIsInstance(result, auth_module.VerifiedLoginCredentials)
            self.assertEqual((result.user_id, result.user_email, result.session_id),
                             (user.id, user.email, claims['session_id']))
            self.assertTrue(result.access_token == token)
            self.assertTrue(result.refresh_token == response.session.refresh_token)
            self.assertEqual(result.access_expires_at, min(response.session.expires_at, claims['exp']))
            self.assertEqual({field.name for field in fields(result)},
                             {'user_id', 'user_email', 'access_token', 'refresh_token', 'access_expires_at', 'session_id'})
            with self.assertRaises(FrozenInstanceError):
                result.user_id = 'changed'
            self.assertEqual(repr(result), '<VerifiedLoginCredentials redacted>')
            self.assertEqual(str(result), repr(result))
            options = sdk.call_args_list[index].kwargs['options']
            self.assertFalse(options.persist_session)
            self.assertFalse(options.auto_refresh_token)
            self.assertIs(options.httpx_client, self.owned[index][0])
            self.assertTrue(self.owned[index][0].is_closed)
        self.assertIsNot(fixtures[0][0], fixtures[1][0])
        self.assertIsNot(self.owned[0][0], self.owned[1][0])

    def test_response_and_identity_failures(self):
        cases = [('response', 'session', None), ('response', 'user', None),
                 ('session', 'user', None), ('session', 'access_token', ' '),
                 ('session', 'refresh_token', ''), ('session', 'access_token', 123),
                 ('session', 'refresh_token', None), ('response_user', 'id', 'other'),
                 ('session_user', 'id', 'other'), ('user', 'id', 'other'),
                 ('user', 'id', ''), ('user', 'email', ' '), ('user', 'email', None),
                 ('user', 'email_confirmed_at', None)]
        for target, field, value in cases:
            with self.subTest(target=target, field=field, value=value):
                client, response, user, _ = self.fixture()
                objects = dict(response=response, session=response.session, user=user,
                               response_user=response.user, session_user=response.session.user)
                setattr(objects[target], field, value)
                self.assert_rejected(self.adapter(client),
                                     'unconfirmed_email' if field == 'email_confirmed_at' else 'invalid_result')
        for response_value in (None, NS()):
            client, _, _, _ = self.fixture()
            client.auth.sign_in_with_password.return_value = response_value
            self.assert_rejected(self.adapter(client), 'invalid_result')
        client, _, _, _ = self.fixture()
        client.auth.get_user.return_value = NS(user=None)
        self.assert_rejected(self.adapter(client), 'invalid_result')

    def test_claims_and_password_amr_policy(self):
        missing = object()
        password = {'method': 'password', 'timestamp': self.now}
        cases = [('sub', 'other'), ('sub', ' '), ('iss', 'wrong'), ('aud', 'anon'),
                 ('role', 'service_role'), ('session_id', missing), ('session_id', ''),
                 ('session_id', 1)]
        cases += [('amr', value) for value in (
            missing, None, [], 'password', {}, ['password'], [{}], [{'method': ''}],
            [{'method': 'password'}], [{'method': 'password', 'timestamp': True}],
            [{'method': 'password', 'timestamp': 'invalid'}],
            *[[{'method': method, 'timestamp': self.now}] for method in ('recovery', 'unknown', 'mfa/totp')],
            *[[password, {'method': method, 'timestamp': self.now}] for method in ('recovery', 'unknown', 'mfa/totp')],
        )]
        for index, (field, value) in enumerate(cases):
            with self.subTest(case=index, field=field):
                client, _, _, claims = self.fixture()
                if value is missing:
                    claims.pop(field)
                else:
                    claims[field] = value
                self.assert_rejected(self.adapter(client), 'invalid_result')
        for value in (None, {}, {'claims': None}, {'claims': {}}, {'claims': []}, {'claims': 'invalid'}):
            client, _, _, _ = self.fixture()
            client.auth.get_claims.return_value = value
            self.assert_rejected(self.adapter(client), 'invalid_result')

    def test_expiry_policy_and_recheck_after_cleanup(self):
        for source in ('response', 'claims'):
            for value in (None, 'invalid', True, float('nan'), float('inf'), self.now, self.now - 1):
                with self.subTest(source=source, value=value):
                    client, response, _, claims = self.fixture()
                    if source == 'response':
                        response.session.expires_at = value
                    else:
                        claims['exp'] = value
                    self.assert_rejected(self.adapter(client), 'invalid_result')
        client, _, _, _ = self.fixture()
        now = [self.now]
        def factory(**kwargs):
            http = self.http_factory(**kwargs)
            transport = self.owned[-1][1]
            close = transport.close
            def advance_and_close():
                close()
                now[0] += 3600
            transport.close = advance_and_close
            return http
        adapter = auth_module.SupabaseAdapters(
            self.url, 'sb_publishable_synthetic_fixture', sdk_factory=Mock(return_value=client),
            http_factory=factory, clock=lambda: now[0])
        self.assert_rejected(adapter, 'invalid_result')

    def test_error_classification_and_sanitization(self):
        sensitive = ' '.join((self.password, 'returned-access-secret', 'returned-refresh-secret', 'private-provider-detail'))
        cases = [
            ('sign_in_with_password', AuthApiError(sensitive, 400, 'invalid_credentials'), 'invalid_credentials'),
            ('sign_in_with_password', AuthApiError(sensitive, 403, 'email_not_confirmed'), 'unconfirmed_email'),
            ('sign_in_with_password', AuthApiError(sensitive, 429, 'over_request_rate_limit'), 'throttled'),
            ('sign_in_with_password', AuthApiError(sensitive, 503, 'unexpected_failure'), 'service_failure'),
            ('sign_in_with_password', TimeoutError(sensitive), 'service_failure'),
            ('get_claims', AuthInvalidJwtError(sensitive), 'invalid_result'),
            ('get_claims', AuthApiError(sensitive, 401, 'bad_jwt'), 'invalid_result'),
            ('get_user', AuthApiError(sensitive, 401, 'bad_jwt'), 'invalid_result'),
            ('get_user', AuthApiError(sensitive, 429, 'over_request_rate_limit'), 'throttled'),
            ('get_user', TimeoutError(sensitive), 'service_failure'),
        ]
        for stage, error, reason in cases:
            with self.subTest(stage=stage, reason=reason):
                client, _, _, _ = self.fixture()
                getattr(client.auth, stage).side_effect = error
                self.assert_rejected(self.adapter(client), reason)

    def test_construction_and_cleanup_failures_are_sanitized(self):
        for stage in ('construction', 'cleanup'):
            with self.subTest(stage=stage):
                client, _, _, _ = self.fixture()
                failure = RuntimeError('private-provider-detail')
                sdk = Mock(side_effect=failure) if stage == 'construction' else Mock(return_value=client)
                def factory(**kwargs):
                    http = self.http_factory(**kwargs)
                    if stage == 'cleanup':
                        transport = self.owned[-1][1]
                        close = transport.close
                        def fail_close():
                            close()
                            raise failure
                        transport.close = fail_close
                    return http
                adapter = auth_module.SupabaseAdapters(
                    self.url, 'sb_publishable_synthetic_fixture', sdk_factory=sdk,
                    http_factory=factory, clock=lambda: self.now)
                self.assert_rejected(adapter, 'service_failure')

    def test_control_flow_signals_propagate_and_close_resources(self):
        for signal_type in (KeyboardInterrupt, SystemExit, GeneratorExit, CancelledError):
            client, _, _, _ = self.fixture()
            signal = signal_type('synthetic interruption')
            client.auth.get_claims.side_effect = signal
            with self.assertRaises(signal_type) as raised:
                self.adapter(client).password_login(self.email, self.password)
            self.assertIs(raised.exception, signal)


if __name__ == '__main__':
    unittest.main()
