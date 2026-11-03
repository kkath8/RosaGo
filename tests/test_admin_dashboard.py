"""Complete catalog health and the protected Admin dashboard presentation."""
from inspect import unwrap
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
import admin_dashboard_service as dashboard
from admin_places_service import AdminPlacesError
from destination_weather_metadata import WeatherCatalog, load_weather_catalog
from normal_auth_coordinator import AuthenticatedContext
import test_admin_authorization as foundation
import test_registration
from test_public_layout import Document


def health_row(n=1, **changes):
    return dict(slug=f'destination-{n:04}', name=f'Destination {n}', category='shopping',
                address='Fixture address', latitude=None, longitude=None, tourism_type=None) | changes


class CatalogHealthTests(unittest.TestCase):
    def setUp(self):
        self.query = Mock()
        for method in ('select', 'eq', 'order', 'range', 'retry'):
            getattr(self.query, method).return_value = self.query
        self.client = Mock(spec=['table'])
        self.client.table.return_value = self.query
        self.context = AuthenticatedContext('handle', 'user', 'private@example.invalid', self.client)

    def read(self, rows, **kwargs):
        self.query.execute.return_value = SimpleNamespace(count=len(rows), data=rows)
        return dashboard.published_catalog_health(self.context, tourism_metadata_enabled=True, **kwargs)

    def test_actual_types_null_coordinates_and_effective_weather_identity(self):
        known = next((slug, record) for slug, record in load_weather_catalog().records.items()
                     if record[3].exposure != 'unknown')
        slug, (name, category, address, _) = known
        rows = [health_row(1, tourism_type='Local', latitude=14.3, longitude=121.1),
                health_row(2, tourism_type='Common'), health_row(3),
                health_row(4, slug=slug, name=name, category=category, address=address)]
        result = self.read(rows)
        self.assertEqual(result, dashboard.CatalogHealth(4, 1, 3, 1, 1, 2, 1, 3))
        rows[-1]['address'] = 'Changed identity'
        self.assertEqual(self.read(rows).weather_classified, 0)
        self.query.select.assert_called_with(dashboard.HEALTH_PROJECTION + ',tourism_type', count='exact')
        self.query.eq.assert_called_with('status', 'published')
        self.query.retry.assert_called_with(False)
        self.client.table.assert_called_with('places')

    def test_disabled_tourism_is_not_counted_as_unclassified(self):
        row = health_row()
        del row['tourism_type']
        self.query.execute.return_value = SimpleNamespace(count=1, data=[row])
        result = dashboard.published_catalog_health(self.context)
        self.assertIsNone(result.local)
        self.assertIsNone(result.common)
        self.assertIsNone(result.unclassified)
        self.assertEqual(result.missing_coordinates, 1)
        self.query.select.assert_called_with(dashboard.HEALTH_PROJECTION, count='exact')

    def test_complete_catalog_over_100_candidates_and_multiple_pages(self):
        rows = [health_row(n, tourism_type='Local') for n in range(205)]
        self.query.execute.side_effect = [SimpleNamespace(count=205, data=rows[:200]),
                                          SimpleNamespace(count=205, data=rows[200:])]
        result = dashboard.published_catalog_health(self.context, tourism_metadata_enabled=True)
        self.assertEqual((result.published, result.local), (205, 205))
        self.assertEqual([call.args for call in self.query.range.call_args_list], [(0, 199), (200, 399)])

    def test_truncation_duplicate_rows_changed_count_and_ceiling_are_unavailable(self):
        rows = [health_row(n) for n in range(200)]
        cases = [[SimpleNamespace(count=2, data=[rows[0]])],
                 [SimpleNamespace(count=2001, data=[])],
                 [SimpleNamespace(count=2, data=[rows[0], rows[0]])],
                 [SimpleNamespace(count=201, data=rows), SimpleNamespace(count=202, data=[health_row(201)])]]
        for responses in cases:
            with self.subTest(responses=len(responses)):
                self.query.execute.side_effect = responses
                with self.assertRaises(AdminPlacesError):
                    dashboard.published_catalog_health(self.context, tourism_metadata_enabled=True)

    def test_invalid_response_values_fail_closed(self):
        for changes in ({'latitude': 14}, {'latitude': True, 'longitude': 121},
                        {'latitude': float('nan'), 'longitude': 121}, {'latitude': 91, 'longitude': 121},
                        {'tourism_type': 'local'}, {'tourism_type': []}, {'category': []},
                        {'slug': 'INVALID'}, {'name': ''}, {'extra': 'private'}):
            with self.subTest(changes=changes), self.assertRaises(AdminPlacesError):
                self.read([health_row(**changes)])
        for count in (True, -1, None, '1'):
            self.query.execute.return_value = SimpleNamespace(count=count, data=[])
            with self.assertRaises(AdminPlacesError):
                dashboard.published_catalog_health(self.context)

    def test_zero_is_valid_and_broken_weather_is_unavailable_not_zero(self):
        result = self.read([])
        self.assertEqual((result.published, result.with_coordinates, result.local), (0, 0, 0))
        with patch.object(dashboard, 'load_weather_catalog', return_value=WeatherCatalog({}, 'unavailable', False)):
            result = self.read([health_row()])
        self.assertIsNone(result.weather_classified)
        self.assertIsNone(result.weather_unknown)


