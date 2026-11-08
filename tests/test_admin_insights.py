"""Catalog-only oversight, complete reads, safe unavailable states and boundary tests."""
from dataclasses import replace
from datetime import datetime, timezone
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import admin_insights_service as insights
from admin_places_service import AdminPlace, AdminPlacesError, read_catalog, PROJECTION
from destination_weather_metadata import WeatherCatalog, validate_weather_catalog
from normal_auth_coordinator import AuthenticatedContext
import test_admin_destinations as destination_fixtures
from test_admin_destinations import record
from test_public_layout import Document


def place(n, category, status='published', tourism_type=None, hours=None, located=False):
    return AdminPlace(f'Fixture {n}', f'fixture-{n:03}', category, status, 'Fixture address',
        datetime(2026, 11, 1, tzinfo=timezone.utc), tourism_type=tourism_type,
        tourism_hours_status=hours, tourism_metadata_available=True,
        latitude=14.3 if located else None, longitude=121.1 if located else None)


class InsightCalculationTests(unittest.TestCase):
    def setUp(self):
        self.places = (place(1, 'shopping', tourism_type='Local', hours='unverified', located=True),
            place(2, 'dining', tourism_type='Common', hours='verify_required'),
            place(3, 'heritage', hours='not_supplied', located=True),
            place(4, 'shopping', status='draft', tourism_type='Local'),
            place(5, 'nature', status='archived', located=True), place(6, 'attraction'))
        rows = []
        for p, exposure in zip(self.places, ('indoor', 'covered', 'mixed', 'outdoor', 'unknown', 'unknown')):
            known = exposure != 'unknown'
            rows.append(dict(slug=p.slug, name=p.name, category=p.category, address=p.address,
                exposure=exposure, source_url='https://example.org/factual-source' if known else None,
                source_note='Test evidence' if known else None, verified_on='2026-11-01' if known else None))
        self.weather = validate_weather_catalog(dict(schema_version=1, destinations=rows))
        guard = patch.object(insights, 'load_weather_catalog', return_value=self.weather)
        guard.start()
        self.addCleanup(guard.stop)

    def summarize(self, **changes):
        args = dict(tourism_metadata_enabled=True, scope='published', issue=None, page=1)
        return insights.summarize_catalog(self.places, **(args | changes))

    def test_publication_scope_category_type_cross_counts_and_percentages(self):
        data = self.summarize()
        self.assertEqual((data['all_total'], data['total']), (6, 4))
        self.assertEqual([r.count for r in data['publication']], [4, 1, 1])
        self.assertEqual([r.count for r in data['tourism']], [1, 1, 2])
        self.assertEqual([r.percent for r in data['tourism']], [25, 25, 50])
        self.assertEqual({r.key for r in data['categories']}, {'shopping', 'dining', 'heritage', 'attraction'})
        self.assertNotIn('accommodation', {r.key for r in data['categories']})
        self.assertEqual(next(r for r in data['category_types'] if r['category'] == 'heritage')['unclassified'], 1)
        category_counts = {row.key: row.count for row in data['categories']}
        for row in data['category_types']:
            self.assertEqual(row['local'] + row['common'] + row['unclassified'], category_counts[row['category']])
        self.assertEqual(sum(row['local'] for row in data['category_types']), data['tourism'][0].count)
        self.assertEqual([r.count for r in self.summarize(scope='draft')['tourism']], [1, 0, 0])

    def test_coordinates_map_readiness_and_missing_destination_list(self):
        data = self.summarize()
        self.assertEqual((data['located'], data['missing_count'], data['map_ready']), (2, 2, 2))
        self.assertEqual([p.slug for p in data['missing_places']], ['fixture-002', 'fixture-006'])
        self.places += (replace(self.places[0], slug='rosago-test-v1-fixture'),)
        data = self.summarize(scope='all')
        self.assertEqual(data['located'], 4)  # includes archived/test coordinates
        self.assertEqual(data['map_ready'], 2)  # public map excludes both

    def test_effective_weather_all_exposures_unknown_and_identity_mismatch(self):
        data = self.summarize(scope='all')
        self.assertEqual([r.count for r in data['weather']], [1, 1, 1, 1, 2])
        self.assertEqual((data['weather_classified'], data['weather_unknown']), (4, 2))
        self.assertEqual(len(data['known_weather']), 4)
        self.places = (replace(self.places[0], address='Different identity'), *self.places[1:])
        data = self.summarize(scope='all')
        self.assertEqual([r.count for r in data['weather']], [0, 1, 1, 1, 3])

    def test_hours_null_is_separate_from_not_supplied_and_flags_are_deterministic(self):
        data = self.summarize()
        self.assertEqual([r.count for r in data['hours']], [1, 1, 1, 1])
        self.assertEqual(data['issue_counts']['hours_not_supplied'], 1)
        self.assertEqual(data['issue_counts']['hours_unset'], 1)
        only = self.summarize(issue='hours_verify_required')
        self.assertEqual([item.place.slug for item in only['attention']], ['fixture-002'])
        self.assertIn('missing_coordinates', only['attention'][0].issues)
        self.assertEqual(only['attention_matching'], 1)
        self.assertEqual(self.summarize(), self.summarize())

    def test_unavailable_curation_and_disabled_tourism_are_not_inferred(self):
        with patch.object(insights, 'load_weather_catalog', return_value=WeatherCatalog({}, 'unavailable', False)):
            data = self.summarize(tourism_metadata_enabled=False)
        for key in ('tourism', 'hours', 'category_types', 'weather', 'weather_classified', 'weather_unknown'):
            self.assertIsNone(data[key], key)
        self.assertEqual(set(data['issue_counts']), {'missing_coordinates'})
        self.assertEqual(data['missing_count'], 2)

    def test_empty_scope_zero_percent_and_bounded_attention_lists(self):
        self.places = ()
        data = self.summarize()
        self.assertEqual(data['total'], 0)
        self.assertTrue(all(r.percent == 0 for r in data['weather']))
        self.assertEqual(data['categories'], ())
        self.places = tuple(place(n, 'shopping') for n in range(31))
        data = self.summarize(page=2)
        self.assertEqual((len(data['attention']), data['attention_matching']), (10, 31))
        self.assertEqual(len(data['missing_places']), 10)
        self.assertTrue(data['attention_has_next'])


