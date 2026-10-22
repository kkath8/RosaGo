"""Offline catalog contract tests; no Flask, database fixtures, or live requests."""
from asyncio import CancelledError
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, fields
from datetime import datetime
import io
import socket
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

import httpx
from postgrest.exceptions import APIError

from places_client import PublicPlacesClient
from places_service import (
    Place, PlacesService, PlacesValidationError, PlacesConsistencyError,
    PlacesUnavailableError, PROJECTION, CATEGORIES, parse_place_row,
)


class PlacesServiceTests(unittest.TestCase):
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
        self.query = Mock(spec=['select', 'eq', 'order', 'range', 'limit', 'retry', 'execute'])
        for method in ('select', 'eq', 'order', 'range', 'limit', 'retry'):
            getattr(self.query, method).return_value = self.query
        self.client = Mock(spec=['table'])
        self.client.table.return_value = self.query
        self.query.execute.return_value = SimpleNamespace(data=[self.row()])
        self.opened = self.closed = 0
        @contextmanager
        def factory():
            self.opened += 1
            try:
                yield self.client
            finally:
                self.closed += 1
        self.service = PlacesService(factory)

    def tearDown(self):
        self.assertEqual(self.opened, self.closed)

    @staticmethod
    def row(**changes):
        return dict(id='00000000-0000-0000-0000-000000000001', name='Synthetic fixture',
                    slug='synthetic-fixture', description='Untrusted <script>text</script>',
                    category='nature', address='Synthetic address', latitude=14.0,
                    longitude=121.0, image_url=None, created_at='2026-10-10T01:02:03Z',
                    updated_at='2026-10-10T09:02:03+08:00') | changes

    def inconsistent(self, data):
        self.query.execute.return_value = SimpleNamespace(data=data)
        with self.assertRaises(PlacesConsistencyError) as raised:
            self.service.list_published()
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)
        self.assertEqual(str(raised.exception), 'Places data is inconsistent.')

    def test_model_exact_frozen_slotted_redacted_and_no_extra_fields(self):
        self.query.execute.return_value.data = [self.row(status='published', token='private')]
        result = self.service.list_published()
        self.assertIsInstance(result, tuple)
        place = result[0]
        self.assertIsInstance(place, Place)
        self.assertEqual([field.name for field in fields(place)], PROJECTION.split(','))
        self.assertFalse(hasattr(place, '__dict__'))
        self.assertFalse(hasattr(place, 'status'))
        self.assertFalse(hasattr(place, 'token'))
        self.assertEqual(repr(place), '<Place redacted>')
        self.assertEqual(place.description, self.row()['description'])
        self.assertIsInstance(place.latitude, float)
        self.assertIsInstance(place.created_at, datetime)
        self.assertIsNotNone(place.updated_at.utcoffset())
        with self.assertRaises(FrozenInstanceError):
            place.name = 'changed'

    def test_public_parser_is_pure_and_uses_existing_validation(self):
        place = parse_place_row(self.row(status='private-extra'))
        self.assertIsInstance(place, Place)
        self.assertFalse(hasattr(place, 'status'))
        self.assertEqual(self.opened, 0)
        self.client.table.assert_not_called()
        for row in (None, {}, self.row(latitude=True), self.row(slug='Bad Slug'),
                    self.row(created_at='private-invalid-timestamp')):
            with self.subTest(row=row), self.assertRaises(PlacesConsistencyError) as raised:
                parse_place_row(row)
            self.assertIsNone(raised.exception.__context__)

    def test_exact_list_query_and_pagination(self):
        expected = 'id,name,slug,description,category,address,latitude,longitude,image_url,created_at,updated_at'
        self.assertEqual(PROJECTION, expected)
        self.service.list_published(category='nature', limit=10, offset=20)
        self.assertEqual(self.client.mock_calls[0], call.table('places'))
        self.assertEqual(self.query.mock_calls, [call.select(expected), call.eq('status', 'published'),
            call.eq('category', 'nature'), call.order('slug', desc=False), call.range(20, 29),
            call.retry(False), call.execute()])
        self.assertEqual((self.opened, self.closed), (1, 1))
        self.query.reset_mock()
        self.service.list_published()
        self.assertEqual(self.query.eq.call_args_list, [call('status', 'published')])
        self.query.range.assert_called_once_with(0, 49)
        for limit in (1, 100):
            self.query.reset_mock()
            self.service.list_published(limit=limit)
            self.query.range.assert_called_once_with(0, limit - 1)

    def test_invalid_callers_fail_before_client_open(self):
        cases = [dict(category=x) for x in ('', 'Nature', ' nature ', 'x', [], True, 'nature,or(status.eq.draft)')]
        cases += [dict(limit=x) for x in (0, -1, 101, True, 1.0, '1', None)]
        cases += [dict(offset=x) for x in (-1, True, 0.0, '0', None)]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(PlacesValidationError):
                self.service.list_published(**kwargs)
        for slug in (None, 1, True, [], '', ' ', 'a' * 121, 'é', 'K', 'a--b', '-a',
                     'a-', 'a b', 'a/b', 'a%20b', 'a,or(status.eq.draft)'):
            with self.subTest(slug=slug), self.assertRaises(PlacesValidationError):
                self.service.get_published_by_slug(slug)
        self.assertEqual(self.opened, 0)
        self.client.table.assert_not_called()
        with self.assertRaises(TypeError):
            self.service.list_published(order='name')

    def test_categories_and_response_mismatch(self):
        self.assertEqual(CATEGORIES, {'attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage'})
        for category in CATEGORIES:
            self.query.execute.return_value.data = [self.row(category=category)]
            self.assertEqual(self.service.list_published(category=category)[0].category, category)
        self.query.execute.return_value.data = [self.row(category='dining')]
        with self.assertRaises(PlacesConsistencyError):
            self.service.list_published(category='nature')

    def test_detail_normalization_exact_query_and_cardinality(self):
        self.assertEqual(self.service.get_published_by_slug(' \tSYNTHETIC-Fixture\n').slug, 'synthetic-fixture')
        self.assertEqual(self.query.mock_calls, [call.select(PROJECTION), call.eq('status', 'published'),
            call.eq('slug', 'synthetic-fixture'), call.limit(2), call.retry(False), call.execute()])
        self.query.execute.return_value.data = []
        self.assertIsNone(self.service.get_published_by_slug('synthetic-fixture'))
        self.assertEqual(self.service.list_published(), ())
        for rows in ([self.row(), self.row()], [self.row(slug='different')]):
            self.query.execute.return_value.data = rows
            with self.assertRaises(PlacesConsistencyError):
                self.service.get_published_by_slug('synthetic-fixture')

    def test_uuid_and_text_boundaries(self):
        for field, maximum in (('name', 150), ('description', 3000), ('address', 500), ('slug', 120)):
            for valid in ('a', 'a' * maximum):
                self.query.execute.return_value.data = [self.row(**{field: valid})]
                self.service.list_published()
            for invalid in (None, True, 123, [], '', ' ', ' a', 'a\n', '\u00a0a', 'a' * (maximum + 1)):
                self.inconsistent([self.row(**{field: invalid})])
        for invalid in ('', 'not-a-uuid', None, 123, True, [], ' 00000000-0000-0000-0000-000000000001'):
            self.inconsistent([self.row(id=invalid)])
        for invalid in ('UPPER', 'a--b', '-a', 'a-', 'é', 'a_b'):
            self.inconsistent([self.row(slug=invalid)])
        for invalid in ('Nature', '', None, [], 'other'):
            self.inconsistent([self.row(category=invalid)])

    def test_coordinate_types_ranges_and_finiteness(self):
        for field, maximum in (('latitude', 90), ('longitude', 180)):
            for valid in (-maximum, 0, maximum, 0.5):
                self.query.execute.return_value.data = [self.row(**{field: valid})]
                self.assertEqual(getattr(self.service.list_published()[0], field), float(valid))
            for invalid in (None, True, False, '1', [], maximum + .1, -maximum - .1,
                            float('nan'), float('inf'), -float('inf'), 10 ** 1000):
                self.inconsistent([self.row(**{field: invalid})])

    def test_image_baseline(self):
        for valid in (None, 'https://x', 'https://' + 'a' * 2040):
            self.query.execute.return_value.data = [self.row(image_url=valid)]
            self.assertEqual(self.service.list_published()[0].image_url, valid)
        for invalid in ('', 'https://', 'http://x', 'HTTPS://x', ' https://x', 'https://x\n',
                        'https://' + 'a' * 2041, True, 123, []):
            self.inconsistent([self.row(image_url=invalid)])

    def test_timestamps(self):
        for field in ('created_at', 'updated_at'):
            for valid in ('2026-10-10T01:02:03Z', '2026-10-10T09:02:03+08:00'):
                self.query.execute.return_value.data = [self.row(**{field: valid})]
                self.assertIsNotNone(getattr(self.service.list_published()[0], field).utcoffset())
            for invalid in (None, True, 123, [], '', 'private-invalid-date', '2026-10-10',
                            '2026-10-10T01:02:03', '2026-99-99T00:00:00Z'):
                self.inconsistent([self.row(**{field: invalid})])

    def test_response_shape_missing_fields_duplicates_and_oversize(self):
        for invalid in (None, {}, (), 'private', [None], [123], [[]]):
            self.inconsistent(invalid)
        for response in (None, object(), SimpleNamespace()):
            self.query.execute.return_value = response
            with self.assertRaises(PlacesConsistencyError):
                self.service.list_published()
        for field in self.row():
            row = self.row()
            del row[field]
            self.inconsistent([row])
        self.inconsistent([self.row(), self.row(slug='another')])
        self.inconsistent([self.row(), self.row(id='00000000-0000-0000-0000-000000000002')])
        self.query.execute.return_value.data = [self.row(), self.row()]
        with self.assertRaises(PlacesConsistencyError):
            self.service.list_published(limit=1)

    def test_provider_errors_sanitized_and_programming_signals_propagate(self):
        secret = 'private-provider-secret'
        request = httpx.Request('GET', 'https://fixture.invalid/' + secret,
                                headers={'Authorization': secret})
        errors = [APIError(dict(code='42501', message=secret, details=secret, hint=secret)),
                  httpx.ReadTimeout(secret, request=request), httpx.ConnectError(secret, request=request)]
        for operation in (self.service.list_published, lambda: self.service.get_published_by_slug('synthetic-fixture')):
            for error in errors:
                self.query.execute.side_effect = error
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level='DEBUG'):
                    with self.assertRaises(PlacesUnavailableError) as raised:
                        operation()
                self.assertEqual(output.getvalue(), '')
                self.assertIsNone(raised.exception.__cause__)
                self.assertIsNone(raised.exception.__context__)
                self.assertNotIn(secret, ''.join(traceback.format_exception(raised.exception)))
                self.assertEqual(str(raised.exception), 'Places are temporarily unavailable.')
            for error in (TypeError('bug'), RuntimeError('bug'), KeyboardInterrupt(), SystemExit(), CancelledError()):
                self.query.execute.side_effect = error
                with self.assertRaises(type(error)) as raised:
                    operation()
                self.assertIs(raised.exception, error)

    def assert_sanitized(self, error):
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        rendered = str(error) + repr(error) + ''.join(traceback.format_exception(error))
        for secret in ('private-wire-body', 'sb_publishable_private_fixture', 'private-credential'):
            self.assertNotIn(secret, rendered)

    def test_real_sdk_malformed_wire_responses(self):
        cases = (
            (200, 'application/json', b'{private-wire-body', PlacesConsistencyError),
            (502, 'text/html', b'<html>private-wire-body private-credential</html>', PlacesUnavailableError),
            (400, 'application/json', b'["private-wire-body"]', PlacesUnavailableError),
            (200, 'application/json', b'{"unexpected":"private-wire-body"}', PlacesConsistencyError),
            (200, 'application/json', b'null', PlacesConsistencyError),
        )
        for status, content_type, body, expected in cases:
            for detail in (False, True):
                with self.subTest(status=status, body_kind=content_type, detail=detail):
                    requests, owned = [], []
                    def handler(request):
                        requests.append(request)
                        return httpx.Response(status, content=body, headers={'content-type': content_type})
                    def factory(**kwargs):
                        http = httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
                        owned.append(http)
                        return http
                    adapter = PublicPlacesClient('https://fixture.invalid', 'sb_publishable_private_fixture',
                                                 http_factory=factory)
                    service = PlacesService(adapter.database_client)
                    output = io.StringIO()
                    with redirect_stdout(output), redirect_stderr(output), self.assertLogs('httpx', level='INFO') as logs:
                        with self.assertRaises(expected) as raised:
                            if detail:
                                service.get_published_by_slug('synthetic-fixture')
                            else:
                                service.list_published()
                    self.assert_sanitized(raised.exception)
                    for secret in ('private-wire-body', 'private-credential', 'sb_publishable_private_fixture'):
                        self.assertNotIn(secret, '\n'.join(logs.output))
                    self.assertEqual(output.getvalue(), '')
                    self.assertEqual(len(requests), 1)
                    self.assertEqual(requests[0].method, 'GET')
                    self.assertEqual(requests[0].url.path, '/rest/v1/places')
                    self.assertTrue(owned[0].is_closed)

    def test_client_entry_failures(self):
        for stage in ('http', 'sdk'):
            for error in (httpx.ConnectError('private-credential'),
                          APIError(dict(code='503', message='private-wire-body', details='', hint='')),
                          TypeError('programming error'), CancelledError()):
                for detail in (False, True):
                    with self.subTest(stage=stage, error=type(error).__name__, detail=detail):
                        owned = []
                        def factory(**kwargs):
                            if stage == 'http':
                                raise error
                            http = httpx.Client(transport=httpx.MockTransport(
                                lambda request: self.fail('Unexpected request')), **kwargs)
                            owned.append(http)
                            return http
                        adapter = PublicPlacesClient('https://fixture.invalid', 'sb_publishable_private_fixture',
                            http_factory=factory, sdk_factory=Mock(side_effect=error))
                        service = PlacesService(adapter.database_client)
                        recognized = isinstance(error, (APIError, httpx.HTTPError))
                        with self.assertRaises(PlacesUnavailableError if recognized else type(error)) as raised:
                            if detail:
                                service.get_published_by_slug('synthetic-fixture')
                            else:
                                service.list_published()
                        if recognized:
                            self.assert_sanitized(raised.exception)
                        else:
                            self.assertIs(raised.exception, error)
                        self.assertTrue(all(http.is_closed for http in owned))

    def test_cleanup_failure_alone_and_during_primary_failure(self):
        for primary_kind in ('none', 'provider', 'consistency', 'programming', 'cancellation'):
            for cleanup_kind in ('provider', 'programming', 'cancellation'):
                for detail in (False, True):
                    with self.subTest(primary=primary_kind, cleanup=cleanup_kind, detail=detail):
                        primary = {
                            'none': None, 'provider': httpx.ReadTimeout('private-wire-body'),
                            'consistency': PlacesConsistencyError(),
                            'programming': TypeError('programming error'), 'cancellation': CancelledError(),
                        }[primary_kind]
                        cleanup = {'provider': httpx.CloseError('private-credential'),
                                   'programming': RuntimeError('cleanup programming error'),
                                   'cancellation': CancelledError()}[cleanup_kind]
                        owned, closes = [], []
                        query = Mock()
                        query.select.return_value = query
                        query.eq.return_value = query
                        query.order.return_value = query
                        query.range.return_value = query
                        query.limit.return_value = query
                        query.retry.return_value = query
                        query.execute.return_value = SimpleNamespace(data=[])
                        query.execute.side_effect = primary
                        sdk = Mock()
                        sdk.table.return_value = query
                        def factory(**kwargs):
                            transport = httpx.MockTransport(
                                lambda request: self.fail('Unexpected request'))
                            http = httpx.Client(transport=transport, **kwargs)
                            owned.append(http)
                            original_close = transport.close
                            def close():
                                closes.append(True)
                                original_close()
                                raise cleanup
                            transport.close = close
                            return http
                        adapter = PublicPlacesClient('https://fixture.invalid', 'sb_publishable_private_fixture',
                            http_factory=factory, sdk_factory=Mock(return_value=sdk))
                        service = PlacesService(adapter.database_client)
                        winner = (cleanup if cleanup_kind == 'cancellation' or primary is None else primary)
                        expected = PlacesUnavailableError if isinstance(winner, httpx.HTTPError) else type(winner)
                        with self.assertRaises(expected) as raised:
                            if detail:
                                service.get_published_by_slug('synthetic-fixture')
                            else:
                                service.list_published()
                        if expected is PlacesUnavailableError:
                            self.assert_sanitized(raised.exception)
                        else:
                            self.assertIs(raised.exception, winner)
                            self.assert_sanitized(raised.exception)
                        if primary is not None:
                            note = ('Places operation also failed before cleanup.' if cleanup_kind == 'cancellation'
                                    else 'Places client cleanup also failed.')
                            self.assertIn(note, raised.exception.__notes__)
                        self.assertEqual(closes, [True])
                        self.assertTrue(owned[0].is_closed)

    def test_real_sdk_get_contract_cleanup_no_auth_or_retry(self):
        requests, owned = [], []
        payload = [self.row()]
        status = 200
        def handler(request):
            requests.append(request)
            return httpx.Response(status, json=payload)
        def factory(**kwargs):
            http = httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
            owned.append(http)
            return http
        adapter = PublicPlacesClient('https://fixture.invalid', 'sb_publishable_fixture', http_factory=factory)
        service = PlacesService(adapter.database_client)
        service.list_published(category='nature', limit=2, offset=3)
        self.assertEqual(dict(requests[-1].url.params), dict(select=PROJECTION, status='eq.published',
            category='eq.nature', order='slug.asc', offset='3', limit='2'))
        service.get_published_by_slug('SYNTHETIC-FIXTURE')
        self.assertEqual(dict(requests[-1].url.params), dict(select=PROJECTION, status='eq.published',
            slug='eq.synthetic-fixture', limit='2'))
        payload = [self.row(latitude=None)]
        with self.assertRaises(PlacesConsistencyError):
            service.list_published()
        status = 503
        payload = dict(code='503', message='private', details='private', hint='private')
        with self.assertRaises(PlacesUnavailableError):
            service.list_published()
        self.assertEqual(len(requests), 4)
        self.assertTrue(all(http.is_closed for http in owned))
        for request in requests:
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.path, '/rest/v1/places')
            self.assertEqual(request.headers['apikey'], 'sb_publishable_fixture')
            self.assertIn(request.headers.get('Authorization'), (None, 'Bearer sb_publishable_fixture'))
            self.assertEqual(request.content, b'')


if __name__ == '__main__':
    unittest.main()
