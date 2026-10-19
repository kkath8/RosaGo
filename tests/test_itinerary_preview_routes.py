"""Offline preview HTTP flow using real auth scopes, adapter and guarded I/O."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import io
import unittest
from unittest.mock import Mock, patch

from flask import before_render_template, g
from werkzeug.datastructures import MultiDict

import test_itinerary_recommendations as recommendations
import test_itinerary_quiz_routes as quiz
import test_trip_routes as trips
from test_public_layout import Document
from test_recommendation_engine import place
from itinerary_draft_service import (
    ItineraryPreviewDraft, DraftResult, DraftRejectedError, DraftValidationError,
    DraftUnavailableError, DraftConsistencyError,
)
from itinerary_preview import build_personalized_preview, validate_preview, PreviewContractError
from normal_auth_coordinator import AuthenticatedContext, SessionBusy, ClientUnavailable
from places_service import PlacesUnavailableError, PlacesConsistencyError

PREVIEW = quiz.REVIEW.replace('/review', '/preview')
EDIT = PREVIEW + '/edit'
ORIGIN = {'Origin': 'http://localhost'}


class PreviewRouteTests(unittest.TestCase):
    seed = trips.TripRouteTests.seed
    protected = trips.TripRouteTests.protected

    def setUp(self):
        recommendations.RecommendationRouteTests.setUp(self)
        self.current = ItineraryPreviewDraft(
            self.draft.draft_id, self.draft.state, self.draft.revision,
            self.draft.preferences, self.draft.expires_at, trips.OWNER, 1, None)
        self.preview_read = Mock(side_effect=self.read_current)
        self.store = Mock(side_effect=self.store_preview)
        self.edit = Mock(side_effect=self.edit_preview)
        self.adapter = Mock(wraps=build_personalized_preview)
        guard = patch.dict(self.namespace,
            get_itinerary_preview_draft=self.preview_read,
            store_itinerary_draft_preview=self.store,
            return_itinerary_draft_to_editing=self.edit,
            build_personalized_preview=self.adapter)
        guard.start(); self.addCleanup(guard.stop)
        self.read.side_effect = self.read_current

    def tearDown(self):
        recommendations.RecommendationRouteTests.tearDown(self)

    def assert_context(self, context):
        self.assertIs(context, g.auth)
        self.assertIs(context.client, self.owned[-1])
        self.assertEqual(context.user_id, trips.OWNER)

    def read_current(self, context, draft_id):
        self.assert_context(context)
        return self.current if draft_id == trips.TRIP else None

    def store_preview(self, context, draft_id, revision, candidate):
        self.assert_context(context)
        self.assertEqual((draft_id, revision), (trips.TRIP, self.current.revision))
        self.current = replace(self.current, state='preview_ready', revision=revision + 1,
                               preview=validate_preview(candidate))
        return DraftResult(draft_id, 'preview_ready', revision + 1)

    def edit_preview(self, context, draft_id, revision):
        self.assert_context(context)
        self.assertEqual((draft_id, revision), (trips.TRIP, self.current.revision))
        self.current = replace(self.current, state='editing', revision=revision + 1, preview=None)
        return DraftResult(draft_id, 'editing', revision + 1)

    def ready(self, places=None):
        selected = (self.match,) if places is None else places
        value = build_personalized_preview(preferences=self.current.preferences,
            selected_places=selected, selected_place_ids=tuple(p.id for p in selected),
            draft_id=trips.TRIP, draft_revision=2, publication_confirmed=True)
        self.current = replace(self.current, state='preview_ready', revision=3, preview=value)

    def payload(self, ids=None, revision='2'):
        data = MultiDict({'csrf_token': self.csrf, 'expected_revision': revision})
        for identity in ([self.match.id] if ids is None else ids):
            data.add('selected_place_ids', identity)
        return data

    def build(self, **kwargs):
        return self.client.post(PREVIEW, data=self.payload(), headers=ORIGIN, **kwargs)

    def return_edit(self, **kwargs):
        return self.client.post(EDIT, data={'csrf_token': self.csrf, 'expected_revision': '3'},
                                headers=ORIGIN, **kwargs)

    def test_build_real_adapter_order_and_prg_round_trip(self):
        later = replace(place(8, 'attraction'), name='Later destination', slug='later')
        self.catalog.list_published.return_value = (later, self.other, self.match)
        before = deepcopy(self.current)
        response = self.client.post(PREVIEW, data=self.payload([later.id, self.match.id]), headers=ORIGIN)
        self.assertEqual((response.status_code, response.location), (303, PREVIEW))
        self.protected(response)
        self.assertNotIn(b'Personalized Itinerary Preview', response.data)
        self.adapter.assert_called_once()
        self.assertEqual(self.adapter.call_args.kwargs['selected_place_ids'], (self.match.id, later.id))
        self.assertTrue(self.adapter.call_args.kwargs['publication_confirmed'])
        self.store.assert_called_once()
        self.assertEqual(self.store.call_args.args[1:3], (trips.TRIP, 2))
        candidate = self.store.call_args.args[3]
        self.assertEqual(validate_preview(candidate).source.draft_revision, 2)
        response = self.client.get(response.location)
        self.assertEqual(response.status_code, 200)
        self.protected(response)
        self.assertLess(response.data.index(b'Matched &lt;Place&gt;'), response.data.index(b'Later destination'))
        self.adapter.assert_called_once()  # No new candidate on GET.
        response = self.return_edit()
        self.assertEqual((response.status_code, response.location), (303, quiz.QUIZ))
        self.edit.assert_called_once()
        self.assertEqual(self.edit.call_args.args[1:], (trips.TRIP, 3))
        self.assertEqual((self.current.state, self.current.revision, self.current.preview), ('editing', 4, None))
        self.assertEqual(self.current.preferences, before.preferences)
        self.assertEqual(self.current.expires_at, before.expires_at)
        response = self.client.get(response.location)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="expected_revision" value="4"', response.data)
        response = self.client.get(recommendations.ROUTE)
        for node in Document(response.get_data(as_text=True)).find('input', type='checkbox'):
            self.assertNotIn('checked', node.attrs)

    def test_all_routes_require_normal_authentication(self):
        routes = [('GET', PREVIEW), ('POST', PREVIEW), ('POST', EDIT), ('GET', recommendations.ROUTE)]
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                for method, path in routes:
                    response = self.client.open(path, method=method, data=self.payload(), headers=ORIGIN)
                    self.assertEqual(response.status_code, 503)
                    self.protected(response)
        for state in ({}, {'user_id': trips.OWNER}, {'password_recovery_id': 'fake'}):
            with self.client.session_transaction() as session:
                session.clear(); session.update(state)
            for method, path in routes:
                response = self.client.open(path, method=method, data=self.payload(), headers=ORIGIN)
                self.assertEqual((response.status_code, response.location), (302, '/login?login_required=1'))
                self.protected(response)
        self.preview_read.assert_not_called()
        self.store.assert_not_called(); self.edit.assert_not_called()

    def test_mutation_csrf_origin_exact_fields_and_revisions(self):
        for path in (PREVIEW, EDIT):
            base = self.payload() if path == PREVIEW else MultiDict({'csrf_token': self.csrf, 'expected_revision': '3'})
            for headers in ({}, {'Origin': 'null'}, {'Origin': ''}, {'Origin': 'https://foreign.invalid'}):
                response = self.client.post(path, data=base, headers=headers)
                self.assertEqual(response.status_code, 403)
                self.protected(response)
            cases = []
            for key, status in (('csrf_token', 403), ('expected_revision', 400)):
                data = base.copy(); del data[key]; cases.append((data, status))
                data = base.copy(); data.add(key, data[key]); cases.append((data, status))
            data = base.copy(); data['csrf_token'] = 'invalid'; cases.append((data, 403))
            for revision in ('0', '-1', '02', '2.0', '', '9223372036854775808'):
                data = base.copy(); data['expected_revision'] = revision; cases.append((data, 400))
            for key in ('user_id', 'preview', 'state', 'name', 'trip_id'):
                data = base.copy(); data[key] = 'forged'; cases.append((data, 400))
            data = base.copy(); data['upload'] = (io.BytesIO(b'bad'), 'file'); cases.append((data, 400))
            for data, status in cases:
                response = self.client.post(path, data=data, headers=ORIGIN)
                self.assertEqual(response.status_code, status)
                self.protected(response)
        self.preview_read.assert_not_called()
        self.assertEqual(self.client.get(EDIT).status_code, 405)
        self.store.assert_not_called(); self.edit.assert_not_called()

    def test_build_strict_selection_bounds(self):
        for ids in ([], [self.match.id] * 2, ['bad'], [''], [self.match.id.replace('-', '')],
                    [' ' + self.match.id], [place(15).id.upper()], [place(n).id for n in range(101)]):
            response = self.client.post(PREVIEW, data=self.payload(ids), headers=ORIGIN)
            self.assertEqual(response.status_code, 400)
            self.protected(response)
        self.preview_read.assert_not_called()
        self.store.assert_not_called()

    def test_owned_missing_foreign_state_expiry_and_stale(self):
        for path, method in ((PREVIEW, 'POST'), (PREVIEW, 'GET'), (EDIT, 'POST')):
            response = self.client.open(path.replace(trips.TRIP, trips.OWNER), method=method,
                data=self.payload() if path == PREVIEW else {'csrf_token': self.csrf, 'expected_revision': '3'},
                headers=ORIGIN)
            self.assertEqual((response.status_code, response.data), (404, b'Draft not found.'))
            self.protected(response)
        for state in ('generating', 'failed', 'saved', 'expired', 'preview_ready'):
            self.current = replace(self.current, state=state)
            self.assertEqual(self.build().status_code, 409)
        self.current = replace(self.current, state='editing', revision=3)
        self.assertEqual(self.build().status_code, 409)
        self.current = replace(self.current, revision=2, expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(self.build().status_code, 409)
        self.assertEqual(self.client.get(PREVIEW).status_code, 409)
        self.assertEqual(self.return_edit().status_code, 409)
        self.catalog.list_published.assert_not_called()
        self.store.assert_not_called(); self.edit.assert_not_called()

    def test_selection_revalidated_against_current_matched_catalog(self):
        for ids, catalog in (([self.other.id], (self.match, self.other)),
                             ([place(99).id], (self.match,)),
                             ([self.match.id], (self.other,)),
                             ([self.match.id], (replace(self.match, category='dining'),))):
            self.catalog.list_published.return_value = catalog
            response = self.client.post(PREVIEW, data=self.payload(ids), headers=ORIGIN)
            self.assertEqual(response.status_code, 409)
            self.protected(response)
        self.adapter.assert_not_called(); self.store.assert_not_called()

    def test_build_catalog_bound_and_failure(self):
        self.catalog.list_published.return_value = tuple(place(n) for n in range(100))
        self.assertEqual(self.build().status_code, 503)
        for kind in (PlacesUnavailableError, PlacesConsistencyError):
            error = kind(); error.args = ('private-provider-message',)
            self.catalog.list_published.side_effect = error
            response = self.build()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b'private-provider-message', response.data)
        self.store.assert_not_called()

    def test_incomplete_preferences_cannot_build(self):
        for preferences in (None, {}, {'interests': ['attraction']}):
            self.current = replace(self.current, preferences=preferences)
            response = self.build()
            self.assertEqual((response.status_code, response.location), (303, quiz.QUIZ))
        self.catalog.list_published.assert_not_called(); self.store.assert_not_called()

    def test_adapter_and_store_failures_sanitized_without_retry(self):
        self.adapter.side_effect = PreviewContractError()
        self.assertEqual(self.build().status_code, 409)
        self.store.assert_not_called()
        self.adapter.side_effect = None
        for kind, status in ((DraftValidationError, 400), (DraftRejectedError, 409),
                             (DraftUnavailableError, 503), (DraftConsistencyError, 500)):
            error = kind(); error.args = ('private-provider-message',)
            self.store.side_effect = error
            self.store.reset_mock()
            response = self.build()
            self.assertEqual(response.status_code, status)
            self.assertNotIn(b'private-provider-message', response.data)
            self.store.assert_called_once()
            self.protected(response)

    def test_get_stored_plan_order_empty_days_details_and_disclosures(self):
        later = replace(place(8, 'attraction'), name='Second stop', slug='rosago-test-v1-attraction-02')
        self.catalog.list_published.return_value = (self.other, self.match, later)
        self.ready((later, self.match))  # Stored order, not catalog/recommendation order.
        response = self.client.get(PREVIEW + '?name=forged&selected_place_ids=bad')
        self.assertEqual(response.status_code, 200)
        self.protected(response)
        page = Document(response.get_data(as_text=True))
        self.assertEqual(page.find('h1')[0].text, 'Personalized Itinerary Preview')
        self.assertLess(response.data.index(b'Second stop'), response.data.index(b'Matched &lt;Place&gt;'))
        self.assertIn(b'Fixture address', response.data)
        self.assertIn(b'Test record', response.data)
        self.assertIn(b'not official tourism records', response.data)
        self.assertIn(b'An untimed plan', response.data)
        self.assertIn(b'route optimization are not yet applied', response.data)
        self.assertIn(b'No selected destinations are assigned to this day.', response.data)
        self.assertIn(b'PHP 5,000.50', response.data)
        self.assertIn(b'Asia/Manila', response.data)
        self.assertIn(b'No trip has been added to My Trips.', response.data)
        self.assertEqual(page.find('input', name='expected_revision')[0].attrs['value'], '3')
        self.assertEqual(len(page.find('section', **{'class': 'card itinerary-card preview-day'})), 7)
        self.assertEqual(page.stack, [])
        for forbidden in (b'forged', b'visit_duration', b'catalog_fingerprint', b'arrival_time',
                          b'5 stars', b'optimized schedule', b'AI-generated', b'<img', b'<script'):
            self.assertNotIn(forbidden, response.data)
        self.adapter.assert_not_called(); self.store.assert_not_called(); self.edit.assert_not_called()

    def test_get_budget_optional_and_zero(self):
        for budget in (None, 0):
            self.current = replace(self.current, preferences=self.draft.preferences | {'budget_centavos': budget})
            self.ready()
            response = self.client.get(PREVIEW)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b'Requested budget per person' in response.data, budget is not None)
            if budget == 0:
                self.assertIn(b'PHP 0.00', response.data)

    def test_get_unavailable_or_changed_place_never_omits_or_replaces(self):
        self.ready()
        before = deepcopy(self.current)
        for catalog in ((), (self.other,), (replace(self.match, name='Changed name'),),
                        (replace(self.match, category='dining'),)):
            self.catalog.list_published.return_value = catalog
            response = self.client.get(PREVIEW)
            self.assertEqual(response.status_code, 409)
            self.assertIn(b'Preview unavailable', response.data)
            self.assertIn(b'Edit Preferences', response.data)
            self.assertNotIn(b'preview-day-heading', response.data)
            self.protected(response)
        self.assertEqual(self.current, before)
        self.store.assert_not_called(); self.edit.assert_not_called()

    def test_get_contract_read_and_catalog_failures(self):
        self.ready()
        self.catalog.list_published.return_value = tuple(place(n) for n in range(100))
        self.assertEqual(self.client.get(PREVIEW).status_code, 503)
        self.catalog.list_published.side_effect = PlacesUnavailableError()
        self.assertEqual(self.client.get(PREVIEW).status_code, 503)
        self.catalog.list_published.side_effect = None
        bad_plan = replace(self.current.preview.plan, unresolved_constraints=())
        self.current = replace(self.current, preview=replace(self.current.preview, plan=bad_plan))
        self.assertEqual(self.client.get(PREVIEW).status_code, 500)
        for kind, status in ((DraftUnavailableError, 503), (DraftConsistencyError, 500)):
            error = kind(); error.args = ('private-provider-message',)
            self.preview_read.side_effect = error
            response = self.client.get(PREVIEW)
            self.assertEqual(response.status_code, status)
            self.assertNotIn(b'private-provider-message', response.data)
        self.store.assert_not_called(); self.edit.assert_not_called()

    def test_get_wrong_states_and_return_revision_state_errors(self):
        original = self.current
        for state in ('editing', 'generating', 'failed', 'saved', 'expired'):
            self.current = replace(original, state=state, revision=3)
            self.assertEqual(self.client.get(PREVIEW).status_code, 409)
            self.assertEqual(self.return_edit().status_code, 409)
        self.ready()
        self.current = replace(self.current, revision=4)
        self.assertEqual(self.return_edit().status_code, 409)
        self.edit.assert_not_called()
        self.ready()
        for kind, status in ((DraftRejectedError, 409), (DraftUnavailableError, 503)):
            error = kind(); error.args = ('private-provider-message',)
            self.edit.side_effect = error; self.edit.reset_mock()
            response = self.return_edit()
            self.assertEqual(response.status_code, status)
            self.assertNotIn(b'private-provider-message', response.data)
            self.edit.assert_called_once()
            self.protected(response)

    def test_jinja_has_no_authority_and_get_never_mutates(self):
        self.ready()
        seen = []
        def inspect(sender, template, context, **extra):
            self.assertNotIn('auth', g)
            for value in context.values():
                self.assertNotIsInstance(value, AuthenticatedContext)
                self.assertTrue(all(value is not client for client in self.owned))
            seen.append(template.name)
        before = deepcopy(self.current)
        with before_render_template.connected_to(inspect, self.app):
            response = self.client.get(PREVIEW)
        self.assertEqual(seen, ['itinerary/preview.html'])
        for secret in (trips.OWNER, self.handle, 'private-access', 'private-refresh'):
            self.assertNotIn(secret.encode(), response.data)
        self.assertIn(b'aria-current="true">Planner', response.data)
        self.assertEqual(before, self.current)
        self.adapter.assert_not_called(); self.store.assert_not_called(); self.edit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
