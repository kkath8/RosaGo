"""Actual Flask integration using public catalog and routing doubles only."""
from dataclasses import replace
from unittest.mock import Mock, call
import unittest

from routing_service import RoutingError, RoutingService
from places_service import PlacesUnavailableError
from test_public_layout import Document
import test_places_routes
import test_trip_routes


class RoutingRouteTests(unittest.TestCase):
    tearDown = test_places_routes.PlacesRouteTests.tearDown

    def setUp(self):
        test_places_routes.PlacesRouteTests.setUp(self)
        self.routing = Mock(spec=['configured', 'modes', 'label', 'route'])
        self.routing.configured = True
        self.routing.modes = ('driving',)
        self.routing.label = 'OSRM'
        self.routing.route.return_value = dict(
            geometry={'type': 'LineString', 'coordinates': [[121, 14], [121.1, 14.1]]},
            distance_m=1234, duration_s=567, provider='OSRM', mode='driving', estimated=True)
        self.app.extensions['rosago_routing'] = self.routing
        self.body = dict(destination_slug='synthetic-place', start_latitude=14.1,
                         start_longitude=121.1, mode='driving')

    def post(self, **changes):
        return self.client.post('/api/route', json=self.body | changes,
                                headers={'Origin': 'http://localhost'})

    def test_route_uses_current_published_destination_not_browser_end_coordinates(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, self.routing.route.return_value)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        self.service.get_published_by_slug.assert_called_once_with('synthetic-place')
        self.routing.route.assert_called_once_with(start_latitude=14.1, start_longitude=121.1,
            end_latitude=self.place.latitude, end_longitude=self.place.longitude, mode='driving')
        self.assertEqual(self.post(end_latitude=12).status_code, 400)

    def test_unlocated_and_unpublished_destinations_do_not_call_provider(self):
        self.service.get_published_by_slug.return_value = replace(self.place, latitude=None, longitude=None)
        response = self.post()
        self.assertEqual((response.status_code, response.json['error']), (422, 'missing_coordinates'))
        self.service.get_published_by_slug.return_value = None
        self.assertEqual(self.post().status_code, 404)
        self.routing.route.assert_not_called()

    def test_validation_and_origin_rejected_before_catalog_and_provider(self):
        for changes in ({'mode': 'walking'}, {'mode': 'public_transport'},
                        {'start_latitude': True}, {'start_longitude': 181},
                        {'start_latitude': '14'}, {'destination_slug': '../../secret'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.post(**changes).status_code, 400)
        for origin in ('https://foreign.invalid', 'null', None):
            headers = {'Origin': origin} if origin else {}
            self.assertEqual(self.client.post('/api/route', json=self.body, headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/api/route', data='invalid',
            headers={'Origin': 'http://localhost'}).status_code, 415)
        self.assertEqual(self.client.post('/api/route', data='{', content_type='application/json',
            headers={'Origin': 'http://localhost'}).status_code, 400)
        self.assertEqual(self.client.post('/api/route', data='x' * 5000, content_type='application/json',
            headers={'Origin': 'http://localhost'}).status_code, 400)
        self.service.get_published_by_slug.assert_not_called()
        self.routing.route.assert_not_called()

    def test_failures_return_sanitized_json_and_do_not_crash(self):
        for code, status in [('provider_timeout', 504), ('no_route', 422),
                             ('provider_unavailable', 503), ('rate_limited', 429)]:
            with self.subTest(code=code):
                self.routing.route.side_effect = RoutingError(code, 'Safe public message.', status)
                response = self.post()
                self.assertEqual((response.status_code, response.json['error']), (status, code))
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                if status == 429:
                    self.assertEqual(response.headers['Retry-After'], '1')
        self.routing.route.reset_mock()
        self.service.get_published_by_slug.side_effect = PlacesUnavailableError()
        self.assertEqual(self.post().json['error'], 'catalog_unavailable')
        self.routing.route.assert_not_called()

    def test_missing_configuration_and_secrets_are_not_rendered(self):
        self.app.extensions['rosago_routing'] = RoutingService('ors')
        self.assertEqual(self.post().status_code, 503)
        page = self.client.get('/map').get_data(as_text=True)
        self.assertIn('Route planning is temporarily unavailable', page)
        self.assertNotIn('id="route-form"', page)
        service = RoutingService('ors', ors_key='private-routing-fixture')
        self.app.extensions['rosago_routing'] = service
        page = self.client.get('/map').get_data(as_text=True)
        self.assertNotIn('private-routing-fixture', page)
        document = Document(page)
        select = document.find('select', id='route-mode')[0]
        self.assertEqual([n.attrs['value'] for n in document.find('option') if select in n.ancestors],
                         ['driving', 'walking', 'cycling'])

    def test_map_pages_beyond_fifty_and_keeps_marker_serialization(self):
        places = [replace(self.place, id=f'00000000-0000-0000-0000-{n:012d}', slug=f'place-{n}')
                  for n in range(1, 52)]
        self.service.list_published.side_effect = [tuple(places[:50]), tuple(places[50:])]
        response = self.client.get('/map')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.service.list_published.call_args_list,
                         [call(category=None, limit=50, offset=0), call(category=None, limit=50, offset=50)])
        self.assertEqual(len(self.render.call_args.kwargs['markers']), 51)


class TransportIntegrationTests(unittest.TestCase):
    def setUp(self):
        test_trip_routes.TripRouteTests.setUp(self)
        self.catalog=Mock(list_published=Mock(return_value=()))
        self.app.extensions['rosago_places']=self.catalog
    tearDown = test_trip_routes.TripRouteTests.tearDown
    seed = test_trip_routes.TripRouteTests.seed

    def test_transport_redirects_to_combined_map_and_preserves_authentication(self):
        response=self.client.get('/user/transport')
        self.assertEqual((response.status_code,response.location),(302,'/map'))
        self.catalog.list_published.assert_not_called()
        with self.client.session_transaction() as session:session.clear()
        self.assertEqual(self.client.get('/user/transport').status_code,302)
        self.assertEqual(self.client.get('/user/transport').location,'/login?login_required=1')

    def test_legacy_transport_does_not_duplicate_catalog_reads_or_error_views(self):
        self.catalog.list_published.side_effect=PlacesUnavailableError()
        response=self.client.get('/user/transport')
        self.assertEqual((response.status_code,response.location),(302,'/map'))
        self.catalog.list_published.assert_not_called()