class InsightsReadTests(unittest.TestCase):
    def test_shared_complete_reader_projects_hours_once_per_page(self):
        query = Mock()
        for key in ('select', 'order', 'range', 'retry'):
            getattr(query, key).return_value = query
        client = Mock(spec=['table'])
        client.table.return_value = query
        context = AuthenticatedContext('handle', 'user', 'email', client, realm='admin')
        fields = (PROJECTION + ',tourism_type,tourism_category,tourism_hours_status').split(',')
        rows = [{key: record(n)[key] for key in fields} for n in range(205)]
        query.execute.side_effect = [SimpleNamespace(data=rows[:200], count=205),
                                     SimpleNamespace(data=rows[200:], count=205)]
        result = read_catalog(context, tourism_metadata_enabled=True, include_hours=True)
        self.assertEqual(len(result), 205)
        query.select.assert_called_with(','.join(fields), count='exact')
        self.assertEqual(query.execute.call_count, 2)
        client.table.assert_called_with('places')
        query.retry.assert_called_with(False)
        query.execute.side_effect = None
        query.execute.return_value = SimpleNamespace(data=[rows[0] | {'tourism_hours_status': 'verified'}], count=1)
        with self.assertRaises(AdminPlacesError):
            read_catalog(context, tourism_metadata_enabled=True, include_hours=True)


