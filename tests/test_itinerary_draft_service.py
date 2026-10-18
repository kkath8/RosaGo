"""Offline service tests; mocked RPCs cannot establish database authorization."""
from dataclasses import FrozenInstanceError
import inspect
import socket
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from postgrest.exceptions import APIError

from normal_auth_coordinator import AuthenticatedContext
import itinerary_draft_service as service


OWNER = '00000000-0000-0000-0000-000000000001'
DRAFT = '00000000-0000-0000-0000-000000000002'


def preferences(**changes):
    return dict(interests=['nature', 'dining'], companion_type='solo',
                start_date='2026-10-17', end_date='2026-10-23',
                daily_start_time='08:00:00', daily_end_time='18:00:00',
                transportation='walking') | changes


class DraftServiceTests(unittest.TestCase):
    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        guard = patch('supabase.create_client', side_effect=AssertionError('New client forbidden.'))
        mocked = guard.start()
        self.addCleanup(guard.stop)
        self.addCleanup(mocked.assert_not_called)
        self.client = Mock(spec=['rpc', 'table', 'close', 'auth'])
        self.query = Mock(spec=['retry', 'execute'])
        self.query.retry.return_value = self.query
        self.client.rpc.return_value = self.query
        self.context = AuthenticatedContext('opaque-handle', OWNER, 'fixture@example.invalid', self.client)
        self.result(1)

    def tearDown(self):
        self.client.table.assert_not_called()
        self.client.close.assert_not_called()
        self.assertEqual(self.client.auth.mock_calls, [])

    def result(self, revision):
        self.query.execute.return_value = SimpleNamespace(data=[dict(draft_id=DRAFT, state='editing', revision=revision)])

    def update(self, **kwargs):
        args = dict(draft_id=DRAFT, expected_revision=1, preferences=preferences()) | kwargs
        return service.update_itinerary_draft_preferences(self.context, **args)

    def test_signatures_no_owner_or_lifecycle_parameters(self):
        self.assertEqual(list(inspect.signature(service.create_itinerary_draft).parameters), ['context'])
        self.assertEqual(list(inspect.signature(service.update_itinerary_draft_preferences).parameters),
                         ['context', 'draft_id', 'expected_revision', 'preferences'])

    def test_create_minimal_response_no_retry_or_client_lifecycle(self):
        result = service.create_itinerary_draft(self.context)
        self.assertEqual((result.draft_id, result.state, result.revision), (DRAFT, 'editing', 1))
        self.assertNotIn(DRAFT, repr(result))
        with self.assertRaises(FrozenInstanceError):
            result.revision = 2
        self.client.rpc.assert_called_once_with('rosago_itinerary_draft_create', {})
        self.query.retry.assert_called_once_with(False)
        self.query.execute.assert_called_once_with()

    def test_update_canonical_snapshot_and_exact_revision(self):
        self.result(8)
        original = preferences()
        result = self.update(expected_revision=7, preferences=original)
        self.assertEqual(result.revision, 8)
        self.assertNotIn('timezone', original)
        self.assertNotIn('budget_centavos', original)
        self.client.rpc.assert_called_once_with('rosago_itinerary_draft_update_preferences', {
            'p_draft_id': DRAFT, 'p_expected_revision': 7,
            'p_preferences': preferences(budget_centavos=None, timezone='Asia/Manila'),
        })
        self.query.retry.assert_called_once_with(False)
        self.query.execute.assert_called_once_with()

    def test_valid_boundaries_and_unknown_budget(self):
        self.result(2)
        for changes in ({'budget_centavos': 0}, {'budget_centavos': 10000000},
                        {'budget_centavos': None}, {'timezone': 'Asia/Manila'},
                        {'end_date': '2026-10-17'},
                        {'start_date': '2028-02-29', 'end_date': '2028-03-06'},
                        {'start_date': '9999-12-31', 'end_date': '9999-12-31'},
                        {'daily_end_time': '23:59:59'},
                        {'interests': sorted(service.CATEGORIES)}):
            with self.subTest(changes=changes):
                self.assertEqual(self.update(preferences=preferences(**changes)).revision, 2)

    def test_invalid_preferences_never_call_rpc(self):
        invalid = [None, [], {}, preferences(user_id=OWNER), preferences(state='saved'),
                   preferences(preview={}), preferences(schema_version=1)]
        for key in service.REQUIRED:
            value = preferences()
            del value[key]
            invalid.append(value)
        for key, values in {
            'interests': [None, 'nature', [], ['nature'] * 2, ['nature'] * 7, [None], [1], [{}], ['unknown']],
            'companion_type': [None, [], 1, 'Solo', ' solo', 'unknown'],
            'budget_centavos': [-1, 10000001, True, 1.0, '1', {}, float('nan')],
            'timezone': [None, 'UTC', 'Asia/Manila ', 1],
            'start_date': ['0000-01-01', '2026-02-29', '2026-13-01', '2026-10-17\n', '2026-1-1', None],
            'end_date': ['2026-10-16', '2026-10-24', 'infinity'],
            'daily_start_time': ['8:00:00', '08:00', '08:00:00Z', '24:00:00', '08:00:60', 'x' * 17000],
            'daily_end_time': ['08:00:00', '07:59:59', '24:00:00', '24:00:01', '18:00:00.1'],
            'transportation': ['bike', True, []],
        }.items():
            invalid.extend(preferences(**{key: value}) for value in values)
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(service.DraftValidationError):
                    self.update(preferences=value)
        self.client.rpc.assert_not_called()

    def test_invalid_identity_revision_context(self):
        for value in ('', 'invalid', ' ' + DRAFT, None, 1):
            with self.assertRaises(service.DraftValidationError):
                self.update(draft_id=value)
        for value in (0, -1, True, 1.0, '1', None, service.MAX_REVISION):
            with self.assertRaises(service.DraftValidationError):
                self.update(expected_revision=value)
        for context in (None, object(), AuthenticatedContext('h', 'bad', 'e', self.client),
                        AuthenticatedContext('h', OWNER, 'e', object())):
            with self.assertRaises(TypeError):
                service.create_itinerary_draft(context)
        self.client.rpc.assert_not_called()

    def test_sanitized_provider_mapping_without_exception_chains(self):
        for code, kind in (('22023', service.DraftValidationError), ('P0002', service.DraftRejectedError),
                           ('42501', service.DraftRejectedError), ('40001', service.DraftUnavailableError),
                           ('XX000', service.DraftUnavailableError)):
            self.query.execute.side_effect = APIError(dict(code=code, message='private-token',
                                                           details='private-token', hint='private-token'))
            with self.assertRaises(kind) as raised:
                self.update()
            self.assertIsNone(raised.exception.__context__)
            self.assertIsNone(raised.exception.__cause__)
            self.assertNotIn('private-token', ''.join(traceback.format_exception(raised.exception)))
        self.query.execute.side_effect = httpx.ReadTimeout('private-token')
        with self.assertRaises(service.DraftUnavailableError) as raised:
            service.create_itinerary_draft(self.context)
        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn('private-token', str(raised.exception))

    def test_malformed_responses_are_not_success(self):
        good = dict(draft_id=DRAFT, state='editing', revision=2)
        for data in (None, {}, [], [good, good], [None], [{}],
                     [good | {'draft_id': OWNER}], [good | {'draft_id': 'bad'}],
                     [good | {'state': 'saved'}], [good | {'revision': 1}],
                     [good | {'revision': True}], [good | {'revision': '2'}],
                     [good | {'private': 'private-token'}]):
            self.query.execute.return_value = SimpleNamespace(data=data)
            with self.assertRaises(service.DraftConsistencyError):
                self.update()
        self.result(2)
        with self.assertRaises(service.DraftConsistencyError):
            service.create_itinerary_draft(self.context)

    def test_programming_errors_propagate_and_no_retry(self):
        error = RuntimeError('sentinel')
        self.query.execute.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self.update()
        self.assertIs(raised.exception, error)
        self.query.execute.assert_called_once()


