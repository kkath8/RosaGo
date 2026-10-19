"""Transient destination selection through real auth scopes and offline doubles."""
from dataclasses import replace
from datetime import datetime, timezone
import io
import unittest

from flask import before_render_template, g
from werkzeug.datastructures import MultiDict

import test_itinerary_recommendations as recommendations
import test_itinerary_quiz_routes as quiz
import test_trip_routes as trips
from test_public_layout import Document
from test_recommendation_engine import place
from normal_auth_coordinator import AuthenticatedContext
from places_service import PlacesUnavailableError, PlacesConsistencyError
from itinerary_draft_service import EXTENSION_FIELDS


ROUTE = quiz.REVIEW.replace('/review', '/selection')


class SelectionRouteTests(unittest.TestCase):
    seed = trips.TripRouteTests.seed
    protected = trips.TripRouteTests.protected
    setUp = recommendations.RecommendationRouteTests.setUp
    tearDown = recommendations.RecommendationRouteTests.tearDown
    test_authentication_and_unavailability_before_any_reads = (
        recommendations.RecommendationRouteTests.test_authentication_and_unavailability_before_any_reads)

    def payload(self, ids=None):
        data = MultiDict({'csrf_token': self.csrf, 'expected_revision': str(self.draft.revision)})
        for identity in ([self.match.id] if ids is None else ids):
            data.add('selected_place_ids', identity)
        return data

    def post(self, **kwargs):
        return self.client.post(ROUTE, data=self.payload(), **kwargs)

    def test_shortlist_form_only_matched_unchecked_accessible_controls(self):
        response = self.client.post(recommendations.ROUTE, data={'csrf_token': self.csrf})
        page = Document(response.get_data(as_text=True))
        form = page.find('form', action=ROUTE)[0]
        self.assertEqual(form.attrs['method'], 'post')
        checkboxes = page.find('input', type='checkbox')
        self.assertEqual([node.attrs['value'] for node in checkboxes], [self.match.id])
        for node in checkboxes:
            self.assertNotIn('checked', node.attrs)
            self.assertEqual(node.attrs['name'], 'selected_place_ids')
            self.assertEqual(node.ancestors[-1].tag, 'label')
            self.assertIn(form, node.ancestors)
        self.assertEqual(page.find('input', name='expected_revision')[0].attrs['value'], '2')
        self.assertEqual(page.find('input', name='csrf_token')[0].attrs['value'], self.csrf)
        self.assertEqual(page.find('button', type='submit')[0].text, 'Review Selected Destinations')
        self.assertTrue(page.find('a', href='/places/matched-place'))
        self.assertEqual(page.stack, [])

    def test_empty_match_set_has_no_selection_form(self):
        for places in ((), (self.other,)):
            self.catalog.list_published.return_value = places
            response = self.client.post(recommendations.ROUTE, data={'csrf_token': self.csrf})
            page = Document(response.get_data(as_text=True))
            self.assertEqual(page.find('input', type='checkbox'), [])
            self.assertEqual(page.find('form', action=ROUTE), [])
            self.assertTrue(page.find('a', href=quiz.QUIZ))
            self.assertTrue(page.find('a', href='/places'))

    def test_strict_form_csrf_origin_upload_and_revision_validation(self):
        cases = []
        for field, status in (('csrf_token', 403), ('expected_revision', 400)):
            missing = self.payload(); del missing[field]
            duplicate = self.payload(); duplicate.add(field, duplicate[field])
            cases.extend(((missing, {}, status), (duplicate, {}, status)))
        for value in ('', '0', '-1', '2.0', '02', '9223372036854775808'):
            data = self.payload(); data['expected_revision'] = value
            cases.append((data, {}, 400))
        bad_csrf = self.payload(); bad_csrf['csrf_token'] = 'bad'
        cases.append((bad_csrf, {}, 403))
        for origin in ('null', '', 'https://foreign.invalid', 'http://localhost.evil'):
            cases.append((self.payload(), {'Origin': origin}, 403))
        for field in ('name', 'category', 'score', 'preview', 'user_id', 'trip_id'):
            data = self.payload(); data[field] = 'forged'
            cases.append((data, {}, 400))
        data = self.payload(); data['file'] = (io.BytesIO(b'upload'), 'file.txt')
        cases.append((data, {}, 400))
        for data, headers, status in cases:
            with self.subTest(fields=list(data), headers=headers):
                response = self.client.post(ROUTE, data=data, headers=headers)
                self.assertEqual(response.status_code, status)
                self.protected(response)
        self.assertEqual(self.client.get(ROUTE).status_code, 405)
        self.read.assert_not_called()
        self.catalog.list_published.assert_not_called()

    def test_selection_minimum_maximum_duplicates_and_canonical_ids(self):
        for ids in ([], [self.match.id] * 2, [''], ['bad'], [self.match.id.replace('-', '')],
                    [' ' + self.match.id], [place(15).id.upper()],
                    [place(n).id for n in range(101)]):
            with self.subTest(ids=ids):
                response = self.client.post(ROUTE, data=self.payload(ids))
                self.assertEqual(response.status_code, 400)
                self.protected(response)
        self.read.assert_not_called()
        self.catalog.list_published.assert_not_called()

    def test_stale_revision_rejected_before_catalog_access(self):
        self.read.side_effect = None
        self.read.return_value = replace(self.draft, revision=3)
        response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertIn(b'preferences have changed', response.data)
        self.protected(response)
        self.read.assert_called_once()
        self.catalog.list_published.assert_not_called()

    def test_missing_foreign_expired_and_nonediting_drafts(self):
        self.read.side_effect = None
        self.read.return_value = None
        for identifier in (trips.TRIP, trips.OWNER):
            response = self.client.post(ROUTE.replace(trips.TRIP, identifier), data=self.payload())
            self.assertEqual((response.status_code, response.data), (404, b'Draft not found.'))
            self.protected(response)
        for state in ('generating', 'preview_ready', 'failed', 'saved', 'expired'):
            self.read.return_value = replace(self.draft, state=state)
            self.assertEqual(self.post().status_code, 409)
        self.read.return_value = replace(self.draft, expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(self.post().status_code, 409)
        self.catalog.list_published.assert_not_called()

    def test_incomplete_preferences_redirect_without_defaults(self):
        self.read.side_effect = None
        legacy = {key: value for key, value in self.draft.preferences.items() if key not in EXTENSION_FIELDS}
        for preferences in (None, legacy, {}):
            self.read.return_value = replace(self.draft, preferences=preferences)
            response = self.post()
            self.assertEqual((response.status_code, response.location), (303, quiz.QUIZ))
        self.catalog.list_published.assert_not_called()

    def test_unmatched_unknown_unpublished_and_changed_category_rejected_identically(self):
        self.client.post(recommendations.ROUTE, data={'csrf_token': self.csrf})
        responses = []
        for identity in (self.other.id, place(99).id):
            responses.append(self.client.post(ROUTE, data=self.payload([identity])))
        # Simulate archival since display: published service no longer returns it.
        self.catalog.list_published.return_value = (self.other,)
        responses.append(self.post())
        self.catalog.list_published.return_value = (replace(self.match, category='dining'),)
        responses.append(self.post())
        for response in responses:
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.data, responses[0].data)
            self.assertNotIn(b'Matched', response.data)
            self.assertNotIn(b'Unmatched dining', response.data)
            self.protected(response)

    def test_success_uses_rank_order_and_is_truthful_transient_response(self):
        later = replace(place(8, 'attraction'), name='Later destination', slug='later')
        self.catalog.list_published.return_value = (later, self.other, self.match)
        with self.client.session_transaction() as session:
            before = dict(session)
        response = self.client.post(ROUTE, data=self.payload([later.id, self.match.id]),
                                    headers={'Origin': 'http://localhost'})
        self.assertEqual(response.status_code, 200)
        self.protected(response)
        self.catalog.list_published.assert_called_once_with(limit=100, offset=0)
        self.engine.assert_called_once_with(self.draft.preferences, (later, self.other, self.match))
        page = Document(response.get_data(as_text=True))
        self.assertEqual(page.find('h1')[0].text, 'Selection Ready')
        self.assertIn(b'Selected destinations (2)', response.data)
        self.assertLess(response.data.index(b'Matched &lt;Place&gt;'), response.data.index(b'Later destination'))
        self.assertNotIn(b'Unmatched dining', response.data)
        self.assertIn(b'Your destination selection is ready. Itinerary building is the next step.', response.data)
        self.assertIn(b'No itinerary or trip has been created.', response.data)
        self.assertIn(b'may require resubmission', response.data)
        self.assertTrue(page.find('a', href=quiz.QUIZ))
        form = page.find('form', action=recommendations.ROUTE)[0]
        self.assertEqual(form.attrs['method'], 'post')
        self.assertIn('Back to Recommendations', form.text)
        build = page.find('form', action=quiz.REVIEW.replace('/review', '/preview'))[0]
        self.assertEqual(build.attrs['method'], 'post')
        self.assertIn('Build Itinerary', build.text)
        self.assertEqual(page.find('input', name='expected_revision')[0].attrs['value'], '2')
        self.assertEqual([node.attrs['value'] for node in page.find('input', name='selected_place_ids')],
                         [self.match.id, later.id])
        self.assertEqual(page.stack, [])
        for forbidden in (b'Day 1', b'Save Itinerary', b'Arrival', b'Departure', b'08:00'):
            self.assertNotIn(forbidden, response.data)
        with self.client.session_transaction() as session:
            self.assertEqual(dict(session), before)
        again = self.client.post(recommendations.ROUTE, data={'csrf_token': self.csrf})
        self.assertNotIn('checked', Document(again.get_data(as_text=True)).find('input', type='checkbox')[0].attrs)

    def test_catalog_failure_bound_and_maximum_current_selection(self):
        self.catalog.list_published.return_value = tuple(place(n, 'attraction') for n in range(99))
        response = self.client.post(ROUTE, data=self.payload([p.id for p in self.catalog.list_published.return_value]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Selected destinations (99)', response.data)
        self.catalog.list_published.return_value = tuple(place(n, 'attraction') for n in range(100))
        self.assertEqual(self.post().status_code, 503)
        for error_type in (PlacesUnavailableError, PlacesConsistencyError):
            error = error_type(); error.args = ('private-provider-message',)
            self.catalog.list_published.side_effect = error
            response = self.post()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b'Selection Ready', response.data)
            self.assertNotIn(b'private-provider-message', response.data)
            self.protected(response)

    def test_authority_isolation_and_escaped_test_record_display(self):
        self.catalog.list_published.return_value = (replace(self.match, slug='rosago-test-v1-attraction-01'),)
        seen = []
        def inspect(sender, template, context, **extra):
            self.assertNotIn('auth', g)
            for value in context.values():
                self.assertNotIsInstance(value, AuthenticatedContext)
                self.assertTrue(all(value is not client for client in self.owned))
            seen.append(template.name)
        with before_render_template.connected_to(inspect, self.app):
            response = self.post()
        self.assertEqual(seen, ['itinerary/selection.html'])
        self.assertIn(b'Test record', response.data)
        self.assertIn(b'Matched &lt;Place&gt;', response.data)
        self.assertIn(b'aria-current="true">Planner', response.data)
        for secret in (trips.OWNER, self.handle, 'private-access', 'private-refresh'):
            self.assertNotIn(secret.encode(), response.data)


if __name__ == '__main__':
    unittest.main()
