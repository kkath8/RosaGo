"""Offline own-profile contract, including requests through the installed SDK."""
from asyncio import CancelledError
import ast
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta
import inspect
import io
from pathlib import Path
import socket
import traceback
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

import httpx
from postgrest.exceptions import APIError

from normal_auth_coordinator import AuthenticatedContext, SupabaseAdapters
import profile_service
from profile_service import (
    UserProfile, get_own_profile, ProfileServiceError,
    ProfileUnavailableError, ProfileConsistencyError,
)


class ProfileServiceTests(unittest.TestCase):
    user_id = '00000000-0000-0000-0000-000000000001'
    secret = 'fake-bearer-secret private-provider-message SQL-details private-hint'

    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname',
                      'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Live network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        self.client = Mock(spec=['table', 'close'])
        self.query = Mock(spec=['select', 'eq', 'limit', 'retry', 'execute'])
        self.client.table.return_value = self.query
        for method in ('select', 'eq', 'limit', 'retry'):
            getattr(self.query, method).return_value = self.query
        self.context = AuthenticatedContext('opaque-handle', self.user_id,
                                            'verified@example.invalid', self.client)
        self.query.execute.return_value = SimpleNamespace(data=[self.row()])

    def row(self, **changes):
        return dict(id=self.user_id, first_name=' Ana ', last_name=' Cruz ',
                    created_at='2026-10-10T01:02:03Z') | changes

    def assert_safe_error(self, error):
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        rendered = str(error) + repr(error) + ''.join(traceback.format_exception(error))
        for value in self.secret.split():
            self.assertNotIn(value, rendered)

    def assert_inconsistent(self, data):
        self.query.execute.return_value = SimpleNamespace(data=data)
        with self.assertRaises(ProfileConsistencyError) as raised:
            get_own_profile(self.context)
        self.assert_safe_error(raised.exception)
        self.assertEqual(str(raised.exception), 'Profile data is inconsistent.')

    def test_success_is_frozen_minimal_and_redacted(self):
        profile = get_own_profile(self.context)
        self.assertIsInstance(profile, UserProfile)
        self.assertEqual(profile.id, self.user_id)
        self.assertEqual((profile.first_name, profile.last_name), ('Ana', 'Cruz'))
        self.assertEqual(profile.created_at, datetime.fromisoformat('2026-10-10T01:02:03+00:00'))
        self.assertEqual({field.name for field in fields(profile)},
                         {'id', 'first_name', 'last_name', 'created_at'})
        self.assertFalse(hasattr(profile, '__dict__'))
        with self.assertRaises(FrozenInstanceError):
            profile.first_name = 'changed'
        self.assertEqual(repr(profile), '<UserProfile redacted>')

    def test_exact_query_identity_and_single_execution_without_writes_or_close(self):
        with patch('supabase.create_client', side_effect=AssertionError('No new client')), \
             patch('normal_auth_coordinator.create_client', side_effect=AssertionError('No new client')):
            get_own_profile(self.context)
        self.assertEqual(self.client.method_calls, [call.table('profiles')])
        self.assertEqual(self.query.mock_calls, [
            call.select('id,first_name,last_name,created_at'), call.eq('id', self.user_id),
            call.limit(2), call.retry(False), call.execute()])

    def test_api_accepts_only_context_and_imports_no_application_or_client_factory(self):
        self.assertEqual(list(inspect.signature(get_own_profile).parameters), ['context'])
        with self.assertRaises(TypeError):
            get_own_profile(self.context, user_id='another-user')
        tree = ast.parse(Path(profile_service.__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(any(alias.name.split('.')[0] in ('app', 'flask', 'supabase')
                                     for alias in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or '').split('.')[0], ('app', 'flask', 'supabase'))
                self.assertFalse(any(alias.name in ('create_client', 'supabase') for alias in node.names))

    def test_nullable_and_whitespace_names(self):
        cases = [('Ana', 'Cruz', 'Ana', 'Cruz'), ('Ana', None, 'Ana', None),
                 (None, 'Cruz', None, 'Cruz'), (None, None, None, None),
                 (' \tAna\n', ' Cruz ', 'Ana', 'Cruz'), (' \t', '', None, None)]
        for first, last, expected_first, expected_last in cases:
            with self.subTest(first=first, last=last):
                self.query.execute.return_value.data = [self.row(first_name=first, last_name=last)]
                profile = get_own_profile(self.context)
                self.assertEqual((profile.first_name, profile.last_name), (expected_first, expected_last))

    def test_invalid_name_types_are_rejected_without_coercion(self):
        for field in ('first_name', 'last_name'):
            for value in (1, True, [], {}, 1.5, b'name', object()):
                with self.subTest(field=field, value_type=type(value).__name__):
                    self.assert_inconsistent([self.row(**{field: value})])

    def test_timestamp_offsets_are_preserved(self):
        for timestamp, offset in (('2026-10-10T01:02:03Z', 0),
                                  ('2026-10-10T09:02:03+08:00', 8),
                                  ('2026-10-09T20:02:03-05:00', -5)):
            self.query.execute.return_value.data = [self.row(created_at=timestamp)]
            self.assertEqual(get_own_profile(self.context).created_at.utcoffset(), timedelta(hours=offset))

    def test_invalid_and_naive_timestamps_are_rejected(self):
        for value in (None, 123, True, [], {}, datetime.now(), '', self.secret,
                      '2026-10-10', '2026-10-10T01:02:03', '2026-99-99T01:02:03Z'):
            with self.subTest(value_type=type(value).__name__):
                self.assert_inconsistent([self.row(created_at=value)])

    def test_missing_profile_returns_none_without_fallback(self):
        self.query.execute.return_value.data = []
        self.assertIsNone(get_own_profile(self.context))
        self.query.execute.assert_called_once_with()
        self.client.table.assert_called_once_with('profiles')
        self.client.close.assert_not_called()

    def test_multiple_rows_rejected_even_if_identical(self):
        self.assert_inconsistent([self.row(), self.row()])
        self.query.execute.assert_called_once_with()

    def test_response_and_row_shapes(self):
        for data in (None, {}, self.secret, (), [None], [123], [self.secret], [[]]):
            with self.subTest(shape=type(data).__name__):
                self.assert_inconsistent(data)
        for response in (None, object(), SimpleNamespace()):
            self.query.execute.return_value = response
            with self.assertRaises(ProfileConsistencyError):
                get_own_profile(self.context)

    def test_required_fields_and_invalid_ids(self):
        for key in self.row():
            row = self.row()
            del row[key]
            self.assert_inconsistent([row])
        for value in (None, 123, True, [], {}, '', ' ', self.secret, 'another-user'):
            self.assert_inconsistent([self.row(id=value)])

    def test_response_cannot_redirect_query_or_add_result_fields(self):
        self.assert_inconsistent([self.row(id='other-user')])
        self.query.eq.assert_called_once_with('id', self.user_id)
        self.query.execute.assert_called_once_with()
        self.query.execute.return_value.data = [MappingProxyType(self.row(
            email=self.secret, access_token=self.secret, metadata={'id': 'other-user'}))]
        profile = get_own_profile(self.context)
        self.assertEqual(profile.id, self.user_id)
        self.assertFalse(hasattr(profile, 'email'))

    def test_lookup_follows_each_verified_context_identity(self):
        other_id = '00000000-0000-0000-0000-000000000002'
        for user_id in (self.user_id, other_id):
            context = replace(self.context, user_id=user_id)
            self.query.execute.return_value.data = [self.row(id=user_id)]
            self.assertEqual(get_own_profile(context).id, user_id)
        self.assertEqual(self.query.eq.call_args_list,
                         [call('id', self.user_id), call('id', other_id)])
        self.assertEqual(self.query.execute.call_count, 2)

    def test_provider_failures_have_fixed_messages_and_no_exception_chain_or_logs(self):
        request = httpx.Request('GET', 'https://fixture.invalid/profiles',
                                headers={'Authorization': 'Bearer ' + self.secret})
        errors = [APIError(dict(code='42501', message=self.secret, details=self.secret, hint=self.secret)),
                  httpx.ReadTimeout(self.secret, request=request),
                  httpx.ConnectError(self.secret, request=request),
                  httpx.HTTPStatusError(self.secret, request=request,
                                        response=httpx.Response(503, request=request))]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.query.execute.side_effect = error
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level='DEBUG'):
                    with self.assertRaises(ProfileUnavailableError) as raised:
                        get_own_profile(self.context)
                self.assertEqual(output.getvalue(), '')
                self.assertIsInstance(raised.exception, ProfileServiceError)
                self.assertEqual(str(raised.exception), 'Profile is temporarily unavailable.')
                self.assert_safe_error(raised.exception)
        self.client.close.assert_not_called()

    def test_programming_errors_and_control_flow_propagate(self):
        for error in (TypeError('misuse'), AttributeError('misuse'), RuntimeError('bug'),
                      KeyboardInterrupt(), SystemExit(), GeneratorExit(), CancelledError()):
            self.query.execute.side_effect = error
            with self.assertRaises(type(error)) as raised:
                get_own_profile(self.context)
            self.assertIs(raised.exception, error)
        self.query.execute.side_effect = None
        builder_error = APIError(dict(code='synthetic', message=self.secret, details='', hint=''))
        self.query.select.side_effect = builder_error
        with self.assertRaises(APIError) as raised:
            get_own_profile(self.context)
        self.assertIs(raised.exception, builder_error)
        self.client.close.assert_not_called()

    def test_context_misuse_fails_before_query(self):
        for context in (None, {}, SimpleNamespace(user_id=self.user_id, client=self.client),
                        replace(self.context, user_id=' '), replace(self.context, user_id=123),
                        replace(self.context, client=None)):
            with self.assertRaises(TypeError):
                get_own_profile(context)
        self.client.table.assert_not_called()

    def test_real_sdk_request_headers_query_and_caller_owned_lifetime(self):
        requests, owned = [], []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=[self.row()])
        def factory(**kwargs):
            http = httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
            owned.append(http)
            return http
        public_key = 'sb_publishable_profile_fixture'
        adapter = SupabaseAdapters('https://fixture.invalid', public_key, http_factory=factory)
        with adapter.database_client('verified-user-token') as client:
            profile = get_own_profile(replace(self.context, client=client))
            self.assertEqual(profile.id, self.user_id)
            self.assertFalse(owned[0].is_closed)
        self.assertTrue(owned[0].is_closed)
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.method, 'GET')
        self.assertEqual(request.url.path, '/rest/v1/profiles')
        self.assertEqual(dict(request.url.params), dict(
            select='id,first_name,last_name,created_at', id='eq.' + self.user_id, limit='2'))
        self.assertEqual(request.headers['Authorization'], 'Bearer verified-user-token')
        self.assertEqual(request.headers['apikey'], public_key)
        self.assertEqual(request.headers['Accept-Profile'], 'public')
        self.assertEqual(request.content, b'')

    def test_real_sdk_provider_failure_executes_once_without_retry(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(503, headers={'server': 'cloudflare'},
                                  json=dict(code='503', message=self.secret, details=self.secret, hint=self.secret))
        http = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http.close)
        adapter = SupabaseAdapters('https://fixture.invalid', 'sb_publishable_profile_fixture',
                                   http_factory=lambda **kwargs: http)
        with adapter.database_client('verified-user-token') as client:
            with self.assertRaises(ProfileUnavailableError) as raised:
                get_own_profile(replace(self.context, client=client))
            self.assert_safe_error(raised.exception)
            self.assertFalse(http.is_closed)
        self.assertTrue(http.is_closed)
        self.assertEqual(len(requests), 1)


if __name__ == '__main__':
    unittest.main()
