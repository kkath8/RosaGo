"""Public adapter tests: synthetic keys and in-memory transport only."""
import base64
import json
import socket
import traceback
import unittest
from unittest.mock import Mock, patch

import httpx
from supabase_auth import SyncGoTrueClient

from places_client import PublicPlacesClient


class PlacesClientTests(unittest.TestCase):
    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname',
                      'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        self.requests, self.owned, self.settings = [], [], []

    @staticmethod
    def legacy_key(role):
        def encode(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
        return encode({'alg': 'HS256'}) + '.' + encode({'role': role}) + '.c3ludGhldGlj'

    def http_factory(self, **kwargs):
        self.settings.append(kwargs)
        def handler(request):
            self.requests.append(request)
            return httpx.Response(200, json=[])
        http = httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
        self.owned.append(http)
        return http

    def test_supported_keys_real_sdk_no_auth_and_scoped_cleanup(self):
        for key in ('sb_publishable_fixture', self.legacy_key('anon')):
            with self.subTest(key_kind=key.split('_')[0]):
                adapter = PublicPlacesClient('https://fixture.invalid/', key,
                                             http_factory=self.http_factory)
                self.assertNotIn(key, repr(adapter))
                with (
                    patch.object(SyncGoTrueClient, 'get_session', side_effect=AssertionError('Auth forbidden')),
                    patch.object(SyncGoTrueClient, 'refresh_session', side_effect=AssertionError('Auth forbidden')),
                    patch.object(SyncGoTrueClient, 'get_user', side_effect=AssertionError('Auth forbidden')),
                    patch.object(SyncGoTrueClient, 'set_session', side_effect=AssertionError('Auth forbidden')),
                ):
                    with adapter.database_client() as client:
                        self.assertFalse(client.options.persist_session)
                        self.assertFalse(client.options.auto_refresh_token)
                        self.assertEqual(client.options.schema, 'public')
                        self.assertIsNone(client.auth._in_memory_session)
                        self.assertFalse(self.owned[-1].is_closed)
                        before = len(self.requests)
                        client.table('places').select('id').execute()
                        self.assertEqual(len(self.requests), before + 1)
                self.assertTrue(self.owned[-1].is_closed)
                request = self.requests[-1]
                self.assertEqual(request.method, 'GET')
                self.assertEqual(request.url.path, '/rest/v1/places')
                self.assertEqual(request.headers['apikey'], key)
                self.assertIn(request.headers.get('Authorization'), (None, 'Bearer ' + key))
                self.assertEqual(request.headers['Accept-Profile'], 'public')
                self.assertEqual(request.content, b'')
                self.assertEqual(self.settings[-1], dict(timeout=20, follow_redirects=False, trust_env=False))

    def test_invalid_configuration_is_redacted_before_resources(self):
        keys = (self.legacy_key('service_role'), self.legacy_key('authenticated'),
                'sb_secret_private-material', 'sb_publishable_', '', None, [],
                'malformed.private-material.key', 'sb_publishable_bad\nkey')
        for key in keys:
            sdk, http = Mock(), Mock()
            with self.subTest(kind=type(key).__name__):
                with self.assertRaises(ValueError) as raised:
                    PublicPlacesClient('https://fixture.invalid', key,
                                       sdk_factory=sdk, http_factory=http)
                self.assertEqual(str(raised.exception), 'Invalid places public configuration.')
                self.assertIsNone(raised.exception.__context__)
                self.assertIsNone(raised.exception.__cause__)
                self.assertNotIn('private-material', ''.join(traceback.format_exception(raised.exception)))
                sdk.assert_not_called()
                http.assert_not_called()
        for url in ('http://fixture.invalid', 'https://user:secret@fixture.invalid',
                    'https://fixture.invalid/path', 'https://fixture.invalid?q=secret', None, []):
            with self.assertRaises(ValueError):
                PublicPlacesClient(url, 'sb_publishable_fixture')

    def test_factory_options_no_token_parameter_and_distinct_clients(self):
        sdk = Mock(side_effect=[object(), object()])
        adapter = PublicPlacesClient('https://fixture.invalid', 'sb_publishable_fixture',
                                     sdk_factory=sdk, http_factory=self.http_factory)
        with adapter.database_client() as first, adapter.database_client() as second:
            self.assertIsNot(first, second)
            for invocation in sdk.call_args_list:
                options = invocation.kwargs['options']
                self.assertNotIn('Authorization', options.headers)
                self.assertFalse(options.persist_session)
                self.assertFalse(options.auto_refresh_token)
        self.assertTrue(all(http.is_closed for http in self.owned))
        self.assertEqual(self.requests, [])
        with self.assertRaises(TypeError):
            adapter.database_client('user-token')

    def test_cleanup_on_construction_and_body_failure(self):
        error = RuntimeError('programming failure')
        adapter = PublicPlacesClient('https://fixture.invalid', 'sb_publishable_fixture',
                                     sdk_factory=Mock(side_effect=error), http_factory=self.http_factory)
        with self.assertRaises(RuntimeError) as raised:
            with adapter.database_client():
                self.fail('Unexpected client')
        self.assertIs(raised.exception, error)
        self.assertTrue(self.owned[-1].is_closed)
        adapter = PublicPlacesClient('https://fixture.invalid', 'sb_publishable_fixture',
                                     http_factory=self.http_factory)
        with self.assertRaises(RuntimeError):
            with adapter.database_client():
                raise error
        self.assertTrue(self.owned[-1].is_closed)
        self.assertEqual(self.requests, [])

    def test_construction_failure_survives_secondary_close_failure(self):
        primary = TypeError('construction programming error')
        closes = []
        def factory(**kwargs):
            transport = httpx.MockTransport(lambda request: self.fail('Unexpected request'))
            http = httpx.Client(transport=transport, **kwargs)
            self.owned.append(http)
            original_close = transport.close
            def close():
                closes.append(True)
                original_close()
                raise httpx.CloseError('private-cleanup-credential')
            transport.close = close
            return http
        adapter = PublicPlacesClient('https://fixture.invalid', 'sb_publishable_fixture',
                                     sdk_factory=Mock(side_effect=primary), http_factory=factory)
        with self.assertRaises(TypeError) as raised:
            with adapter.database_client():
                self.fail('Unexpected client')
        self.assertIs(raised.exception, primary)
        self.assertIsNone(primary.__context__)
        self.assertIsNone(primary.__cause__)
        self.assertEqual(primary.__notes__, ['Places client cleanup also failed.'])
        self.assertNotIn('private-cleanup-credential', ''.join(traceback.format_exception(primary)))
        self.assertEqual(closes, [True])
        self.assertTrue(self.owned[0].is_closed)


if __name__ == '__main__':
    unittest.main()