class DashboardRouteTests(unittest.TestCase):
    setUp = foundation.AdminBoundaryTests.setUp
    tearDown = foundation.AdminBoundaryTests.tearDown
    protected = foundation.AdminBoundaryTests.protected

    def install_catalog(self):
        test_registration.seed_normal_session(self)
        self.value = True
        self.records = [health_row(1, tourism_type='Local', latitude=14.3, longitude=121.1),
                        health_row(2, tourism_type='Common'), health_row(3)]

        def respond(request):
            self.requests.append(request)
            self.assertEqual(request.headers['authorization'], 'Bearer fixture-access')
            if request.url.path.endswith('/rosago_is_admin'):
                return httpx.Response(200, json=self.value)
            if request.url.path.endswith('/rosago_admin_operational_overview'):
                return httpx.Response(503, json={'message':'Unavailable'})
            self.assertEqual(request.url.path, '/rest/v1/places')
            if request.method == 'HEAD':
                counts = {None: 6, 'eq.published': 3, 'eq.draft': 2, 'eq.archived': 1}
                return httpx.Response(200, headers={'Content-Range': f"*/{counts[request.url.params.get('status')]}"})
            self.assertEqual(request.method, 'GET')
            projection = request.url.params['select'].split(',')
            return httpx.Response(200, json=[{k: (row[k] if k in row else {'status':'published','updated_at':'2026-10-20T04:00:00Z','tourism_category':None,'tourism_hours_status':None}[k]) for k in projection} for row in self.records],
                                  headers={'Content-Range': '0-2/3'})
        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
            self.clients.append(client)
            return client
        self.dependencies.adapters._http_factory = factory

    def test_real_read_pipeline_metrics_and_safe_navigation(self):
        self.install_catalog()
        with patch.dict(os.environ, ROSAGO_TOURISM_METADATA_ENABLED='true'):
            response = self.client.get('/admin')
        self.protected(response, 200)
        page = Document(response.get_data(as_text=True))
        self.assertEqual([p.text for p in page.find('p', **{'class': 'metric-value'})], ['3', '2', '1', '6'])
        for text in (b'1 / 3', b'2 missing coordinates', b'1 Local', b'1 Common', b'1 not assigned', b'0 classified', b'3 unknown'):
            self.assertIn(text, response.data)
        self.assertTrue(page.find('a', href='/admin', **{'aria-current': 'page'}))
        self.assertTrue(page.find('a', href='/admin/places?status=draft'))
        self.assertTrue(page.find('a', href='/admin/system'))
        self.assertTrue(page.find('form', action='/admin/logout'))
        self.assertEqual(page.stack, [])
        for forbidden in (b'Recent Activity', b'Registered users', b'Saved trips', b'Planner', b'AI Assistant',
                          b'personal-state.js', b'private@example.invalid', b'/admin/analytics'):
            self.assertNotIn(forbidden, response.data)

    def test_theme_assets_and_mobile_navigation_share_existing_theme(self):
        self.install_catalog()
        response = self.client.get('/admin')
        for asset in (b'css/design-tokens.css', b'css/theme.css', b'js/theme.js', b'css/admin.css', b'js/admin.js'):
            self.assertIn(asset, response.data)
        for marker in (b'fonts.googleapis.com/css2?family=Inter', b'Mobile Admin navigation',
                       b'data-set-theme="light"', b'data-set-theme="dark"', b'Admin account'):
            self.assertIn(marker, response.data)

    def test_disabled_tourism_is_explicit_and_dashboard_never_fetches_weather(self):
        self.install_catalog()
        with patch.dict(os.environ, ROSAGO_TOURISM_METADATA_ENABLED='false'), patch.object(
                self.app.extensions['rosago_weather'], 'get_weather', side_effect=AssertionError('Unexpected provider call')):
            response = self.client.get('/admin')
        self.protected(response, 200)
        self.assertIn(b'Tourism data is not enabled', response.data)
        self.assertNotIn(b'class="metric metric-local"', response.data)
        self.assertNotIn(b'0 not assigned', response.data)

    def test_missing_health_does_not_erase_status_counts(self):
        self.install_catalog()
        namespace = unwrap(self.app.view_functions['admin.index']).__globals__
        with patch.dict(namespace, published_catalog_health=Mock(side_effect=AdminPlacesError())):
            response = self.client.get('/admin')
        self.protected(response, 200)
        self.assertIn(b'Catalog health is temporarily unavailable', response.data)
        self.assertIn(b'class="metric-value">3', response.data)

    def test_nonmember_never_reads_dashboard_catalog(self):
        self.install_catalog()
        self.value = False
        self.protected(self.client.get('/admin'), 403)
        self.assertFalse(any(request.url.path.endswith('/places') for request in self.requests))
