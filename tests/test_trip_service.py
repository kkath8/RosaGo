"""Offline trip contracts, including the installed SDK via MockTransport."""
from asyncio import CancelledError
import ast
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime
import inspect
import io
import json
from pathlib import Path
import socket
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

import httpx
from postgrest.exceptions import APIError
from postgrest.types import ReturnMethod
from supabase import ClientOptions, create_client

from normal_auth_coordinator import AuthenticatedContext
from places_service import Place, PROJECTION as PLACE_PROJECTION
import trip_service as service


OWNER = '00000000-0000-0000-0000-000000000001'
TRIP = '00000000-0000-0000-0000-000000000002'
PLACE = '00000000-0000-0000-0000-000000000003'
OTHER = '00000000-0000-0000-0000-000000000004'
STAMP = '2026-10-10T01:02:03Z'
SECRET = 'private-message private-details private-hint private-token'


def trip(**changes):
    return dict(id=TRIP, user_id=OWNER, name='Visit', visit_date=None,
                created_at=STAMP, updated_at=STAMP) | changes


def member(**changes):
    return dict(trip_id=TRIP, place_id=PLACE, position=1, created_at=STAMP) | changes


def place(**changes):
    return dict(id=PLACE, name='Offline fixture', slug='offline-fixture',
                description='Test fixture only', category='nature', address='Fixture address',
                latitude=14.0, longitude=121.0, image_url=None,
                created_at=STAMP, updated_at=STAMP) | changes


