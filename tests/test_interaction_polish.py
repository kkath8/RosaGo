"""Targeted interaction contracts with real services and guarded test doubles."""
from contextlib import contextmanager
from dataclasses import asdict, replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_dashboard as dashboard
import test_places_routes as places
import test_registration as registration
import test_user_features as features
from profile_service import ProfileUnavailableError
from places_service import PlacesService
from test_public_layout import Document
from test_weather_service import NOW, weather_payload
from weather_service import parse_weather


class DashboardGreetingTests(unittest.TestCase):
    def setUp(self):
        dashboard.DashboardTests.setUp(self)
        self.reader.side_effect = None
        self.reader.return_value = ()

    def test_real_first_name_and_fallbacks(self):
        namespace = self.app.view_functions['index'].__globals__
        registration.seed_normal_session(self)
        with patch.dict(namespace, get_own_profile=Mock(return_value=SimpleNamespace(first_name='Kathleen'))):
            response = self.client.get('/')
        self.assertIn(b'Welcome, Kathleen', response.data)
        self.assertNotIn(b'Welcome, ana@', response.data)
        for profile in (None, SimpleNamespace(first_name=None), SimpleNamespace(first_name='')):
            with patch.dict(namespace, get_own_profile=Mock(return_value=profile)):
                self.assertIn(b'Welcome, Traveler', self.client.get('/').data)
        with patch.dict(namespace, get_own_profile=Mock(side_effect=ProfileUnavailableError())):
            self.assertIn(b'Welcome, Traveler', self.client.get('/').data)
        with patch.dict(namespace, get_own_profile=Mock(return_value=SimpleNamespace(first_name='<script>name</script>'))):
            output = self.client.get('/').data
            self.assertIn(b'Welcome, &lt;script&gt;name&lt;/script&gt;', output)
            self.assertNotIn(b'<script>name</script>', output)
        with self.client.session_transaction() as session:
            session.clear()
        reader = Mock(side_effect=AssertionError('Signed out must not read a profile'))
        with patch.dict(namespace, get_own_profile=reader):
            self.assertIn(b'Welcome, Traveler', self.client.get('/').data)
        reader.assert_not_called()


class ExploreInteractionTests(unittest.TestCase):
    setUp = places.PlacesRouteTests.setUp
    tearDown = places.PlacesRouteTests.tearDown
    get = places.PlacesRouteTests.get

    def real_catalog(self, extra=0):
        rows = []
        for number, category in enumerate(('dining', 'heritage', 'industrial', 'nature'), 1):
            item = replace(self.place, id=f'00000000-0000-0000-0000-{number:012x}',
                name='Santa Rosa '+category, slug=category, category=category)
            row = asdict(item)
            row.update(created_at=item.created_at.isoformat(), updated_at=item.updated_at.isoformat(), status='published')
            rows.append(row)
        rows += [dict(rows[0], id=f'00000000-0000-0000-0000-{100+n:012x}', slug=f'extra-{n}') for n in range(extra)]
        rows += [dict(rows[0], id=f'00000000-0000-0000-0000-{900+n:012x}', name=state+' hidden', slug=state, status=state)
                 for n, state in enumerate(('draft', 'archived'))]
        @contextmanager
        def factory():
            predicates, bounds = [], [0, 49]
            query = Mock()
            query.select.return_value = query
            query.order.return_value = query
            query.retry.return_value = query
            def equal(key, value):
                predicates.append((key, value))
                return query
            def page(start, end):
                bounds[:] = [start, end]
                return query
            query.eq.side_effect = equal
            query.range.side_effect = page
            query.execute.side_effect = lambda: SimpleNamespace(data=[row for row in rows
                if all(row.get(key) == value for key, value in predicates)][bounds[0]:bounds[1]+1])
            yield Mock(table=Mock(return_value=query))
        self.app.extensions['rosago_places'] = PlacesService(factory)

    def test_all_categories_search_combination_and_active_links(self):
        self.real_catalog()
        for query, expected in [('', {'dining','heritage','industrial','nature'}),
                ('?category=dining', {'dining'}), ('?category=heritage', {'heritage'}),
                ('?category=industrial', {'industrial'}), ('?q=Santa+Rosa', {'dining','heritage','industrial','nature'}),
                ('?q=heritage', {'heritage'}), ('?q=Santa+Rosa&category=heritage', {'heritage'}),
                ('?q=dining&category=heritage', set())]:
            response = self.get('/places'+query)
            self.assertEqual(response.status_code, 200)
            page = Document(response.get_data(as_text=True))
            cards = page.find('article', **{'class': 'place-card'})
            self.assertEqual({card.attrs['data-category'] for card in cards}, expected)
            self.assertNotIn(b'draft hidden', response.data)
            self.assertNotIn(b'archived hidden', response.data)
            if 'category=heritage' in query:
                nav = page.find('nav', **{'aria-label': 'Place categories'})[0]
                self.assertEqual([a.text for a in page.find('a') if nav in a.ancestors and 'aria-current' in a.attrs], ['Heritage'])
                self.assertEqual(page.find('input', name='category')[0].attrs['value'], 'heritage')
            if query == '?q=Santa+Rosa&category=heritage':
                self.assertTrue(page.find('a', href='/places?category=dining&q=Santa+Rosa'))
            self.assertNotIn('published', page.find('section', **{'class':'explore-results'})[0].text.lower())
        self.assertEqual(self.get('/places?category=forged').status_code, 400)

    def test_all_includes_catalog_beyond_first_page(self):
        self.real_catalog(extra=51)
        page = Document(self.get('/places').get_data(as_text=True))
        self.assertEqual(len(page.find('article', **{'class':'place-card'})), 55)
        self.assertIn('55 destinations', page.find('p', **{'class':'destination-result-count'})[0].text)


class DashboardWeatherApiTests(unittest.TestCase):
    setUp = features.UserFeatureTests.setUp
    tearDown = features.UserFeatureTests.tearDown
    seed = features.UserFeatureTests.seed

    def test_success_partial_and_failure_use_existing_weather_service(self):
        weather = parse_weather(weather_payload(), now=NOW)
        service = Mock(get_weather=Mock(return_value=weather))
        self.app.extensions['rosago_weather'] = service
        response = self.client.get('/api/weather')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['temperature_c'], weather.temperature_c)
        self.assertEqual(response.json['apparent_c'], weather.apparent_c)
        self.assertEqual(response.json['condition'], weather.condition)
        self.assertFalse(response.json['sample'])
        service.get_weather.return_value = replace(weather, apparent_c=None)
        self.assertIsNone(self.client.get('/api/weather').json['apparent_c'])
        service.get_weather.return_value = None
        failed = self.client.get('/api/weather')
        self.assertEqual(failed.status_code, 503)
        self.assertNotIn('temperature_c', failed.json)
        self.assertIn('temporarily unavailable', failed.json['error'])
