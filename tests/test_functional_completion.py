"""Offline Flask flows with real publication filtering/search/auth adapters."""
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID
import unittest
from unittest.mock import Mock, patch

from werkzeug.datastructures import MultiDict

from places_service import PlacesService, PlacesUnavailableError, PlacesConsistencyError, parse_place_row
import test_places_routes as routes
import test_places_service as catalog
import test_login as login
import test_itinerary_preview_routes as preview
import test_itinerary_quiz_routes as quiz
import test_trip_routes as trips
from test_public_layout import Document


class SearchRoutesTests(unittest.TestCase):
    tearDown = routes.PlacesRouteTests.tearDown

    def setUp(self):
        routes.PlacesRouteTests.setUp(self)
        self.rows = [self.row(1, name='Kanin Club', category='dining', address='Nuvali lakeside',
                              description='Traditional Filipino food', tourism_category='Japanese Restaurant'),
                     self.row(2, name='Old Church', category='heritage', tourism_type='Common'),
                     self.row(3, name='Hidden Japanese draft', status='draft'),
                     self.row(4, name='Hidden Japanese archive', status='archived')]
        self.queries = []
        owner = self

        class Query:
            def __init__(self):
                self.filters = []
            def select(self, fields):
                self.fields = fields.split(','); return self
            def eq(self, key, value):
                self.filters.append((key, value)); return self
            def order(self, key, desc=False):
                owner.assertEqual((key, desc), ('slug', False)); return self
            def range(self, first, last):
                self.first, self.last = first, last; return self
            def retry(self, enabled):
                owner.assertFalse(enabled); return self
            def execute(self):
                owner.assertIn(('status', 'published'), self.filters)
                rows = [r for r in owner.rows if all(r[k] == v for k, v in self.filters)]
                rows.sort(key=lambda r: r['slug'])
                return SimpleNamespace(data=[{k: r.get(k) for k in self.fields}
                    for r in rows[self.first:self.last + 1]])

        def table(name):
            self.assertEqual(name, 'places')
            query = Query(); self.queries.append(query); return query

        @contextmanager
        def clients():
            yield SimpleNamespace(table=table)
        self.app.extensions['rosago_places'] = PlacesService(clients, tourism_metadata_enabled=True)

    @staticmethod
    def row(number, **values):
        return catalog.PlacesServiceTests.row(**(dict(id=str(UUID(int=number)), slug=f'destination-{number:03}',
            status='published', tourism_type='Local', tourism_category=None,
            tourism_source='private-provenance-marker') | values))

    def search(self, query, **values):
        response = self.client.get('/places', query_string={'q': query, **values})
        self.assertEqual(response.status_code, 200)
        page = Document(response.get_data(as_text=True))
        names = [n.text.strip() for n in page.find('h2')
                 if any(a.attrs.get('class') == 'destination-card-body' for a in n.ancestors)]
        return page, names

    def test_real_service_publication_filter_and_all_search_fields(self):
        for query, expected in (('kAnIn', ['Kanin Club']), ('dining', ['Kanin Club']),
                                ('Nuvali', ['Kanin Club']), ('Filipino', ['Kanin Club']),
                                ('Japanese', ['Kanin Club']), ('heritage', ['Old Church']),
                                ('COMMON', ['Old Church']), ('Local', ['Kanin Club']),
                                ('kanin japanese', ['Kanin Club'])):
            with self.subTest(query=query):
                self.assertEqual(self.search(query)[1], expected)
        for query in ('Hidden', 'private-provenance-marker', "' OR 1=1 --", '%', '_'):
            self.assertEqual(self.search(query)[1], [])
        self.assertTrue(all(q.filters == [('status', 'published')] for q in self.queries))

    def test_search_reads_beyond_first_page_without_changing_order(self):
        self.rows = [self.row(n, name=f'Place {n}') for n in range(1, 122)]
        self.rows[-1]['name'] = 'Last-page Japanese destination'
        self.assertEqual(self.search('Japanese')[1], ['Last-page Japanese destination'])
        self.assertEqual([(q.first, q.last) for q in self.queries], [(0, 49), (50, 99), (100, 149)])

    def test_category_composes_with_search_and_clear_and_filters_preserve_state(self):
        page, names = self.search('Japanese', category='dining')
        self.assertEqual(names, ['Kanin Club'])
        links = [n for n in page.find('a') if n.text.strip() == 'Heritage']
        args = parse_qs(urlsplit(links[0].attrs['href']).query)
        self.assertEqual(args, {'category': ['heritage'], 'q': ['Japanese']})
        self.assertTrue(page.find('a', href='/places?category=dining'))
        self.assertEqual(self.search('Japanese', category='heritage')[1], [])
        form = page.find('form', role='search')[0]
        self.assertEqual(form.attrs['action'], '/places')
        self.assertTrue([n for n in page.find('input', name='category') if form in n.ancestors])

    def test_invalid_queries_never_touch_catalog_and_empty_query_uses_existing_list(self):
        for args in (MultiDict([('q', 'a'), ('q', 'b')]), {'q': 'a' * 201},
                     {'q': 'a\x00b'}, {'q': 'a\nb'}, {'q': 'x', 'category': 'invalid'}):
            self.assertEqual(self.client.get('/places', query_string=args).status_code, 400)
        self.assertEqual(self.queries, [])
        response = self.client.get('/places', query_string={'q': '   '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.queries), 1)

    def test_query_echo_is_escaped_and_no_match_has_recovery_action(self):
        response = self.client.get('/places', query_string={'q': '<script>alert(1)</script>'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'<script>alert(1)</script>', response.data)
        self.assertIn(b'&lt;script&gt;', response.data)
        self.assertIn(b'No destinations match your search', response.data)
        self.assertTrue(Document(response.get_data(as_text=True)).find('a', href='/places'))

    def test_catalog_errors_and_repeated_pages_fail_safely(self):
        service = self.app.extensions['rosago_places']
        for error, status in ((PlacesUnavailableError(), 503), (PlacesConsistencyError(), 500)):
            with patch.object(service, 'list_published', side_effect=error):
                response = self.client.get('/places?q=Japanese')
                self.assertEqual(response.status_code, status)
                self.assertNotIn(b'Traceback', response.data)
        row = self.place
        with patch.object(service, 'list_published', return_value=(row,) * 50):
            self.assertEqual(self.client.get('/places?q=x').status_code, 500)


class PlannerSelectionFlowTests(unittest.TestCase):
    setUp = preview.PreviewRouteTests.setUp
    tearDown = preview.PreviewRouteTests.tearDown
    seed = preview.PreviewRouteTests.seed
    assert_context = preview.PreviewRouteTests.assert_context
    read_current = preview.PreviewRouteTests.read_current
    store_preview = preview.PreviewRouteTests.store_preview
    edit_preview = preview.PreviewRouteTests.edit_preview

    def test_review_reaches_recommendations_selection_and_persisted_preview(self):
        self.app.extensions['rosago_weather'] = Mock(get_weather=Mock(return_value=None))
        response = self.client.get(quiz.REVIEW)
        self.assertEqual(response.status_code, 200)
        shortlist = quiz.REVIEW.replace('/review', '/recommendations')
        self.assertTrue(Document(response.get_data(as_text=True)).find('a', href=shortlist))
        response = self.client.get(shortlist)
        self.assertEqual(response.status_code, 200)
        page = Document(response.get_data(as_text=True))
        form = page.find('form', id='personalized-recommendations')[0]
        # The current recommendations screen selects destinations and submits
        # directly to Preview; no separate Selection page is required.
        self.assertEqual((form.attrs['method'], form.attrs['action']), ('post', preview.PREVIEW))
        hidden = {node.attrs['name']: node.attrs['value'] for node in page.find('input', type='hidden')
                  if form in node.ancestors}
        self.assertEqual(hidden, {'csrf_token': self.csrf, 'expected_revision': '2'})
        fields = {'csrf_token': self.csrf, 'expected_revision': '2', 'selected_place_ids': self.match.id}
        response = self.client.post(preview.PREVIEW, data=fields, headers=preview.ORIGIN)
        self.assertEqual((response.status_code, response.location), (303, preview.PREVIEW))
        self.store.assert_called_once()
        self.assertEqual(self.current.state, 'preview_ready')
        self.assertEqual(self.current.revision, 3)
        self.assertEqual(self.current.preview.source.selected_place_ids, (self.match.id,))
        response = self.client.get(response.location)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your Personalized Itinerary', response.data)
        self.store.assert_called_once()  # Refresh reads the persisted preview.


class AddToTripLoginTests(unittest.TestCase):
    setUp = login.LoginTests.setUp

    def test_signed_out_guard_login_form_and_authenticated_continuation(self):
        target = '/user/trips/add-place/kanin-club'
        response = self.client.get(target)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(parse_qs(urlsplit(response.location).query),
                         {'login_required': ['1'], 'add_place': ['kanin-club']})
        form = Document(self.client.get(response.location).get_data(as_text=True))
        self.assertTrue(form.find('input', name='add_place', value='kanin-club'))
        self.assertFalse(form.find('input', id='remember-me'))
        response = self.client.post('/login', data=self.credentials | {'add_place': 'kanin-club'})
        self.assertEqual((response.status_code, response.location), (303, target))
        with self.client.session_transaction() as session:
            self.assertEqual(set(session), {'auth_session_id'})
            record = self.store.resolve(session['auth_session_id'])
            self.assertIsNotNone(record)
        # Continue through the actual chooser, CSRF-protected add POST and trip
        # detail. Only the external catalog/storage operations are doubled.
        place = parse_place_row(catalog.PlacesServiceTests.row(slug='kanin-club', name='Kanin Club'))
        self.app.extensions['rosago_places'] = Mock(get_published_by_slug=Mock(return_value=place))
        trip = SimpleNamespace(id=str(UUID(int=900)), name='My saved trip', visit_date=None)
        detail = SimpleNamespace(trip=trip, memberships=(SimpleNamespace(place=place, position=1),),
                                 next_after_position=None)
        add = Mock()
        namespace = self.app.view_functions['trips_add_place'].__wrapped__.__globals__
        with patch.dict(namespace, list_user_trips=Mock(return_value=(trip,)),
                        add_place=add, get_user_trip=Mock(return_value=detail)):
            chooser = self.client.get(target)
            self.assertEqual(chooser.status_code, 200)
            self.assertIn(b'value="' + trip.id.encode() + b'"', chooser.data)
            add.assert_not_called()
            response = self.client.post(target, data={'csrf_token': record.csrf, 'trip_id': trip.id},
                                        headers={'Origin': 'http://localhost'})
            self.assertEqual((response.status_code, response.location), (303, '/user/trips/' + trip.id))
            add.assert_called_once()
            self.assertEqual(add.call_args.args[1:], (trip.id, place.id))
            response = self.client.get(response.location)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Kanin Club', response.data)

    def test_bad_continuations_cannot_redirect_outside_fixed_trip_route(self):
        for slug in ('https://attacker.invalid', '//attacker.invalid', '../admin',
                     'kanin?next=https://attacker.invalid', 'x' * 121, ''):
            with self.subTest(slug=slug):
                response = self.client.post('/login', data=self.credentials | {'add_place': slug})
                self.assertEqual((response.status_code, response.location), (303, '/'))
        values = MultiDict(self.credentials)
        values.add('add_place', 'kanin-club'); values.add('add_place', 'other')
        self.assertEqual(self.client.post('/login', data=values).location, '/')

    def test_failed_login_retains_destination_without_granting_authority(self):
        self.login_client.auth.sign_in_with_password.side_effect = login.AuthApiError(
            'private-provider-message', 400, 'invalid_credentials')
        response = self.client.post('/login', data=self.credentials | {'add_place': 'kanin-club'})
        self.assertEqual(response.status_code, 401)
        self.assertIn(b'name="add_place" value="kanin-club"', response.data)
        self.assertNotIn(b'private-provider-message', response.data)
        with self.client.session_transaction() as session:
            self.assertNotIn('auth_session_id', session)
