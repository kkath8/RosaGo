"""Offline HTTP-boundary coverage: real SDK, services, models and templates.

The transport supplies synthetic PostgREST responses; this cannot prove live RLS
or reproduce an unknown running server's state. Socket guards remain enabled.
"""
from copy import deepcopy
import json
import unittest

import httpx
from werkzeug.datastructures import MultiDict

from normal_auth_coordinator import SupabaseAdapters
from places_client import PublicPlacesClient
from places_service import PlacesService
from itinerary_quiz_form import parse_quiz_form
from itinerary_draft_service import validate_complete_preferences
from test_itinerary_quiz_form import form
from test_public_layout import Document
import test_registration
import test_trip_routes as trips


ROOT = '/user/itinerary/' + trips.TRIP
ORIGIN = {'Origin': 'http://localhost'}


class ItineraryRuntimeTests(unittest.TestCase):
    seed = trips.TripRouteTests.seed
    protected = trips.TripRouteTests.protected

    def setUp(self):
        test_registration.RegistrationTests.setUp(self)
        self.dependencies = self.app.extensions['rosago_normal_auth']
        self.handle = self.seed()
        self.csrf = self.dependencies.store.resolve(self.handle).csrf
        self.row = dict(id=trips.TRIP, user_id=trips.OWNER, state='editing',
                        schema_version=1, revision=2,
                        preferences=parse_quiz_form(form())[1],
                        expires_at='2099-01-01T00:00:00Z', preview=None)
        self.place = dict(id='00000000-0000-0000-0000-000000000002',
                          name='Synthetic <destination>', slug='rosago-test-v1-attraction-01',
                          description='Synthetic destination', category='attraction',
                          address='Fixture address', latitude=14.0, longitude=121.0,
                          image_url=None, created_at='2026-10-17T00:00:00Z',
                          updated_at='2026-10-17T00:00:00Z')
        self.calls = []
        self.http_clients = []

        def http_factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(self.respond), **kwargs)
            self.http_clients.append(client)
            return client

        config = ('https://example.supabase.co', 'sb_publishable_synthetic_test_fixture')
        adapters = SupabaseAdapters(*config, http_factory=http_factory)
        self.dependencies.coordinator._clients = adapters.database_client
        public = PublicPlacesClient(*config, http_factory=http_factory)
        self.app.extensions['rosago_places'] = PlacesService(public.database_client)

    def tearDown(self):
        self.assertTrue(all(client.is_closed for client in self.http_clients))
        self.assertEqual(self.supabase.mock_calls, [])

    def respond(self, request):
        path = request.url.path
        self.calls.append((request.method, path))
        if path == '/rest/v1/places':
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.params['status'], 'eq.published')
            self.assertNotEqual(request.headers.get('authorization'), 'Bearer private-access')
            return httpx.Response(200, json=[self.place])
        self.assertEqual(request.headers['authorization'], 'Bearer private-access')
        if path == '/rest/v1/itinerary_drafts':
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.params['id'], 'eq.' + trips.TRIP)
            self.assertEqual(request.url.params['user_id'], 'eq.' + trips.OWNER)
            keys = request.url.params['select'].split(',')
            return httpx.Response(200, json=[{key: self.row[key] for key in keys}])
        self.assertEqual(request.method, 'POST')
        payload = json.loads(request.content)
        self.assertEqual(payload['p_draft_id'], trips.TRIP)
        self.assertEqual(payload['p_expected_revision'], self.row['revision'])
        if path == '/rest/v1/rpc/rosago_itinerary_draft_update_preferences':
            preferences = payload['p_preferences']
            self.assertEqual(validate_complete_preferences(preferences), preferences)
            self.row.update(preferences=preferences)
        elif path == '/rest/v1/rpc/rosago_itinerary_draft_store_preview':
            self.row.update(state='preview_ready', preview=payload['p_candidate_preview'])
        elif path == '/rest/v1/rpc/rosago_itinerary_draft_return_to_editing':
            self.row.update(state='editing', preview=None)
        else:
            self.fail('Unexpected SDK operation: ' + path)
        self.row['revision'] += 1
        return httpx.Response(200, json=[dict(draft_id=trips.TRIP,
            state=self.row['state'], revision=self.row['revision'])])

    def submit_form(self, response, action):
        page = Document(response.get_data(as_text=True))
        target = page.find('form', action=action)[0]
        data = MultiDict((node.attrs['name'], node.attrs['value'])
                         for node in page.find('input') if target in node.ancestors)
        return self.client.post(action, data=data, headers=ORIGIN)

    def test_fresh_quiz_rendered_controls_submit_through_real_parser_and_service(self):
        self.row.update(revision=1, preferences=None)
        response = self.client.get(ROOT + '/preferences')
        self.assertEqual(response.status_code, 200)
        page = Document(response.get_data(as_text=True))
        target = page.find('form', action=ROOT + '/preferences')[0]
        entered = dict(budget='5000.50', start_date='2026-10-19', end_date='2026-10-20',
                       daily_start_time='08:00', daily_end_time='17:00',
                       other_interests='', additional_preferences='')
        payload = MultiDict()
        chosen = set()
        for node in page.elements:
            if node.tag not in ('input', 'textarea') or target not in node.ancestors:
                continue
            name = node.attrs['name']
            kind = node.attrs.get('type')
            if kind in ('radio', 'checkbox'):
                # Select the first real rendered choice in each required group.
                if name in chosen:
                    continue
                chosen.add(name)
                payload.add(name, node.attrs['value'])
            else:
                payload.add(name, entered.get(name,
                    node.text if node.tag == 'textarea' else node.attrs['value']))
        expected_revision, canonical = parse_quiz_form(payload)
        self.assertEqual(expected_revision, 1)
        self.assertEqual(validate_complete_preferences(canonical), canonical)
        response = self.client.post(target.attrs['action'], data=payload, headers=ORIGIN)
        self.assertEqual((response.status_code, response.location), (303, ROOT + '/review'))
        self.assertEqual(self.row['preferences'], canonical)
        self.assertEqual(self.row['revision'], 2)
        review = self.client.get(response.location)
        self.assertEqual(review.status_code, 200)
        self.assertIn(b'Review Your Trip', review.data)
        self.assertEqual([path for method, path in self.calls if method == 'POST'],
                         ['/rest/v1/rpc/rosago_itinerary_draft_update_preferences'])
        self.protected(response)
        self.protected(review)

    def test_rendered_quiz_time_order_error_and_correction(self):
        path = ROOT + '/preferences'
        def controls(response):
            page = Document(response.get_data(as_text=True))
            target = page.find('form', action=path)[0]
            payload = MultiDict()
            for node in page.elements:
                if node.tag not in ('input', 'textarea') or target not in node.ancestors:
                    continue
                if node.attrs.get('type') in ('radio', 'checkbox') and 'checked' not in node.attrs:
                    continue
                payload.add(node.attrs['name'],
                    node.text if node.tag == 'textarea' else node.attrs['value'])
            return payload

        original = deepcopy(self.row)
        payload = controls(self.client.get(path))
        # Synthetic examples of the confirmed branch; no real submitted values.
        for end_time in ('07:59', '08:00'):
            with self.subTest(end_time=end_time):
                payload['daily_start_time'] = '08:00'
                payload['daily_end_time'] = end_time
                response = self.client.post(path, data=payload, headers=ORIGIN)
                self.assertEqual(response.status_code, 400)
                self.assertIn(b'End Time must be later than Start Time on the same day.', response.data)
                self.assertIn(b'Check AM/PM', response.data)
                self.assertNotIn(b'Check all fields:', response.data)
                self.protected(response)
                self.assertEqual(controls(response), payload)
                self.assertEqual(self.row, original)
                self.assertFalse(any(method == 'POST' for method, _ in self.calls))
        payload = controls(response)
        payload['daily_end_time'] = '17:00'
        response = self.client.post(path, data=payload, headers=ORIGIN)
        self.assertEqual((response.status_code, response.location), (303, ROOT + '/review'))
        self.assertEqual(self.row['preferences']['daily_start_time'], '08:00:00')
        self.assertEqual(self.row['preferences']['daily_end_time'], '17:00:00')
        self.assertEqual(self.row['revision'], original['revision'] + 1)
        self.assertEqual(self.client.get(response.location).status_code, 200)

    def test_rendered_selection_build_preview_and_return_with_real_services(self):
        # Production-style error handling; errors must fail HTTP assertions.
        self.app.testing = False
        original = deepcopy(self.row)
        review = self.client.get(ROOT + '/review')
        self.assertEqual(review.status_code, 200)
        recommendations = self.submit_form(review, ROOT + '/recommendations')
        self.assertEqual(recommendations.status_code, 200)
        selection = self.submit_form(recommendations, ROOT + '/selection')
        self.assertEqual(selection.status_code, 200)
        self.assertIn(b'Selection Ready', selection.data)
        self.assertIn(b'Synthetic &lt;destination&gt;', selection.data)
        self.assertEqual(self.row, original)
        build = self.submit_form(selection, ROOT + '/preview')
        self.assertEqual((build.status_code, build.location), (303, ROOT + '/preview'))
        preview = self.client.get(build.location)
        self.assertEqual(preview.status_code, 200)
        self.assertIn(b'Personalized Itinerary Preview', preview.data)
        edited = self.submit_form(preview, ROOT + '/preview/edit')
        self.assertEqual((edited.status_code, edited.location), (303, ROOT + '/recommendations'))
        returned = self.client.get(edited.location)
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(self.row, original | {'revision': 4})
        self.assertEqual([path for method, path in self.calls if method == 'POST'], [
            '/rest/v1/rpc/rosago_itinerary_draft_store_preview',
            '/rest/v1/rpc/rosago_itinerary_draft_return_to_editing'])
        for response in (review, recommendations, selection, build, preview, edited, returned):
            self.protected(response)
            for secret in (trips.OWNER, self.handle, 'private-access', 'private-refresh'):
                self.assertNotIn(secret.encode(), response.data)
