"""Authenticated shortlist routes with socket guards and no live database."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, patch

from flask import before_render_template, g
from werkzeug.datastructures import MultiDict

import test_itinerary_quiz_routes as quiz
import test_trip_routes as trips
from test_public_layout import Document
from test_recommendation_engine import place
from itinerary_draft_service import EXTENSION_FIELDS, DraftUnavailableError, DraftConsistencyError
from normal_auth_coordinator import AuthenticatedContext, SessionBusy, ClientUnavailable
from places_service import PlacesUnavailableError, PlacesConsistencyError
from recommendation_engine import rank_candidates


ROUTE = quiz.REVIEW.replace('/review', '/recommendations')


class RecommendationRouteTests(unittest.TestCase):
    seed = trips.TripRouteTests.seed
    protected = trips.TripRouteTests.protected

    def setUp(self):
        quiz.QuizRouteTests.setUp(self)
        self.read = self.drafts['get_itinerary_draft']
        self.catalog = Mock(spec=['list_published'])
        self.match = replace(place(2, 'attraction'), name='Matched <Place>', slug='matched-place')
        self.other = replace(place(1, 'dining'), name='Unmatched dining', slug='other-place')
        self.catalog.list_published.return_value = (self.other, self.match)
        self.app.extensions['rosago_places'] = self.catalog
        self.namespace = self.app.view_functions['itinerary_recommendations'].__wrapped__.__globals__
        self.engine = Mock(wraps=rank_candidates)
        guard = patch.dict(self.namespace, rank_candidates=self.engine)
        guard.start()
        self.addCleanup(guard.stop)
        self.original = deepcopy(self.draft)

    def tearDown(self):
        quiz.QuizRouteTests.tearDown(self)
        self.drafts['create_itinerary_draft'].assert_not_called()
        self.drafts['update_itinerary_draft_preferences'].assert_not_called()
        self.assertEqual(self.draft, self.original)

    def post(self, **kwargs):
        return self.client.post(ROUTE, data={'csrf_token': self.csrf}, **kwargs)

    def test_owned_shortlist_real_engine_and_presentation(self):
        response = self.post(headers={'Origin': 'http://localhost'})
        self.assertEqual(response.status_code, 200)
        self.protected(response)
        self.assertIn(b'aria-current="true">Planner', response.data)
        self.read.assert_called_once()
        self.assertEqual(self.read.call_args.args[1], trips.TRIP)
        self.catalog.list_published.assert_called_once_with(limit=100, offset=0)
        self.engine.assert_called_once_with(self.draft.preferences, (self.other, self.match))
        page = Document(response.get_data(as_text=True))
        self.assertEqual(page.find('h1')[0].text, 'Recommended Places')
        heading = page.find('header', **{'class': 'itinerary-heading'})[0]
        self.assertIn('Choose destinations, review your selection, then build an untimed itinerary preview.', heading.text)
        self.assertIn(b'Matched &lt;Place&gt;', response.data)
        self.assertNotIn(b'Unmatched dining', response.data)
        self.assertIn(b'Matches your Attractions interest.', response.data)
        self.assertIn(b'Fixture address', response.data)
        self.assertTrue(page.find('a', href='/places/matched-place'))
        for target in (quiz.QUIZ, quiz.REVIEW, '/places'):
            self.assertTrue(page.find('a', href=target))
        actions = page.find('nav', **{'aria-label': 'Shortlist actions'})[0]
        for label in ('Edit Preferences', 'Back to Review', 'Explore More Places'):
            self.assertIn(label, actions.text)
        self.assertEqual(page.stack, [])
        self.assertEqual(page.find('script'), [])
        for unsupported in (b'Affordable', b'Open now', b'5 stars', b'Day 1', b'Save Itinerary', b'Add to Trip'):
            self.assertNotIn(unsupported, response.data)
        self.assertIn(b'have not been evaluated', response.data)

    def test_authentication_and_unavailability_before_any_reads(self):
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                response = self.post()
                self.assertEqual(response.status_code, 503)
                self.protected(response)
        for state in ({}, {'user_id': trips.OWNER}, {'password_recovery_id': 'grant'}):
            with self.client.session_transaction() as session:
                session.clear()
                session.update(state)
            response = self.post()
            self.assertEqual((response.status_code, response.location), (302, '/login?login_required=1'))
            self.protected(response)
        self.read.assert_not_called()
        self.catalog.list_published.assert_not_called()

    def test_post_protections_precede_draft_and_catalog_reads(self):
        valid = {'csrf_token': self.csrf}
        cases = [({}, {}, 403), ({'csrf_token': 'bad'}, {}, 403),
                 (MultiDict([('csrf_token', self.csrf)] * 2), {}, 403),
                 (valid | {'interests': 'dining'}, {}, 400)]
        cases += [(valid, {'Origin': origin}, 403) for origin in
                  ('null', '', 'https://foreign.invalid', 'http://localhost.evil')]
        for data, headers, status in cases:
            with self.subTest(headers=headers, data=data):
                response = self.client.post(ROUTE, data=data, headers=headers)
                self.assertEqual(response.status_code, status)
                self.protected(response)
        self.read.assert_not_called()
        self.catalog.list_published.assert_not_called()

    def test_get_recommendations_is_read_only_return_target(self):
        response = self.client.get(ROUTE)
        self.assertEqual(response.status_code, 200)
        self.protected(response)
        self.read.assert_called_once()
        self.catalog.list_published.assert_called_once_with(limit=100, offset=0)
        self.assertIn(b'name="expected_revision" value="2"', response.data)

    def test_missing_foreign_and_unusable_states(self):
        self.read.side_effect = None
        self.read.return_value = None
        responses = [self.client.post(ROUTE.replace(trips.TRIP, identifier),
                                     data={'csrf_token': self.csrf})
                     for identifier in (trips.TRIP, trips.OWNER)]
        for response in responses:
            self.assertEqual((response.status_code, response.data), (404, b'Draft not found.'))
            self.protected(response)
        for state in ('generating', 'preview_ready', 'failed', 'saved', 'expired'):
            self.read.return_value = replace(self.draft, state=state)
            self.assertEqual(self.post().status_code, 409)
        self.read.return_value = replace(self.draft, expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(self.post().status_code, 409)
        self.catalog.list_published.assert_not_called()

    def test_incomplete_and_legacy_preferences_redirect_without_defaults(self):
        legacy = {key: value for key, value in self.draft.preferences.items() if key not in EXTENSION_FIELDS}
        self.read.side_effect = None
        for snapshot in (None, {}, legacy, self.draft.preferences | {'trip_pace': None},
                         self.draft.preferences | {'interests': ['invalid']}):
            self.read.return_value = replace(self.draft, preferences=snapshot)
            response = self.post()
            self.assertEqual((response.status_code, response.location), (303, quiz.QUIZ))
            self.protected(response)
        self.catalog.list_published.assert_not_called()
        self.engine.assert_not_called()

    def test_zero_matches_and_empty_catalog_are_honest(self):
        for places in ((), (self.other,)):
            self.catalog.list_published.return_value = places
            response = self.post()
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"We couldn't find published destinations matching your selected interests.", response.data)
            self.assertNotIn(b'Unmatched dining', response.data)
            self.assertNotIn(b'Why recommended:', response.data)

    def test_catalog_bound_never_silently_truncates_or_claims_zero(self):
        self.catalog.list_published.return_value = tuple(place(n, 'attraction') for n in range(99))
        self.assertEqual(self.post().status_code, 200)
        self.engine.reset_mock()
        for count in (100, 101):
            self.catalog.list_published.return_value = tuple(place(n, 'attraction') for n in range(count))
            response = self.post()
            self.assertEqual(response.status_code, 503)
            self.protected(response)
            self.assertIn(b'cannot show a complete shortlist', response.data)
            self.assertNotIn(b"couldn't find", response.data)
        self.engine.assert_not_called()

    def test_provider_and_consistency_failures_sanitized(self):
        for error_type in (PlacesUnavailableError, PlacesConsistencyError):
            error = error_type()
            error.args = ('private-provider-message',)
            self.catalog.list_published.side_effect = error
            response = self.post()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b'private-provider-message', response.data)
            self.assertNotIn(b"couldn't find", response.data)
            self.protected(response)
        self.catalog.list_published.side_effect = None
        self.catalog.list_published.return_value = (self.match, self.match)
        self.assertEqual(self.post().status_code, 503)
        for error_type, status in ((DraftUnavailableError, 503), (DraftConsistencyError, 500)):
            error = error_type()
            error.args = ('private-provider-message',)
            self.read.side_effect = error
            response = self.post()
            self.assertEqual(response.status_code, status)
            self.assertNotIn(b'private-provider-message', response.data)

    def test_template_has_no_authority_and_no_secret_output(self):
        seen = []
        def inspect(sender, template, context, **extra):
            self.assertNotIn('auth', g)
            for value in context.values():
                self.assertNotIsInstance(value, AuthenticatedContext)
                self.assertTrue(all(value is not client for client in self.owned))
            seen.append(template.name)
        with before_render_template.connected_to(inspect, self.app):
            response = self.post()
            self.catalog.list_published.side_effect = PlacesUnavailableError()
            error = self.post()
        self.assertEqual(seen, ['itinerary/recommendations.html'] * 2)
        for output in (response, error):
            for secret in (trips.OWNER, self.handle, 'private-access', 'private-refresh'):
                self.assertNotIn(secret.encode(), output.data)

    def test_test_record_disclosure_only_when_displaying_test_records(self):
        self.assertNotIn(b'Development preview:', self.post().data)
        self.catalog.list_published.return_value = (replace(self.match, slug='rosago-test-v1-attraction-01'),)
        response = self.post()
        self.assertIn(b'Development preview:', response.data)
        self.assertIn(b'not real businesses or attractions', response.data)
        self.assertIn(b'Test record', response.data)


if __name__ == '__main__':
    unittest.main()
