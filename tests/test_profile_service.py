"""Offline own-profile contract, including requests through the installed SDK."""
from asyncio import CancelledError
import ast
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta
import inspect
import io
import json
from pathlib import Path
import socket
import traceback
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

import httpx
from postgrest.exceptions import APIError
from postgrest.types import ReturnMethod

from normal_auth_coordinator import AuthenticatedContext, SupabaseAdapters
import profile_service
from profile_service import (
    UserProfile, get_own_profile, ProfileServiceError,
    ProfileUnavailableError, ProfileConsistencyError,
    update_own_profile, ProfileValidationError, ProfileNotFoundError,
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


class ProfileUpdateTests(unittest.TestCase):
    user_id = ProfileServiceTests.user_id
    secret = ProfileServiceTests.secret
    row = ProfileServiceTests.row
    assert_safe_error = ProfileServiceTests.assert_safe_error

    def setUp(self):
        ProfileServiceTests.setUp(self)
        self.query = Mock(spec=['update', 'eq', 'select', 'retry', 'execute'])
        self.client.table.return_value = self.query
        for method in ('update', 'eq', 'select', 'retry'):
            getattr(self.query, method).return_value = self.query
        self.query.execute.return_value = SimpleNamespace(data=[self.row()])

    def update(self, **changes):
        return update_own_profile(self.context, **(dict(first_name='Ana', last_name='Cruz') | changes))

    def test_exact_query_and_existing_client_only(self):
        with patch('supabase.create_client', side_effect=AssertionError('No new client')), \
             patch('normal_auth_coordinator.create_client', side_effect=AssertionError('No new client')):
            profile = self.update()
        self.assertIsInstance(profile, UserProfile)
        self.assertEqual(repr(profile), '<UserProfile redacted>')
        self.assertEqual(self.client.method_calls, [call.table('profiles')])
        self.assertEqual(self.query.mock_calls, [
            call.update(dict(first_name='Ana', last_name='Cruz'), returning=ReturnMethod.representation),
            call.eq('id', self.user_id), call.select('id,first_name,last_name,created_at'),
            call.retry(False), call.execute()])

    def test_api_excludes_owner_and_arbitrary_columns(self):
        parameters = inspect.signature(update_own_profile).parameters
        self.assertEqual(list(parameters), ['context', 'first_name', 'last_name'])
        for field in ('first_name', 'last_name'):
            self.assertEqual(parameters[field].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameters[field].default, inspect.Parameter.empty)
        for key in ('user_id', 'profile_id', 'id', 'created_at', 'email', 'role', 'updates'):
            with self.assertRaises(TypeError):
                self.update(**{key: 'untrusted'})
        with self.assertRaises(TypeError):
            update_own_profile(self.context, 'Ana', 'Cruz')
        self.client.table.assert_not_called()

    def test_normalization_and_unicode_code_point_boundary(self):
        cases = [None, '', ' \t\n ', ' \tAna\n', "O'Neill", 'Anne-Marie',
                 '小明', 'José', 'Ana  Maria', 'a\u200db', 'é' * 100, '𐐀' * 100,
                 ' ' + 'x' * 100 + ' ', 'e\u0301' * 50]
        for first in cases:
            for last in (None, ' Cruz '):
                with self.subTest(first=first, last=last):
                    expected = (first.strip() or None) if first is not None else None
                    expected_last = last.strip() if last is not None else None
                    self.query.execute.return_value.data = [self.row(first_name=expected, last_name=expected_last)]
                    profile = self.update(first_name=first, last_name=last)
                    self.assertEqual((profile.first_name, profile.last_name), (expected, expected_last))
                    self.assertEqual(self.query.update.call_args.args[0],
                                     dict(first_name=expected, last_name=expected_last))

    def test_invalid_input_rejected_before_query(self):
        invalid = [True, 1, 1.5, b'name', [], {}, object(), 'x' * 101,
                   '𐐀' * 101, 'e\u0301' * 51, 'A\x00B', 'A\tB', 'A\nB',
                   'A\rB', 'A\x7fB', 'A\x85B', 'A\ud800B']
        for field in ('first_name', 'last_name'):
            for value in invalid:
                with self.subTest(field=field, value_type=type(value).__name__):
                    with self.assertRaises(ProfileValidationError) as raised:
                        self.update(**{field: value})
                    self.assert_safe_error(raised.exception)
                    self.assertEqual(str(raised.exception), 'Profile names are invalid.')
        self.client.table.assert_not_called()

    def test_context_misuse_rejected_before_query(self):
        for context in (None, {}, SimpleNamespace(user_id=self.user_id, client=self.client),
                        replace(self.context, user_id=' '), replace(self.context, client=None)):
            with self.assertRaises(TypeError):
                update_own_profile(context, first_name=None, last_name=None)
        self.client.table.assert_not_called()

    def test_each_verified_identity_controls_target(self):
        for user_id in (self.user_id, '00000000-0000-0000-0000-000000000002'):
            self.query.execute.return_value.data = [self.row(id=user_id)]
            result = update_own_profile(replace(self.context, user_id=user_id), first_name='Ana', last_name='Cruz')
            self.assertEqual(result.id, user_id)
            self.query.eq.assert_called_with('id', user_id)
        self.assertEqual(self.query.execute.call_count, 2)

    def test_zero_rows_is_not_found_without_fallback(self):
        self.query.execute.return_value.data = []
        with self.assertRaises(ProfileNotFoundError) as raised:
            self.update()
        self.assert_safe_error(raised.exception)
        self.assertEqual(str(raised.exception), 'Profile is unavailable for update.')
        self.query.execute.assert_called_once_with()
        self.client.table.assert_called_once_with('profiles')

    def test_malformed_duplicate_mismatched_and_incomplete_responses(self):
        rows = [None, {}, self.secret, (), [None], [[]], [self.row(), self.row()],
                [self.row(id='other-user')], [self.row(id=None)],
                [self.row(first_name=[])], [self.row(last_name=True)],
                [self.row(created_at='2026-10-10T01:02:03')],
                [self.row(created_at=self.secret)], [self.row(created_at=None)]]
        rows += [[{k: v for k, v in self.row().items() if k != missing}] for missing in self.row()]
        responses = [SimpleNamespace(data=data) for data in rows] + [None, object(), SimpleNamespace()]
        for response in responses:
            self.query.execute.return_value = response
            with self.assertRaises(ProfileConsistencyError) as raised:
                self.update()
            self.assert_safe_error(raised.exception)

    def test_returned_names_must_confirm_submitted_values(self):
        for changes in (dict(first_name='Other'), dict(last_name='Other'),
                        dict(first_name=None), dict(last_name=None)):
            self.query.execute.return_value.data = [self.row(**changes)]
            with self.assertRaises(ProfileConsistencyError):
                self.update()
        self.query.execute.return_value.data = [self.row(email=self.secret, access_token=self.secret)]
        profile = self.update()
        self.assertEqual((profile.first_name, profile.last_name), ('Ana', 'Cruz'))
        self.assertFalse(hasattr(profile, 'access_token'))
        self.assertFalse(hasattr(profile, 'email'))

    def test_provider_errors_are_sanitized_without_logs_or_retry(self):
        for error in (APIError(dict(code='42501', message=self.secret, details=self.secret, hint=self.secret)),
                      httpx.ReadTimeout(self.secret), httpx.ConnectError(self.secret),
                      httpx.HTTPStatusError(self.secret, request=httpx.Request('PATCH', 'https://fixture.invalid'),
                                            response=httpx.Response(503))):
            self.query.execute.reset_mock()
            self.query.execute.side_effect = error
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level='DEBUG'):
                with self.assertRaises(ProfileUnavailableError) as raised:
                    self.update()
            self.assert_safe_error(raised.exception)
            self.assertEqual(output.getvalue(), '')
            self.query.execute.assert_called_once_with()
        self.client.close.assert_not_called()

    def test_programming_and_builder_errors_propagate(self):
        for error in (TypeError('bug'), AttributeError('bug'), RuntimeError('bug'),
                      KeyboardInterrupt(), SystemExit(), GeneratorExit(), CancelledError()):
            self.query.execute.side_effect = error
            with self.assertRaises(type(error)) as raised:
                self.update()
            self.assertIs(raised.exception, error)
        self.query.execute.reset_mock()
        error = APIError(dict(code='synthetic', message=self.secret, details='', hint=''))
        self.query.update.side_effect = error
        with self.assertRaises(APIError) as raised:
            self.update()
        self.assertIs(raised.exception, error)
        self.query.execute.assert_not_called()

    def test_real_sdk_patch_contract_and_lifetime(self):
        requests, owned = [], []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=[self.row(first_name="Ana-María", last_name=None)])
        def factory(**kwargs):
            http = httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
            owned.append(http)
            return http
        key = 'sb_publishable_profile_fixture'
        adapter = SupabaseAdapters('https://fixture.invalid', key, http_factory=factory)
        with adapter.database_client('verified-user-token') as client:
            profile = update_own_profile(replace(self.context, client=client),
                                         first_name=' Ana-María ', last_name=' ')
            self.assertEqual(profile.first_name, 'Ana-María')
            self.assertFalse(owned[0].is_closed)
        self.assertTrue(owned[0].is_closed)
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.method, 'PATCH')
        self.assertEqual(request.url.path, '/rest/v1/profiles')
        self.assertEqual(dict(request.url.params), dict(id='eq.' + self.user_id,
                                                       select='id,first_name,last_name,created_at'))
        self.assertEqual(json.loads(request.content), dict(first_name='Ana-María', last_name=None))
        self.assertEqual(request.headers['Authorization'], 'Bearer verified-user-token')
        self.assertEqual(request.headers['apikey'], key)
        self.assertEqual(request.headers['Content-Profile'], 'public')
        self.assertIn('return=representation', request.headers['Prefer'].split(','))

    def test_real_sdk_failures_never_repeat_mutation(self):
        for failure in ('provider', 'network'):
            requests = []
            def handler(request):
                requests.append(request)
                if failure == 'network':
                    raise httpx.ReadTimeout(self.secret, request=request)
                return httpx.Response(503, headers={'server': 'cloudflare'},
                                      json=dict(code='503', message=self.secret, details=self.secret, hint=self.secret))
            http = httpx.Client(transport=httpx.MockTransport(handler))
            adapter = SupabaseAdapters('https://fixture.invalid', 'sb_publishable_profile_fixture',
                                       http_factory=lambda **kwargs: http)
            with adapter.database_client('verified-user-token') as client:
                with self.assertRaises(ProfileUnavailableError) as raised:
                    update_own_profile(replace(self.context, client=client), first_name='Ana', last_name='Cruz')
                self.assert_safe_error(raised.exception)
                self.assertFalse(http.is_closed)
            self.assertTrue(http.is_closed)
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].method, 'PATCH')


if __name__ == '__main__':
    unittest.main()