class InsightsRoutes(unittest.TestCase):
    setUp = destination_fixtures.DestinationReviewRoutes.setUp
    tearDown = destination_fixtures.DestinationReviewRoutes.tearDown
    protected = destination_fixtures.DestinationReviewRoutes.protected
    install_catalog = destination_fixtures.DestinationReviewRoutes.install_catalog

    def test_authentication_membership_and_no_mutation(self):
        self.protected(self.client.get('/admin/insights'), 302)
        self.install_catalog()
        self.value = False
        self.requests.clear()
        self.protected(self.client.get('/admin/insights'), 403)
        self.assertFalse(any(r.url.path.endswith('/places') for r in self.requests))
        self.protected(self.client.post('/admin/insights'), 405)

    def test_real_read_pipeline_counts_labels_links_and_active_navigation(self):
        self.install_catalog()
        response = self.client.get('/admin/insights')
        self.protected(response, 200)
        page = Document(response.get_data(as_text=True))
        self.assertEqual(page.find('h1')[0].text, 'Catalog Insights')
        self.assertTrue(page.find('a', href='/admin/insights', **{'aria-current': 'page'}))
        for text in ('Category Distribution', 'Recommendation Readiness', 'Geographic Coverage',
                     'Weather Metadata Coverage', 'Tourism Hours Status', 'Needs Attention', 'Unclassified'):
            self.assertIn(text, response.get_data(as_text=True))
        self.assertTrue(page.find('a', href='/admin/places/fixture-002'))
        self.assertTrue(page.find('a', href='/admin/places?coordinates=missing&status=published'))
        self.assertEqual(page.stack, [])
        for secret in (b'fixture-access', b'fixture-refresh', b'private@example.invalid', b'AI conversations'):
            self.assertNotIn(secret, response.data)
        for form in page.find('form'):
            self.assertIn(form.attrs.get('method'), ('get', 'post'))
            if form.attrs.get('method') == 'post':
                self.assertEqual(form.attrs['action'], '/admin/logout')

    def test_provider_failure_never_affects_insights_and_curation_unavailable_is_honest(self):
        self.install_catalog()
        with patch.object(self.app.extensions['rosago_weather'], 'get_weather', side_effect=AssertionError('No provider calls')):
            with patch.object(insights, 'load_weather_catalog', return_value=WeatherCatalog({}, 'unavailable', False)):
                response = self.client.get('/admin/insights')
        self.protected(response, 200)
        self.assertIn(b'Weather curation is unavailable', response.data)
        self.assertNotIn(b'0 unknown', response.data)
        self.assertIn(b'Category Distribution', response.data)

    def test_scopes_attention_filter_and_bad_query_rejection(self):
        self.install_catalog()
        for scope in insights.SCOPES:
            self.protected(self.client.get('/admin/insights?scope=' + scope), 200)
        response = self.client.get('/admin/insights?scope=all&issue=draft')
        self.protected(response, 200)
        section = Document(response.get_data(as_text=True)).find('section', id='needs-attention')[0]
        self.assertIn('Fixture destination 4', section.text)
        self.assertNotIn('Fixture destination 1', section.text)
        for query in ('scope=invalid', 'issue=boost', 'page=0', 'page=01', 'page=201', 'scope=all&scope=draft', 'user_id=foreign'):
            self.requests.clear()
            self.protected(self.client.get('/admin/insights?' + query), 400)
            self.assertFalse(any(r.url.path.endswith('/places') for r in self.requests))

    def test_catalog_failure_unavailable_theme_assets_and_empty_render(self):
        self.install_catalog()
        self.records = []
        response = self.client.get('/admin/insights')
        self.protected(response, 200)
        self.assertIn(b'No destinations in this scope', response.data)
        for marker in (b'css/theme.css', b'js/theme.js', b'Mobile Admin navigation'):
            self.assertIn(marker, response.data)
        self.records = [record(tourism_hours_status='not_an_enum')]
        response = self.client.get('/admin/insights')
        self.protected(response, 503)
        self.assertIn(b'No partial counts are shown', response.data)

    def test_disabled_tourism_and_attention_pagination(self):
        self.install_catalog()
        self.records = [record(n, status='published') for n in range(25)]
        response = self.client.get('/admin/insights?scope=all&issue=missing_coordinates')
        next_link = next(a for a in Document(response.get_data(as_text=True)).find('a') if a.text == 'Next page')
        self.assertIn('issue=missing_coordinates', next_link.attrs['href'])
        self.assertIn('page=2', next_link.attrs['href'])
        self.protected(self.client.get(next_link.attrs['href']), 200)
        with patch.dict(os.environ, ROSAGO_TOURISM_METADATA_ENABLED='false'):
            response = self.client.get('/admin/insights')
        self.protected(response, 200)
        self.assertIn(b'Unavailable data is not counted as unclassified', response.data)