class TripServiceTests(unittest.TestCase):
    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Live network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        self.client = Mock(spec=['table', 'rpc', 'close', 'auth'])
        self.context = AuthenticatedContext('opaque-handle', OWNER, 'fixture@example.invalid', self.client)
        self.queries = []
        self.client.table.side_effect = lambda table: self.queries.pop(0)
        self.client.rpc.side_effect = lambda name, params: self.queries.pop(0)

    def query(self, data):
        methods = ['select', 'eq', 'gt', 'in_', 'order', 'range', 'limit',
                   'insert', 'update', 'delete', 'retry', 'execute']
        query = Mock(spec=methods)
        for method in methods[:-1]:
            getattr(query, method).return_value = query
        query.execute.return_value = SimpleNamespace(data=data)
        self.queries.append(query)
        return query

    def safe(self, error):
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        rendered = str(error) + repr(error) + ''.join(traceback.format_exception(error))
        for token in SECRET.split():
            self.assertNotIn(token, rendered)
        self.assertFalse(getattr(error, '__notes__', ()))

    def test_exact_public_signatures_and_no_ownership_input(self):
        expected = {
            'list_user_trips': ['context', 'limit', 'offset'],
            'get_user_trip': ['context', 'trip_id', 'membership_limit', 'after_position'],
            'create_trip': ['context', 'name', 'visit_date'],
            'update_trip': ['context', 'trip_id', 'name', 'visit_date'],
            'delete_trip': ['context', 'trip_id'],
            'add_place': ['context', 'trip_id', 'place_id'],
            'remove_place': ['context', 'trip_id', 'place_id'],
            'reorder_places': ['context', 'trip_id', 'place_ids'],
        }
        for name, parameters in expected.items():
            function = getattr(service, name)
            self.assertEqual(list(inspect.signature(function).parameters), parameters)
            with self.assertRaises(TypeError):
                function(self.context, user_id=OTHER)
        for name, fields_ in {'list_user_trips': ['limit', 'offset'],
                              'get_user_trip': ['membership_limit', 'after_position'],
                              'create_trip': ['name', 'visit_date'],
                              'update_trip': ['name', 'visit_date']}.items():
            for field in fields_:
                self.assertEqual(inspect.signature(getattr(service, name)).parameters[field].kind,
                                 inspect.Parameter.KEYWORD_ONLY)
        self.client.table.assert_not_called()
        self.client.rpc.assert_not_called()

    def test_service_has_no_flask_or_client_factory_dependency(self):
        tree = ast.parse(Path(service.__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(any(a.name.split('.')[0] in ('app', 'flask', 'supabase') for a in node.names))
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or '').split('.')[0], ('app', 'flask', 'supabase'))

    def test_list_exact_projection_owner_bounds_order_and_retry(self):
        query = self.query([trip()])
        with patch('supabase.create_client', side_effect=AssertionError('No new client')):
            result = service.list_user_trips(self.context, limit=100, offset=7)
        self.assertIsInstance(result, tuple)
        self.assertEqual(self.client.method_calls, [call.table('trips')])
        self.assertEqual(query.mock_calls, [
            call.select('id,user_id,name,visit_date,created_at,updated_at'), call.eq('user_id', OWNER),
            call.order('created_at', desc=True), call.order('id', desc=True), call.range(7, 106),
            call.retry(False), call.execute()])
        self.client.close.assert_not_called()
        self.assertEqual(self.client.auth.mock_calls, [])

    def test_models_frozen_slotted_redacted_and_minimal(self):
        self.query([trip(user_extra='secret')]); self.query([member()]); self.query([place()])
        detail = service.get_user_trip(self.context, TRIP)
        for value, expected in (
            (detail.trip, ['id', 'name', 'visit_date', 'created_at', 'updated_at']),
            (detail.memberships[0], ['trip_id', 'place_id', 'position', 'created_at', 'place']),
            (detail, ['trip', 'memberships', 'next_after_position']),
        ):
            self.assertEqual([f.name for f in fields(value)], expected)
            self.assertFalse(hasattr(value, '__dict__'))
            self.assertEqual(repr(value), f'<{type(value).__name__} redacted>')
            with self.assertRaises(FrozenInstanceError):
                setattr(value, expected[0], None)
        self.assertIsInstance(detail.memberships, tuple)
        self.assertIsInstance(detail.memberships[0].place, Place)
        self.assertFalse(hasattr(detail.trip, 'user_id'))

    def test_missing_or_rls_hidden_trip_stops_reads(self):
        query = self.query([])
        self.assertIsNone(service.get_user_trip(self.context, TRIP))
        self.assertEqual(self.client.method_calls, [call.table('trips')])
        self.assertEqual(query.mock_calls, [call.select(service.TRIP_PROJECTION), call.eq('id', TRIP),
                         call.eq('user_id', OWNER), call.limit(2), call.retry(False), call.execute()])

    def test_empty_page_has_no_place_query(self):
        self.query([trip()]); self.query([])
        result = service.get_user_trip(self.context, TRIP)
        self.assertEqual(result.memberships, ())
        self.assertIsNone(result.next_after_position)
        self.assertEqual(self.client.method_calls, [call.table('trips'), call.table('trip_places')])

    def test_paged_hydration_preserves_gaps_and_unavailable_members(self):
        self.query([trip()])
        membership_query = self.query([member(position=4), member(place_id=OTHER, position=9)])
        place_query = self.query([place()])
        detail = service.get_user_trip(self.context, TRIP, membership_limit=2, after_position=3)
        self.assertEqual(detail.next_after_position, 9)
        self.assertEqual([m.position for m in detail.memberships], [4, 9])
        self.assertEqual(detail.memberships[0].place.id, PLACE)
        self.assertIsNone(detail.memberships[1].place)
        self.assertEqual(membership_query.mock_calls, [call.select('trip_id,place_id,position,created_at'),
            call.eq('trip_id', TRIP), call.gt('position', 3), call.order('position', desc=False),
            call.limit(2), call.retry(False), call.execute()])
        self.assertEqual(place_query.mock_calls, [call.select(PLACE_PROJECTION), call.eq('status', 'published'),
            call.in_('id', [PLACE, OTHER]), call.limit(2), call.retry(False), call.execute()])
        self.assertEqual(self.client.method_calls, [call.table('trips'), call.table('trip_places'), call.table('places')])

    def test_all_unpublished_members_remain_without_fallback(self):
        self.query([trip()]); self.query([member(), member(place_id=OTHER, position=3)]); self.query([])
        detail = service.get_user_trip(self.context, TRIP)
        self.assertEqual([m.place for m in detail.memberships], [None, None])
        self.assertEqual(self.client.table.call_count, 3)
        self.client.rpc.assert_not_called()

    def test_failed_hydration_does_not_become_unavailable_places(self):
        self.query([trip()]); self.query([member()])
        query = self.query([])
        query.execute.side_effect = httpx.ReadTimeout(SECRET)
        with self.assertRaises(service.TripUnavailableError) as raised:
            service.get_user_trip(self.context, TRIP)
        self.safe(raised.exception)
        query.execute.assert_called_once()

    def test_create_and_update_exact_payload_and_returned_values(self):
        for operation in ('create', 'update'):
            with self.subTest(operation=operation):
                self.client.reset_mock()
                query = self.query([trip(visit_date='0001-01-01')])
                function = getattr(service, operation + '_trip')
                args = (self.context,) if operation == 'create' else (self.context, TRIP)
                result = function(*args, name='  Visit  ', visit_date=date.min)
                self.assertEqual(result.visit_date, date.min)
                payload = {'name': 'Visit', 'visit_date': '0001-01-01'}
                expected = ([call.insert(payload, returning=ReturnMethod.representation)] if operation == 'create'
                            else [call.update(payload, returning=ReturnMethod.representation),
                                  call.eq('id', TRIP), call.eq('user_id', OWNER)])
                self.assertEqual(query.mock_calls, expected + [call.select(service.TRIP_PROJECTION),
                                                               call.retry(False), call.execute()])
                self.assertEqual(self.client.method_calls, [call.table('trips')])

    def test_update_none_clears_date(self):
        query = self.query([trip()])
        self.assertIsNone(service.update_trip(self.context, TRIP, name='Visit', visit_date=None).visit_date)
        query.update.assert_called_once_with({'name': 'Visit', 'visit_date': None}, returning=ReturnMethod.representation)

    def test_delete_minimal_owned_representation(self):
        query = self.query([{'id': TRIP, 'user_id': OWNER}])
        self.assertIsNone(service.delete_trip(self.context, TRIP))
        self.assertEqual(query.mock_calls, [call.delete(returning=ReturnMethod.representation), call.eq('id', TRIP),
            call.eq('user_id', OWNER), call.select('id,user_id'), call.retry(False), call.execute()])
        self.assertEqual(self.client.method_calls, [call.table('trips')])

    def test_zero_row_write_behaviors(self):
        for function, args, kwargs, error in (
            (service.create_trip, (), {'name': 'Visit'}, service.TripConsistencyError),
            (service.update_trip, (TRIP,), {'name': 'Visit', 'visit_date': None}, service.TripNotFoundError),
            (service.delete_trip, (TRIP,), {}, service.TripNotFoundError),
        ):
            self.query([])
            with self.assertRaises(error):
                function(self.context, *args, **kwargs)

    def test_rpc_exact_mapping_order_normalization_and_void(self):
        for function, args, name, parameters in (
            (service.add_place, (TRIP, PLACE), 'rosago_trip_add_place', {'p_trip_id': TRIP, 'p_place_id': PLACE}),
            (service.remove_place, (TRIP, PLACE), 'rosago_trip_remove_place', {'p_trip_id': TRIP, 'p_place_id': PLACE}),
            (service.reorder_places, (TRIP, [OTHER.replace('-', ''), PLACE]), 'rosago_trip_reorder_places',
             {'p_trip_id': TRIP, 'p_place_ids': [OTHER, PLACE]}),
            (service.reorder_places, (TRIP, ()), 'rosago_trip_reorder_places', {'p_trip_id': TRIP, 'p_place_ids': []}),
        ):
            for data in (None, []):
                self.client.reset_mock()
                query = self.query(data)
                self.assertIsNone(function(self.context, *args))
                self.assertEqual(self.client.method_calls, [call.rpc(name, parameters)])
                self.assertEqual(query.mock_calls, [call.retry(False), call.execute()])

    def test_invalid_rpc_results_are_not_success_or_retried(self):
        for data in ({}, '', False, 0, [None], [member()], 'private-message'):
            query = self.query(data)
            with self.assertRaises(service.TripConsistencyError):
                service.add_place(self.context, TRIP, PLACE)
            query.execute.assert_called_once()

    def test_invalid_ids_rejected_before_io(self):
        for value in (None, '', 'bad', True, 7, {}, [], ' ' + TRIP, TRIP + ' '):
            for function, args in ((service.get_user_trip, (value,)), (service.delete_trip, (value,)),
                                   (service.add_place, (value, PLACE)), (service.remove_place, (TRIP, value)),
                                   (service.reorder_places, (TRIP, [value]))):
                with self.subTest(function=function.__name__, value=value), self.assertRaises(service.TripValidationError):
                    function(self.context, *args)
        self.client.table.assert_not_called(); self.client.rpc.assert_not_called()

    def test_invalid_names_dates_and_reorder_rejected_before_io(self):
        for value in (None, '', '   ', 'a' * 101, True, 7, 'a\x00', 'a\ud800', '\tVisit', 'Visit\n'):
            with self.assertRaises(service.TripValidationError):
                service.create_trip(self.context, name=value)
        for value in ('2026-01-01', datetime(2026, 1, 1), True, 0, []):
            with self.assertRaises(service.TripValidationError):
                service.update_trip(self.context, TRIP, name='Visit', visit_date=value)
        for value in (None, PLACE, {PLACE}, [PLACE, PLACE.replace('-', '')], [PLACE] * 1001, [[PLACE]]):
            with self.assertRaises(service.TripValidationError):
                service.reorder_places(self.context, TRIP, value)
        self.client.table.assert_not_called(); self.client.rpc.assert_not_called()

    def test_invalid_pagination_before_io(self):
        for value in (True, False, 0, -1, 101, 1.5, '50', None):
            for function, kwargs in ((service.list_user_trips, {'limit': value}),
                                     (service.get_user_trip, {'membership_limit': value})):
                with self.assertRaises(service.TripValidationError):
                    function(self.context, *(() if function is service.list_user_trips else (TRIP,)), **kwargs)
        for value in (True, -1, 2147483648, 1.5, None):
            with self.assertRaises(service.TripValidationError):
                service.list_user_trips(self.context, offset=value)
            with self.assertRaises(service.TripValidationError):
                service.get_user_trip(self.context, TRIP, after_position=value)
        with self.assertRaises(service.TripValidationError):
            service.list_user_trips(self.context, offset=2147483647, limit=2)
        self.client.table.assert_not_called(); self.client.rpc.assert_not_called()

    def test_valid_boundaries(self):
        self.query([])
        self.assertEqual(service.list_user_trips(self.context, limit=1, offset=2147483647), ())
        self.query([trip()]); self.query([])
        self.assertIsNone(service.get_user_trip(self.context, TRIP, after_position=2147483647).next_after_position)
        self.query([trip(name='é' * 100, visit_date='9999-12-31')])
        self.assertEqual(service.create_trip(self.context, name='é' * 100, visit_date=date.max).visit_date, date.max)
        ids = [str(__import__('uuid').UUID(int=i + 10)) for i in range(1000)]
        self.query(None)
        service.reorder_places(self.context, TRIP, ids)

    def test_invalid_context_is_programming_error_before_io(self):
        for context in (None, {}, SimpleNamespace(user_id=OWNER, client=self.client),
                        AuthenticatedContext('x', 'bad', 'x', self.client),
                        AuthenticatedContext('x', OWNER, 'x', object())):
            with self.assertRaises(TypeError):
                service.list_user_trips(context)
        self.client.table.assert_not_called()

    def test_trip_response_shape_identity_dates_and_order_validation(self):
        bad_rows = [None, {}, trip(user_id=OTHER), trip(id='bad'), trip(name=' Visit'),
                    trip(name=''), trip(visit_date='20260101'), trip(visit_date='2026-02-30'),
                    trip(visit_date=7), trip(created_at='2026-01-01'), trip(updated_at=SECRET)]
        for data in (None, {}, 'bad', [trip(), trip()], *([row] for row in bad_rows)):
            self.query(data)
            with self.assertRaises(service.TripConsistencyError) as raised:
                service.get_user_trip(self.context, TRIP)
            self.safe(raised.exception)
        self.query([trip(id=OTHER)])
        with self.assertRaises(service.TripConsistencyError):
            service.get_user_trip(self.context, TRIP)
        for rows in ([trip(), trip()], [trip(), trip(id=OTHER)], [trip()] * 101):
            self.query(rows)
            with self.assertRaises(service.TripConsistencyError):
                service.list_user_trips(self.context)

    def test_membership_validation_stops_before_hydration(self):
        bad = [None, {}, member(trip_id=OTHER), member(place_id='bad'), member(position=True),
               member(position=0), member(position=2147483648), member(created_at=SECRET)]
        for rows in (*([row] for row in bad), [member(), member()],
                     [member(position=3), member(place_id=OTHER, position=2)]):
            self.query([trip()]); self.query(rows)
            with self.assertRaises(service.TripConsistencyError) as raised:
                service.get_user_trip(self.context, TRIP)
            self.safe(raised.exception)
        self.query([trip()]); self.query([member()])
        with self.assertRaises(service.TripConsistencyError):
            service.get_user_trip(self.context, TRIP, after_position=1)

    def test_place_hydration_validation(self):
        for rows in ([place(id=OWNER)], [place(latitude=None)], [place(created_at=SECRET)],
                     [place(), place()], [place(), place(id=OTHER)]):
            self.query([trip()]); self.query([member(), member(place_id=OTHER, position=2)]); self.query(rows)
            with self.assertRaises(service.TripConsistencyError) as raised:
                service.get_user_trip(self.context, TRIP)
            self.safe(raised.exception)

    def test_write_response_owner_identity_and_submitted_values(self):
        for function, args, kwargs in (
            (service.create_trip, (), {'name': 'Visit'}),
            (service.update_trip, (TRIP,), {'name': 'Visit', 'visit_date': None}),
        ):
            for data in ([trip(user_id=OTHER)], [trip(name='Different')], [trip(visit_date='2026-01-01')],
                         [trip(), trip()], None):
                query = self.query(data)
                with self.assertRaises(service.TripConsistencyError):
                    function(self.context, *args, **kwargs)
                query.execute.assert_called_once()
        for data in ([{'id': OTHER, 'user_id': OWNER}], [{'id': TRIP, 'user_id': OTHER}], [{}],
                     [trip(), trip()], None):
            self.query(data)
            with self.assertRaises(service.TripConsistencyError):
                service.delete_trip(self.context, TRIP)

    def test_provider_mapping_sanitization_and_no_write_replay(self):
        operations = [lambda: service.create_trip(self.context, name='Visit'),
                      lambda: service.update_trip(self.context, TRIP, name='Visit', visit_date=None),
                      lambda: service.delete_trip(self.context, TRIP),
                      lambda: service.add_place(self.context, TRIP, PLACE),
                      lambda: service.remove_place(self.context, TRIP, PLACE),
                      lambda: service.reorder_places(self.context, TRIP, [])]
        for operation in operations:
            for code, expected in [('P0002', service.TripNotFoundError),
                                   ('22023', service.TripOperationRejectedError),
                                   ('23505', service.TripUnavailableError),
                                   ('40P01', service.TripUnavailableError),
                                   (None, service.TripUnavailableError)]:
                query = self.query(None)
                error = (APIError({'code': code, 'message': SECRET, 'details': SECRET, 'hint': SECRET})
                         if code else httpx.ReadTimeout(SECRET))
                error.add_note(SECRET)
                query.execute.side_effect = error
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output), self.assertRaises(expected) as raised:
                    operation()
                self.safe(raised.exception)
                self.assertEqual(output.getvalue(), '')
                query.execute.assert_called_once()
                query.retry.assert_called_once_with(False)

    def test_programming_errors_and_control_flow_propagate(self):
        for error in (RuntimeError('bug'), TypeError('bug'), CancelledError(), KeyboardInterrupt(), SystemExit()):
            query = self.query(None)
            query.execute.side_effect = error
            with self.assertRaises(type(error)) as raised:
                service.add_place(self.context, TRIP, PLACE)
            self.assertIs(raised.exception, error)

    def sdk(self, handler):
        http = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http.close)
        client = create_client('https://offline.example.invalid', 'sb_publishable_offline', options=ClientOptions(
            headers={'Authorization': 'Bearer offline-user-token'}, persist_session=False,
            auto_refresh_token=False, httpx_client=http))
        return AuthenticatedContext('handle', OWNER, 'fixture@example.invalid', client), http

    def test_installed_sdk_read_wire_contract_and_client_lifetime(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'trips': [trip()], 'trip_places': [member()],
                                            'places': [place()]}[request.url.path.rsplit('/', 1)[1]])
        context, http = self.sdk(handler)
        result = service.get_user_trip(context, TRIP, membership_limit=2, after_position=0)
        self.assertIsInstance(result.memberships[0].place, Place)
        self.assertEqual(len(requests), 3)
        for request in requests:
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.headers['authorization'], 'Bearer offline-user-token')
            self.assertTrue(request.url.path.startswith('/rest/v1/'))
        self.assertEqual(dict(requests[0].url.params), {'select': service.TRIP_PROJECTION,
                         'id': 'eq.' + TRIP, 'user_id': 'eq.' + OWNER, 'limit': '2'})
        self.assertEqual(dict(requests[1].url.params), {'select': service.MEMBERSHIP_PROJECTION,
                         'trip_id': 'eq.' + TRIP, 'position': 'gt.0', 'order': 'position.asc', 'limit': '2'})
        self.assertEqual(dict(requests[2].url.params), {'select': PLACE_PROJECTION,
                         'status': 'eq.published', 'id': 'in.(' + PLACE + ')', 'limit': '1'})
        self.assertFalse(http.is_closed)

    def test_installed_sdk_mutation_wire_contracts_and_void_forms(self):
        requests = []
        def handler(request):
            requests.append(request)
            if '/rpc/' in request.url.path:
                return httpx.Response(204) if request.url.path.endswith('remove_place') else httpx.Response(200, json=None)
            return httpx.Response(200, json=[trip()])
        context, http = self.sdk(handler)
        service.create_trip(context, name='Visit')
        service.update_trip(context, TRIP, name='Visit', visit_date=None)
        service.delete_trip(context, TRIP)
        service.add_place(context, TRIP, PLACE)
        service.remove_place(context, TRIP, PLACE)
        service.reorder_places(context, TRIP, [OTHER, PLACE])
        self.assertEqual([r.method for r in requests], ['POST', 'PATCH', 'DELETE', 'POST', 'POST', 'POST'])
        for request in requests[:2]:
            self.assertEqual(json.loads(request.content), {'name': 'Visit', 'visit_date': None})
            self.assertEqual(request.url.params['select'], service.TRIP_PROJECTION)
            self.assertIn('return=representation', request.headers['prefer'])
        for request in requests[1:3]:
            self.assertEqual(request.url.params['id'], 'eq.' + TRIP)
            self.assertEqual(request.url.params['user_id'], 'eq.' + OWNER)
        self.assertEqual(requests[2].url.params['select'], 'id,user_id')
        for request, suffix, payload in zip(requests[3:], ['add_place', 'remove_place', 'reorder_places'],
                [{'p_trip_id': TRIP, 'p_place_id': PLACE}, {'p_trip_id': TRIP, 'p_place_id': PLACE},
                 {'p_trip_id': TRIP, 'p_place_ids': [OTHER, PLACE]}]):
            self.assertEqual(request.url.path, '/rest/v1/rpc/rosago_trip_' + suffix)
            self.assertEqual(json.loads(request.content), payload)
        self.assertFalse(http.is_closed)

    def test_installed_sdk_uncertain_writes_execute_once(self):
        for failure in ('transport', 'provider', 'malformed'):
            requests = []
            def handler(request):
                requests.append(request)
                if failure == 'transport':
                    raise httpx.ReadTimeout(SECRET)
                if failure == 'provider':
                    return httpx.Response(503, json={'code': '503', 'message': SECRET, 'details': SECRET, 'hint': SECRET})
                return httpx.Response(200, text=SECRET)
            context, http = self.sdk(handler)
            expected = service.TripConsistencyError if failure == 'malformed' else service.TripUnavailableError
            with self.assertRaises(expected) as raised:
                service.add_place(context, TRIP, PLACE)
            self.safe(raised.exception)
            self.assertEqual(len(requests), 1)
            self.assertFalse(http.is_closed)


if __name__ == '__main__':
    unittest.main()