class DraftReadServiceTests(unittest.TestCase):
    setUp = DraftServiceTests.setUp
    result = DraftServiceTests.result

    def read_query(self, data):
        query = Mock(spec=['select', 'eq', 'limit', 'retry', 'execute'])
        for name in ('select', 'eq', 'limit', 'retry'):
            getattr(query, name).return_value = query
        query.execute.return_value = SimpleNamespace(data=data)
        self.client.table.return_value = query
        return query

    def row(self, **changes):
        return dict(id=DRAFT, user_id=OWNER, state='editing', schema_version=1, revision=2,
                    preferences=preferences(budget_centavos=None, timezone='Asia/Manila'),
                    expires_at='2099-01-01T00:00:00+00:00') | changes

    def tearDown(self):
        self.client.rpc.assert_not_called()
        self.client.close.assert_not_called()
        self.assertEqual(self.client.auth.mock_calls, [])

    def test_exact_projection_owner_filter_and_safe_result(self):
        query = self.read_query([self.row()])
        draft = service.get_itinerary_draft(self.context, DRAFT)
        self.client.table.assert_called_once_with('itinerary_drafts')
        query.select.assert_called_once_with(service.DRAFT_PROJECTION)
        self.assertEqual(query.eq.call_args_list, [unittest.mock.call('id', DRAFT), unittest.mock.call('user_id', OWNER)])
        query.limit.assert_called_once_with(2)
        query.retry.assert_called_once_with(False)
        self.assertEqual(draft.revision, 2)
        self.assertFalse(hasattr(draft, 'user_id'))
        self.assertNotIn(DRAFT, repr(draft))

    def test_missing_and_null_snapshot(self):
        self.read_query([])
        self.assertIsNone(service.get_itinerary_draft(self.context, DRAFT))
        self.read_query([self.row(preferences=None, revision=1)])
        self.assertIsNone(service.get_itinerary_draft(self.context, DRAFT).preferences)

    def test_invalid_rows_and_local_uuid(self):
        for data in (None, {}, [self.row(), self.row()], [{}],
                     [self.row(user_id=DRAFT)], [self.row(id=OWNER)], [self.row(revision=True)],
                     [self.row(schema_version=2)], [self.row(state='unknown')],
                     [self.row(expires_at='infinity')], [self.row(expires_at='2026-01-01')],
                     [self.row(preferences={})], [self.row(preferences=preferences())],
                     [self.row(preferences=preferences(timezone='UTC'))]):
            self.read_query(data)
            with self.assertRaises(service.DraftConsistencyError):
                service.get_itinerary_draft(self.context, DRAFT)
        self.client.table.reset_mock()
        with self.assertRaises(service.DraftValidationError):
            service.get_itinerary_draft(self.context, 'bad')
        self.client.table.assert_not_called()

    def test_read_provider_failures_sanitized(self):
        query = self.read_query([])
        for error in (APIError(dict(code='42501', message='private-token', details='private-token', hint='private-token')),
                      httpx.ReadTimeout('private-token')):
            query.execute.side_effect = error
            with self.assertRaises(service.DraftUnavailableError) as raised:
                service.get_itinerary_draft(self.context, DRAFT)
            self.assertIsNone(raised.exception.__context__)
            self.assertNotIn('private-token', ''.join(traceback.format_exception(raised.exception)))


if __name__ == '__main__':
    unittest.main()
