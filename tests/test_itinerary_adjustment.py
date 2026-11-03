"""Offline conversational adjustment boundary tests; no live Gemini or database."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from werkzeug.datastructures import MultiDict

import test_ai_routes as ai
import test_itinerary_preview_routes as preview
import test_itinerary_draft_service as drafts
import test_gemini_service as gemini
from test_public_layout import Document, assert_shared_scripts
from test_recommendation_engine import place
from itinerary_adjustment import validate_adjustment
from itinerary_draft_service import adjust_itinerary_draft_preview, DraftResult, DraftUnavailableError, DraftValidationError
from itinerary_preview import validate_preview, build_personalized_preview


def interpretation(**changes):
    return dict(intent='modify', changes=dict(set_interests=None, add_interests=[],
        remove_interests=[], pace=None, place_count=None) | changes, unsupported_requests=[])


class AdjustmentRoutes(unittest.TestCase):
    tearDown = preview.PreviewRouteTests.tearDown
    seed = preview.PreviewRouteTests.seed
    assert_context = preview.PreviewRouteTests.assert_context
    read_current = preview.PreviewRouteTests.read_current
    store_preview = preview.PreviewRouteTests.store_preview
    edit_preview = preview.PreviewRouteTests.edit_preview
    ready = preview.PreviewRouteTests.ready

    def setUp(self):
        preview.PreviewRouteTests.setUp(self)
        self.places = tuple(place(n, 'attraction') for n in range(10, 16))
        self.heritage = place(20, 'heritage')
        self.catalog.list_published.return_value = self.places + (self.heritage,)
        self.ready(self.places[:4])
        self.provider = Mock(configured=True)
        self.provider.interpret_adjustment.return_value = interpretation(place_count=2)
        self.app.extensions['rosago_gemini'] = self.provider
        self.mutate = Mock(side_effect=self.save)
        guard = patch.dict(self.namespace, adjust_itinerary_draft_preview=self.mutate)
        guard.start(); self.addCleanup(guard.stop)
        self.path = preview.PREVIEW + '/adjust'

    def save(self, context, draft_id, revision, preferences, candidate):
        self.assert_context(context)
        self.assertEqual((draft_id, revision), (self.current.draft_id, self.current.revision))
        self.current = replace(self.current, revision=revision + 1, preferences=preferences,
                               preview=validate_preview(candidate))
        return DraftResult(draft_id, 'preview_ready', revision + 1)

    def post(self, data=None, headers=preview.ORIGIN):
        return self.client.post(self.path, headers=headers, data=data if data is not None else
            dict(csrf_token=self.csrf, expected_revision=str(self.current.revision), message='Only 2 places'))

    def test_category_change_rebuilds_using_real_engine_and_preserves_other_preferences(self):
        before = deepcopy(self.current.preferences)
        self.provider.interpret_adjustment.return_value = interpretation(set_interests=['heritage'])
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.current.preview.source.selected_place_ids, (self.heritage.id,))
        self.assertEqual(self.current.preferences, before | {'interests': ['heritage']})
        self.engine.assert_called_once()
        self.assertIn(b'Category interests: heritage.', response.data)
        self.assertEqual(self.current.revision, 4)

    def test_count_and_pace_supported_with_deterministic_published_order(self):
        original = deepcopy(self.current)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        selected = self.current.preview.source.selected_place_ids
        self.assertEqual(selected, tuple(p.id for p in self.places[:2]))
        self.assertEqual(self.current.preferences, original.preferences)
        self.current = original
        self.catalog.list_published.return_value = tuple(reversed(self.places)) + (self.heritage,)
        self.post()
        self.assertEqual(self.current.preview.source.selected_place_ids, selected)
        self.current = original
        self.provider.interpret_adjustment.return_value = interpretation(pace='relaxed')
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.current.preferences['trip_pace'], 'relaxed')
        days = len(self.current.preview.plan.days)
        self.assertEqual(len(self.current.preview.source.selected_place_ids), min(days * 2, len(self.places)))
        self.assertIn(b'Pace: relaxed.', response.data)
        self.assertTrue(set(self.current.preview.source.selected_place_ids) <= {p.id for p in self.places})

    def test_remove_category_and_add_interest(self):
        self.current = replace(self.current, preferences=self.current.preferences | {'interests': ['attraction', 'heritage']})
        self.ready(self.places[:3] + (self.heritage,))
        self.provider.interpret_adjustment.return_value = interpretation(remove_interests=['attraction'])
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.current.preview.source.selected_place_ids, (self.heritage.id,))
        self.provider.interpret_adjustment.return_value = interpretation(add_interests=['attraction'], place_count=2)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(len(self.current.preview.source.selected_place_ids), 2)

    def test_unsupported_requests_do_not_write_or_claim_compliance(self):
        before = deepcopy(self.current)
        for kind, phrase in [('budget', b'Exact budget planning is not available'), ('time', b'Exact end times'),
                             ('environment', b'Indoor or outdoor filtering is not available'), ('replacement', b'try changing your interests')]:
            self.provider.interpret_adjustment.return_value = interpretation() | {'unsupported_requests': [kind]}
            response = self.post()
            self.assertEqual(response.status_code, 200)
            self.assertIn(phrase, response.data)
            self.assertEqual(self.current, before)
        self.mutate.assert_not_called()

    def test_mixed_request_applies_supported_part_and_discloses_unsupported(self):
        self.provider.interpret_adjustment.return_value = interpretation(place_count=2) | {'unsupported_requests': ['budget', 'time', 'environment']}
        response = self.post()
        self.assertIn(b'Updated to 2 destinations.', response.data)
        for phrase in (b'Exact budget planning is not available', b'Exact end times', b'Indoor or outdoor filtering is not available'):
            self.assertIn(phrase, response.data)

    def test_ambiguous_invalid_and_injected_ai_output_never_writes(self):
        before = deepcopy(self.current)
        for output in (None, {}, interpretation(place_count=True), interpretation(place_count=101),
                       interpretation() | {'destination_ids': [self.heritage.id]},
                       interpretation() | {'intent': 'clarify'},
                       interpretation(set_interests=['unknown']), interpretation(remove_interests=['attraction'])):
            self.provider.interpret_adjustment.return_value = output
            response = self.post()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.current, before)
            self.assertEqual(len(Document(response.get_data(as_text=True)).find('article', **{'class': 'preview-stop'})), 4)
        self.mutate.assert_not_called()

    def test_zero_matches_keeps_original_preview(self):
        self.provider.interpret_adjustment.return_value = interpretation(set_interests=['shopping'])
        before = deepcopy(self.current)
        response = self.post()
        self.assertIn(b'No matching published destinations', response.data)
        self.assertEqual(self.current, before)
        self.mutate.assert_not_called()

    def test_actual_provider_timeout_malformed_json_and_unconfigured_leave_preview(self):
        before = deepcopy(self.current)
        for provider in (ai.GeminiService(), ai.mocked_gemini(error=httpx.ReadTimeout('private-secret')),
                         ai.mocked_gemini(output={'invalid': True}), ai.mocked_gemini(status=429)):
            self.app.extensions['rosago_gemini'] = provider
            response = self.post()
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Your itinerary has not changed', response.data)
            self.assertNotIn(b'private-secret', response.data)
            self.assertEqual(self.current, before)
        self.mutate.assert_not_called()

    def test_csrf_origin_exact_form_and_message_bounds_before_ai(self):
        good = dict(csrf_token=self.csrf, expected_revision='3', message='Two places')
        for data, headers, status in [(good | {'csrf_token': 'wrong'}, preview.ORIGIN, 403),
                (good, {}, 403), (good, {'Origin': 'https://foreign.invalid'}, 403),
                (good | {'destination_ids': self.heritage.id}, preview.ORIGIN, 400),
                (good | {'changes': '{"place_count":2}'}, preview.ORIGIN, 400),
                (good | {'message': 'x'*1001}, preview.ORIGIN, 400),
                (good | {'message': 'x'*9000}, preview.ORIGIN, 413),
                (good | {'message': ' '}, preview.ORIGIN, 400),
                (good | {'expected_revision': 'bad'}, preview.ORIGIN, 400),
                (MultiDict(list(good.items()) + [('message', 'duplicate')]), preview.ORIGIN, 400)]:
            self.assertEqual(self.post(data, headers).status_code, status)
        self.provider.interpret_adjustment.assert_not_called()
        self.mutate.assert_not_called()

    def test_auth_owner_revision_expiry_lifecycle(self):
        original = self.current
        self.assertEqual(self.client.post(self.path.replace(self.current.draft_id, drafts.OWNER),
            headers=preview.ORIGIN, data=dict(csrf_token=self.csrf, expected_revision='3', message='Two')).status_code, 404)
        for change in (dict(revision=4), dict(expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)),
                       *[dict(state=state) for state in ('editing', 'generating', 'failed', 'saved', 'expired')]):
            self.current = replace(original, **change)
            self.assertEqual(self.post(dict(csrf_token=self.csrf, expected_revision='3', message='Two')).status_code, 409)
        self.provider.interpret_adjustment.assert_not_called()
        self.mutate.assert_not_called()
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.post().status_code, 302)

    def test_catalog_change_or_failure_prevents_interpretation_and_write(self):
        for catalog in ((), (replace(self.places[0], name='Changed'),) + self.places[1:],
                        tuple(place(n) for n in range(100))):
            self.catalog.list_published.return_value = catalog
            self.assertIn(self.post().status_code, (409, 503))
        self.provider.interpret_adjustment.assert_not_called()
        self.mutate.assert_not_called()

    def test_explanations_clear_and_form_has_current_revision(self):
        self.provider.explain.return_value = {'explanations': [dict(place_id=self.places[0].id, reason='Old explanation')]}
        explained = self.client.post(preview.PREVIEW + '/explain', headers=preview.ORIGIN,
            data=dict(csrf_token=self.csrf, expected_revision='3'))
        self.assertIn(b'Old explanation', explained.data)
        response = self.post()
        self.assertNotIn(b'Old explanation', response.data)
        self.provider.explain.assert_called_once()
        self.assertIn(b'name="expected_revision" value="4"', response.data)
        self.assertIn(b'Why these places?', response.data)
        assert_shared_scripts(self,Document(response.get_data(as_text=True)))
        self.assertEqual(self.client.get(preview.PREVIEW).status_code, 200)
        # Checkpoint 2 still explains the new server-validated selection/revision.
        self.provider.explain.return_value = {'explanations': [dict(
            place_id=self.current.preview.source.selected_place_ids[0], reason='New explanation')]}
        response = self.client.post(preview.PREVIEW + '/explain', headers=preview.ORIGIN,
            data=dict(csrf_token=self.csrf, expected_revision='4'))
        self.assertIn(b'New explanation', response.data)

    def test_atomic_write_failure_is_not_retried(self):
        self.mutate.side_effect = DraftUnavailableError()
        before = deepcopy(self.current)
        self.assertEqual(self.post().status_code, 503)
        self.mutate.assert_called_once()
        self.assertEqual(self.current, before)


class InterpretationProtocol(unittest.TestCase):
    service = gemini.GeminiServiceTests.service

    def test_one_request_sends_only_message_and_schema_and_validates(self):
        expected = interpretation(place_count=2)
        provider = self.service(expected)
        self.assertEqual(provider.interpret_adjustment('Only two places'), expected)
        self.assertEqual(len(self.calls), 1)
        payload = json.loads(self.calls[0].content)
        context = json.loads(payload['contents'][0]['parts'][0]['text'])['context']
        self.assertEqual(context, {'message': 'Only two places'})
        self.assertNotIn('destination_ids', json.dumps(payload))
        self.assertIsNone(provider.interpret_adjustment('Only two places'))
        self.assertEqual(len(self.calls), 1)  # existing shared throttle

    def test_rejects_raw_invalid_json_injection_and_wrong_types(self):
        for raw in (b'not json',):
            self.assertIsNone(self.service(raw=raw).interpret_adjustment('Change places'))
        for output in (interpretation() | {'ids': ['unknown']}, interpretation(place_count=True),
                       interpretation(pace='extreme'), interpretation(add_interests=['heritage'], remove_interests=['heritage']),
                       interpretation() | {'unsupported_requests': ['invented']},
                       interpretation(place_count=2) | {'intent': 'clarify'}):
            self.assertIsNone(self.service(output).interpret_adjustment('Change places'))
        with self.assertRaises(ValueError):
            validate_adjustment(interpretation(set_interests=['heritage'], add_interests=['nature']))


class AtomicAdjustmentService(unittest.TestCase):
    setUp = drafts.DraftServiceTests.setUp
    tearDown = drafts.DraftServiceTests.tearDown
    result = drafts.DraftServiceTests.result

    def candidate(self):
        import test_itinerary_preview as fixtures
        args = fixtures.arguments() | {'draft_id': drafts.DRAFT, 'draft_revision': 3}
        return args['preferences'], build_personalized_preview(**args).to_document()

    def test_one_rpc_and_revision_increment(self):
        preferences, candidate = self.candidate()
        self.query.execute.return_value = SimpleNamespace(data=[dict(draft_id=drafts.DRAFT, state='preview_ready', revision=4)])
        result = adjust_itinerary_draft_preview(self.context, drafts.DRAFT, 3, preferences, candidate)
        self.assertEqual(result.revision, 4)
        self.client.rpc.assert_called_once_with('rosago_itinerary_draft_adjust_preview', dict(
            p_draft_id=drafts.DRAFT, p_expected_revision=3, p_preferences=preferences, p_candidate_preview=candidate))
        self.query.retry.assert_called_once_with(False)

    def test_invalid_contract_never_writes(self):
        preferences, candidate = self.candidate()
        for revision, document in ((2, candidate), (True, candidate), (3, {})):
            with self.assertRaises(DraftValidationError):
                adjust_itinerary_draft_preview(self.context, drafts.DRAFT, revision, preferences, document)
        self.client.rpc.assert_not_called()

    def test_rpc_network_failure_is_sanitized_and_never_retried(self):
        preferences, candidate = self.candidate()
        self.query.execute.side_effect = httpx.ReadTimeout('private-secret')
        with self.assertRaises(DraftUnavailableError) as raised:
            adjust_itinerary_draft_preview(self.context, drafts.DRAFT, 3, preferences, candidate)
        self.assertNotIn('private-secret', str(raised.exception))
        self.client.rpc.assert_called_once()
        self.query.execute.assert_called_once()
        self.query.retry.assert_called_once_with(False)


class AdjustmentMigrationContract(unittest.TestCase):
    def test_atomic_wrapper_keeps_existing_catalog_checks_and_limits_preference_changes(self):
        # Static contract only; actual transaction rollback/locks require PostgreSQL.
        sql = (Path(__file__).resolve().parents[1] /
               'migrations/0010_itinerary_preview_adjustment.sql').read_text(encoding='utf-8')
        code = '\n'.join(line.split('--')[0] for line in sql.splitlines())
        for required in ('owner_id uuid := auth.uid()', 'SECURITY DEFINER SET search_path = \'\'',
                         'draft.user_id = owner_id FOR UPDATE', "locked_draft.state <> 'preview_ready'",
                         'locked_draft.revision <> p_expected_revision',
                         'locked_draft.expires_at <= pg_catalog.clock_timestamp()',
                         'public.rosago_validate_draft_preferences(p_preferences)',
                         "locked_draft.preferences - ARRAY['interests', 'trip_pace']",
                         'public.rosago_itinerary_draft_store_preview(',
                         'FROM PUBLIC, anon, authenticated, service_role', 'TO authenticated;'):
            self.assertIn(required, code)
        self.assertNotIn('EXCEPTION WHEN', code)
        self.assertNotIn('CREATE TABLE', code)
        self.assertNotIn('ALTER POLICY', code)
        self.assertLess(code.index('FOR UPDATE'), code.index('UPDATE public.itinerary_drafts'))
        self.assertLess(code.index('UPDATE public.itinerary_drafts'), code.index('RETURN QUERY'))
