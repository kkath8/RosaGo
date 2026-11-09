"""Provider protocol, failures and secrets tested without live routing calls."""
import json
import unittest

import httpx

from routing_service import RoutingService, RoutingError, validate_request
from transport_modes import TRANSPORTATION, route_mode_for_preference


GEOMETRY = {'type': 'LineString', 'coordinates': [[121.0, 14.0], [121.01, 14.01], [121.02, 14.0]]}


def osrm_payload():
    return {'code': 'Ok', 'routes': [{'geometry': GEOMETRY, 'distance': 3456, 'duration': 789}]}


class RoutingServiceTests(unittest.TestCase):
    def service(self, *, payload=None, status=200, provider='osrm', error=None):
        self.requests, self.clients, self.options = [], [], []
        def handle(request):
            self.requests.append(request)
            if error:
                raise error
            return httpx.Response(status, json=osrm_payload() if payload is None else payload)
        def factory(**options):
            self.options.append(options)
            client = httpx.Client(transport=httpx.MockTransport(handle), **options)
            self.clients.append(client)
            return client
        return RoutingService(provider, ors_key='private-routing-fixture', http_factory=factory)

    def request(self, service, **changes):
        values = dict(start_latitude=14, start_longitude=121,
                      end_latitude=14, end_longitude=121.02, mode='driving')
        return service.route(**(values | changes))

    def test_osrm_uses_road_geometry_lon_lat_order_and_provider_estimates(self):
        service = self.service()
        result = self.request(service)
        self.assertEqual(result['geometry'], GEOMETRY)
        self.assertEqual((result['distance_m'], result['duration_s']), (3456, 789))
        self.assertTrue(result['estimated'])
        request = self.requests[0]
        self.assertEqual(request.method, 'GET')
        self.assertEqual(request.url.path, '/route/v1/driving/121.0,14.0;121.02,14.0')
        self.assertEqual(request.url.params['geometries'], 'geojson')
        self.assertNotIn('authorization', request.headers)
        self.assertEqual(self.options, [dict(timeout=12, follow_redirects=False, trust_env=False)])
        self.assertTrue(self.clients[0].is_closed)

    def test_ors_profiles_and_key_remain_server_side(self):
        for mode, profile in [('driving', 'driving-car'), ('walking', 'foot-walking'), ('cycling', 'cycling-regular')]:
            with self.subTest(mode=mode):
                payload = {'features': [{'geometry': GEOMETRY,
                                        'properties': {'summary': {'distance': 123, 'duration': 456}}}]}
                service = self.service(provider='ors', payload=payload)
                result = self.request(service, mode=mode)
                request = self.requests[0]
                self.assertEqual(request.method, 'POST')
                self.assertEqual(request.url.host, 'api.heigit.org')
                self.assertEqual(request.headers['authorization'], 'private-routing-fixture')
                self.assertEqual(request.url.path, '/openrouteservice/v2/directions/' + profile + '/geojson')
                self.assertEqual(json.loads(request.content)['coordinates'], [[121.0, 14.0], [121.02, 14.0]])
                self.assertNotIn('private-routing-fixture', json.dumps(result) + repr(service))
                self.assertTrue(self.clients[0].is_closed)

    def test_configuration_and_supported_mode_model(self):
        self.assertEqual(RoutingService.from_environment({}).modes, ('driving',))
        self.assertEqual(RoutingService.from_environment({'ORS_API_KEY': 'secret'}).modes,
                         ('driving', 'walking', 'cycling'))
        for environment in ({'ROUTING_PROVIDER': 'ors'}, {'ROUTING_PROVIDER': 'unknown'},
                            {'ORS_API_KEY': 'bad\nkey'}, {'OSRM_BASE_URL': 'http://unsafe.example'},
                            {'OSRM_BASE_URL': 'https://user:password@example.org'},
                            {'OSRM_BASE_URL': 'https://example.org?api_key=secret'}):
            with self.subTest(environment=environment):
                service = RoutingService.from_environment(environment)
                self.assertFalse(service.configured)
                self.assertEqual(service.modes, ())
        self.assertEqual(route_mode_for_preference('private_car', ('driving',)), 'driving')
        self.assertEqual(route_mode_for_preference('bicycle', ('cycling',)), 'cycling')
        self.assertIsNone(route_mode_for_preference('walking', ('driving',)))
        for preference in ('motorcycle', 'public_transport', 'ride_hailing', 'mixed_transport'):
            self.assertIn(preference, TRANSPORTATION)
            self.assertIsNone(route_mode_for_preference(preference, ('driving', 'walking', 'cycling')))

    def test_invalid_coordinates_and_modes_never_reach_provider(self):
        service = self.service()
        for changes in ({'start_latitude': None}, {'end_longitude': True}, {'start_latitude': 91},
                        {'end_longitude': float('nan')}, {'mode': 'walking'},
                        {'mode': 'public_transport'}, {'mode': []}):
            with self.subTest(changes=changes), self.assertRaises(RoutingError):
                self.request(service, **changes)
        self.assertEqual(self.requests, [])

    def test_request_fields_are_strict_and_destination_is_a_slug(self):
        valid = dict(destination_slug='santa-rosa-arch', start_latitude=14, start_longitude=121, mode='driving')
        self.assertEqual(validate_request(valid, ('driving',)), ('santa-rosa-arch', 14, 121, 'driving'))
        for data in ([], None, {}, valid | {'end_latitude': 14}, valid | {'mode': 'public_transport'},
                     valid | {'start_latitude': '14'}, valid | {'destination_slug': 'https://evil.test'}):
            with self.subTest(data=data), self.assertRaises(RoutingError):
                validate_request(data, ('driving',))

    def test_no_route_and_unsnappable_points(self):
        for payload, provider in [({'code': 'NoRoute'}, 'osrm'), ({'code': 'NoSegment'}, 'osrm'),
                                  ({'error': {'code': 2009}}, 'ors'), ({'error': {'code': 2010}}, 'ors')]:
            with self.subTest(payload=payload):
                service = self.service(payload=payload, provider=provider, status=400)
                with self.assertRaises(RoutingError) as caught:
                    self.request(service)
                self.assertEqual((caught.exception.code, caught.exception.status), ('no_route', 422))

    def test_timeout_and_provider_failures_are_sanitized(self):
        for error, code, status in [(httpx.ReadTimeout('private-routing-fixture'), 'provider_timeout', 504),
                                    (httpx.ConnectError('private-routing-fixture'), 'provider_unavailable', 503)]:
            service = self.service(error=error)
            with self.assertRaises(RoutingError) as caught:
                self.request(service)
            self.assertEqual((caught.exception.code, caught.exception.status), (code, status))
            self.assertNotIn('private-routing-fixture', str(caught.exception))
            self.assertTrue(self.clients[0].is_closed)
        for status in (301, 401, 429, 500):
            service = self.service(status=status, payload={'private': 'private-routing-fixture'})
            with self.assertRaises(RoutingError) as caught:
                self.request(service)
            self.assertEqual(caught.exception.status, 503)
            self.assertNotIn('private-routing-fixture', str(caught.exception))

    def test_malformed_geometry_and_summaries_do_not_become_routes(self):
        for patch in ({'geometry': {'type': 'Point', 'coordinates': [121, 14]}},
                      {'geometry': {'type': 'LineString', 'coordinates': [[181, 14], [121, 14]]}},
                      {'distance': -1}, {'duration': True}, {'duration': float('inf')}):
            data = osrm_payload()
            data['routes'][0].update(patch)
            service = self.service(payload=data)
            with self.subTest(patch=patch), self.assertRaises(RoutingError) as caught:
                self.request(service)
            self.assertEqual(caught.exception.status, 503)

    def test_requests_are_rate_limited_without_automatic_retries(self):
        service = self.service()
        service._clock = lambda: 10
        self.request(service)
        with self.assertRaises(RoutingError) as caught:
            self.request(service)
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(len(self.requests), 1)
