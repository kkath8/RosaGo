"""Mocked preview boundary tests, with all network connections forbidden."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
import traceback
import unittest
from unittest.mock import call

import httpx
from postgrest.exceptions import APIError

import itinerary_draft_service as service
import itinerary_preview as preview
import test_itinerary_draft_service as existing
import test_itinerary_preview as fixtures


def document():
    return preview.build_personalized_preview(**(fixtures.arguments() | {'draft_id': existing.DRAFT})).to_document()


class PreviewMutationTests(unittest.TestCase):
    setUp = existing.DraftServiceTests.setUp
    tearDown = existing.DraftServiceTests.tearDown
    result = existing.DraftServiceTests.result

    def store(self, **changes):
        return service.store_itinerary_draft_preview(self.context, **(dict(
            draft_id=existing.DRAFT, expected_revision=2, candidate_preview=document()) | changes))

    def editing(self, **changes):
        return service.return_itinerary_draft_to_editing(self.context, **(dict(
            draft_id=existing.DRAFT, expected_revision=3) | changes))

    def test_store_exact_rpc_and_new_state(self):
        self.query.execute.return_value = SimpleNamespace(data=[dict(
            draft_id=existing.DRAFT, state='preview_ready', revision=3)])
        candidate = document()
        before = deepcopy(candidate)
        result = self.store(candidate_preview=candidate)
        self.assertEqual((result.state, result.revision), ('preview_ready', 3))
        self.client.rpc.assert_called_once_with('rosago_itinerary_draft_store_preview', {
            'p_draft_id': existing.DRAFT, 'p_expected_revision': 2, 'p_candidate_preview': before})
        self.assertEqual(candidate, before)
        self.query.retry.assert_called_once_with(False)
        self.query.execute.assert_called_once_with()
        self.assertNotIn(existing.DRAFT, repr(result))

    def test_return_to_edit_exact_rpc(self):
        self.result(4)
        result = self.editing()
        self.assertEqual((result.state, result.revision), ('editing', 4))
        self.client.rpc.assert_called_once_with('rosago_itinerary_draft_return_to_editing', {
            'p_draft_id': existing.DRAFT, 'p_expected_revision': 3})
        self.query.retry.assert_called_once_with(False)
        self.query.execute.assert_called_once_with()

    def test_invalid_candidate_identity_revision_no_rpc(self):
        bad = document()
        bad['days'][0]['stops'][0]['arrival_time'] = '09:00:00'
        for candidate in (None, [], {}, bad, document() | {'unknown': True}):
            with self.assertRaises(service.DraftValidationError):
                self.store(candidate_preview=candidate)
        for method in (self.store, self.editing):
            for revision in (None, True, 0, -1, 1.0, service.MAX_REVISION):
                with self.assertRaises(service.DraftValidationError):
                    method(expected_revision=revision)
            with self.assertRaises(service.DraftValidationError):
                method(draft_id='invalid')
        with self.assertRaises(service.DraftValidationError):
            self.store(expected_revision=1)
        with self.assertRaises(service.DraftValidationError):
            self.store(draft_id=existing.OWNER)
        self.client.rpc.assert_not_called()

    def test_failure_sanitization_and_no_automatic_retry(self):
        errors = [(APIError(dict(code=code, message='secret-token', details='secret-token', hint='secret-token')), kind)
                  for code, kind in [('22023', service.DraftValidationError), ('P0002', service.DraftRejectedError),
                                     ('42501', service.DraftRejectedError), ('40001', service.DraftUnavailableError),
                                     ('40P01', service.DraftUnavailableError)]]
        errors.append((httpx.ReadTimeout('secret-token'), service.DraftUnavailableError))
        for method in (self.store, self.editing):
            for error, kind in errors:
                self.client.rpc.reset_mock()
                self.query.reset_mock()
                self.query.execute.side_effect = error
                with self.assertRaises(kind) as raised:
                    method()
                self.assertIsNone(raised.exception.__context__)
                self.assertIsNone(raised.exception.__cause__)
                self.assertNotIn('secret-token', ''.join(traceback.format_exception(raised.exception)))
                self.client.rpc.assert_called_once()
                self.query.retry.assert_called_once_with(False)
                self.query.execute.assert_called_once_with()

    def test_wrong_response_state_revision_or_shape_fails(self):
        for method, state, revision in ((self.store, 'preview_ready', 3), (self.editing, 'editing', 4)):
            good = dict(draft_id=existing.DRAFT, state=state, revision=revision)
            for data in ([], [good, good], [good | {'state': 'saved'}], [good | {'revision': revision - 1}],
                         [good | {'revision': True}], [good | {'preview': {}}], [good | {'draft_id': existing.OWNER}]):
                self.query.execute.return_value = SimpleNamespace(data=data)
                with self.assertRaises(service.DraftConsistencyError):
                    method()


class PreviewReadTests(unittest.TestCase):
    setUp = existing.DraftServiceTests.setUp
    result = existing.DraftServiceTests.result
    tearDown = existing.DraftReadServiceTests.tearDown
    read_query = existing.DraftReadServiceTests.read_query

    def row(self, **changes):
        return dict(id=existing.DRAFT, user_id=existing.OWNER, state='preview_ready',
                    schema_version=1, revision=3, preferences=fixtures.preferences(days=2),
                    preview=document(), expires_at='2099-01-01T00:00:00+00:00') | changes

    def read(self):
        return service.get_itinerary_preview_draft(self.context, existing.DRAFT)

    def test_preview_reader_owner_projection_and_model(self):
        query = self.read_query([self.row()])
        draft = self.read()
        self.assertIsInstance(draft, service.ItineraryPreviewDraft)
        self.assertEqual(draft.preview.to_document(), document())
        self.assertEqual((draft.user_id, draft.schema_version, draft.revision), (existing.OWNER, 1, 3))
        query.select.assert_called_once_with(service.PREVIEW_DRAFT_PROJECTION)
        self.assertEqual(query.eq.call_args_list, [call('id', existing.DRAFT), call('user_id', existing.OWNER)])
        query.limit.assert_called_once_with(2)
        query.retry.assert_called_once_with(False)
        self.assertNotIn(existing.DRAFT, repr(draft))
        with self.assertRaises(FrozenInstanceError):
            draft.preview = None
        self.assertFalse(hasattr(draft, 'accepted_preview_digest'))

    def test_missing_and_editing_preview(self):
        self.read_query([])
        self.assertIsNone(self.read())
        self.read_query([self.row(state='editing', preview=None, preferences=None, revision=1)])
        self.assertIsNone(self.read().preview)

    def test_malformed_or_inconsistent_preview(self):
        bad = document()
        bad['source_version']['version'] = 'v1:' + '0' * 64
        for changes in (dict(preview=None), dict(preview={}), dict(preview=bad), dict(state='editing'),
                        dict(revision=4), dict(preferences=None), dict(user_id=existing.DRAFT),
                        dict(preferences=fixtures.preferences(days=1)), dict(preferences=fixtures.preferences(days=2, budget=100))):
            self.read_query([self.row(**changes)])
            with self.assertRaises(service.DraftConsistencyError):
                self.read()

    def test_read_errors_sanitized(self):
        query = self.read_query([])
        for error in (httpx.ReadTimeout('secret-token'),
                      APIError(dict(code='42501', message='secret-token', details='secret-token', hint='secret-token'))):
            query.execute.side_effect = error
            with self.assertRaises(service.DraftUnavailableError) as raised:
                self.read()
            self.assertIsNone(raised.exception.__context__)
            self.assertNotIn('secret-token', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
