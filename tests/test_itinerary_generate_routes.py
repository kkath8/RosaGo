"""Automatic generation with real ranker, selector, adapter and auth scopes."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import io
import unittest
from unittest.mock import patch

from flask import before_render_template, g
from werkzeug.datastructures import MultiDict

import test_itinerary_preview_routes as preview
import test_itinerary_quiz_routes as quiz
import test_trip_routes as trips
from test_recommendation_engine import place
from itinerary_draft_service import DraftUnavailableError, DraftRejectedError, DraftConsistencyError
from itinerary_preview import PreviewContractError
from itinerary_selection_policy import SelectionPolicyError
from normal_auth_coordinator import SessionBusy, ClientUnavailable
from places_service import PlacesUnavailableError, PlacesConsistencyError

ROUTE = quiz.REVIEW.replace('/review', '/generate')
ORIGIN = preview.ORIGIN


class GenerateRouteTests(unittest.TestCase):
    setUp = preview.PreviewRouteTests.setUp
    tearDown = preview.PreviewRouteTests.tearDown
    seed = preview.PreviewRouteTests.seed
    protected = preview.PreviewRouteTests.protected
    assert_context = preview.PreviewRouteTests.assert_context
    read_current = preview.PreviewRouteTests.read_current
    store_preview = preview.PreviewRouteTests.store_preview
    edit_preview = preview.PreviewRouteTests.edit_preview

    def payload(self):
        return MultiDict({'csrf_token': self.csrf, 'expected_revision': '2'})

    def generate(self, **kwargs):
        return self.client.post(ROUTE, data=self.payload(), headers=ORIGIN, **kwargs)

    def test_real_pipeline_diversity_order_and_prg(self):
        self.current = replace(self.current, preferences=self.current.preferences | {
            'start_date': '2026-10-20', 'end_date': '2026-10-20', 'trip_pace': 'balanced',
            'interests': ['nature', 'attraction']})
        self.catalog.list_published.return_value = tuple(place(n, 'nature' if n < 5 else 'attraction')
                                                        for n in (6, 5, 4, 3, 2, 1))
        response = self.generate()
        self.assertEqual((response.status_code, response.location), (303, preview.PREVIEW))
        self.protected(response)
        self.engine.assert_called_once()
        self.catalog.list_published.assert_called_once_with(limit=100, offset=0)
        self.adapter.assert_called_once()
        self.assertEqual(self.adapter.call_args.kwargs['selected_place_ids'],
                         tuple(place(n).id for n in (1, 5, 6)))
        self.store.assert_called_once()
        self.assertEqual(self.current.preview.source.recommendation_policy_version, 'category-interest-v1')
        response = self.client.get(response.location)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'automatically selects', response.data)
        self.assertIn(b'not time feasibility', response.data)
        self.adapter.assert_called_once()
        self.store.assert_called_once()

    def test_zero_matches_read_only_prg_fixed_notice(self):
        before = deepcopy(self.current)
        for catalog in ((), (self.other,)):
            self.catalog.list_published.return_value = catalog
            response = self.generate()
            self.assertEqual((response.status_code, response.location),
                             (303, quiz.REVIEW + '?notice=no_matches'))
            response = self.client.get(response.location)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'No currently published destinations matched', response.data)
            self.assertIn(b'Edit Preferences', response.data)
            self.protected(response)
        self.assertEqual(self.current, before)
        self.assertNotIn(b'No currently published destinations matched', self.client.get(quiz.REVIEW).data)
        self.assertNotIn(b'<script>', self.client.get(quiz.REVIEW + '?notice=<script>').data)
        self.adapter.assert_not_called()
        self.store.assert_not_called()

    def test_insufficient_matches_excludes_unmatched(self):
        self.generate()
        self.assertEqual(self.current.preview.source.selected_place_ids, (self.match.id,))
        self.assertEqual(sum(len(day.stops) for day in self.current.preview.plan.days), 1)
        self.assertEqual(len(self.current.preview.plan.days), 7)

    def test_strict_fields_csrf_origin_before_reads(self):
        cases = []
        for origin in ({}, {'Origin': 'null'}, {'Origin': ''}, {'Origin': 'https://foreign.invalid'}):
            cases.append((self.payload(), origin, 403))
        for key, status in (('csrf_token', 403), ('expected_revision', 400)):
            data = self.payload(); del data[key]; cases.append((data, ORIGIN, status))
            data = self.payload(); data.add(key, data[key]); cases.append((data, ORIGIN, status))
        for key in ('selected_place_ids', 'user_id', 'preview', 'state', 'trip_pace'):
            data = self.payload(); data[key] = 'forged'; cases.append((data, ORIGIN, 400))
        data = self.payload(); data['csrf_token'] = 'invalid'; cases.append((data, ORIGIN, 403))
        for revision in ('0', '-1', '02', '2.0', '', '9223372036854775807'):
            data = self.payload(); data['expected_revision'] = revision; cases.append((data, ORIGIN, 400))
        data = self.payload(); data['upload'] = (io.BytesIO(b'bad'), 'file'); cases.append((data, ORIGIN, 400))
        for data, headers, status in cases:
            with self.subTest(fields=list(data), headers=headers):
                response = self.client.post(ROUTE, data=data, headers=headers)
                self.assertEqual(response.status_code, status)
                self.protected(response)
        self.assertEqual(self.client.get(ROUTE).status_code, 405)
        self.preview_read.assert_not_called()
        self.catalog.list_published.assert_not_called()
        self.store.assert_not_called()

    def test_authentication_and_unavailability(self):
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                self.assertEqual(self.generate().status_code, 503)
        for state in ({}, {'user_id': trips.OWNER}, {'password_recovery_id': 'fake'}):
            with self.client.session_transaction() as session:
                session.clear(); session.update(state)
            response = self.generate()
            self.assertEqual((response.status_code, response.location), (302, '/login?login_required=1'))
            self.protected(response)
        self.preview_read.assert_not_called()
        self.store.assert_not_called()

    def test_missing_foreign_state_expiry_and_revision(self):
        response = self.client.post(ROUTE.replace(trips.TRIP, trips.OWNER), data=self.payload(), headers=ORIGIN)
        self.assertEqual(response.status_code, 404)
        original = self.current
        for state in ('generating', 'failed', 'saved', 'expired', 'preview_ready'):
            self.current = replace(original, state=state)
            self.assertEqual(self.generate().status_code, 409)
        self.current = replace(original, revision=3)
        self.assertEqual(self.generate().status_code, 409)
        self.current = replace(original, expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(self.generate().status_code, 409)
        self.catalog.list_published.assert_not_called()
        self.store.assert_not_called()

    def test_catalog_safeguard_failures_and_incomplete_preferences(self):
        self.catalog.list_published.return_value = tuple(place(n) for n in range(100))
        self.assertEqual(self.generate().status_code, 503)
        for kind in (PlacesUnavailableError, PlacesConsistencyError):
            error = kind(); error.args = ('private-provider-message',)
            self.catalog.list_published.side_effect = error
            response = self.generate()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b'private-provider-message', response.data)
        self.catalog.list_published.reset_mock()
        for preferences in (None, {}, {'interests': ['attraction']}):
            self.current = replace(self.current, preferences=preferences)
            response = self.generate()
            self.assertEqual((response.status_code, response.location), (303, quiz.QUIZ))
        self.catalog.list_published.assert_not_called()
        self.store.assert_not_called()

    def test_single_attempt_sanitized_adapter_and_storage_failures(self):
        self.adapter.side_effect = PreviewContractError()
        self.assertEqual(self.generate().status_code, 409)
        self.store.assert_not_called()
        self.adapter.side_effect = None
        for kind, status in ((DraftUnavailableError, 503), (DraftRejectedError, 409), (DraftConsistencyError, 500)):
            error = kind(); error.args = ('private-provider-message',)
            self.store.side_effect = error; self.store.reset_mock()
            response = self.generate()
            self.assertEqual(response.status_code, status)
            self.assertNotIn(b'private-provider-message', response.data)
            self.store.assert_called_once()
            self.protected(response)

    def test_zero_match_notice_jinja_authority_isolation(self):
        self.catalog.list_published.return_value = ()
        seen = []
        def inspect(sender, template, context, **kwargs):
            self.assertNotIn('auth', g)
            seen.append(template.name)
        with before_render_template.connected_to(inspect, self.app):
            response = self.generate(follow_redirects=True)
        self.assertEqual(seen, ['itinerary/review.html'])
        for secret in (self.handle, trips.OWNER, 'private-access', 'private-refresh'):
            self.assertNotIn(secret.encode(), response.data)
        self.protected(response)

    def test_invalid_ranking_input_and_selector_failure_do_not_write(self):
        self.catalog.list_published.return_value = (self.match, self.match)
        response = self.generate()
        self.assertEqual(response.status_code, 503)
        self.protected(response)
        self.catalog.list_published.return_value = (self.match,)
        with patch.dict(self.namespace, select_destinations=unittest.mock.Mock(
                side_effect=SelectionPolicyError())):
            response = self.generate()
        self.assertEqual(response.status_code, 409)
        self.protected(response)
        self.adapter.assert_not_called()
        self.store.assert_not_called()
