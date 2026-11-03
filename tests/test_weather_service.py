"""Open-Meteo protocol, validation and expiry tests with no external network."""
from copy import deepcopy
from datetime import datetime, timedelta
import unittest

import httpx

from weather_service import (WeatherService, WeatherValidationError, MANILA,
                             condition_label, parse_weather)

NOW = datetime(2026, 10, 22, 15, 5, tzinfo=MANILA)


def weather_payload(now=NOW):
    return {
        'latitude': 14.312, 'longitude': 121.125, 'timezone': 'Asia/Manila',
        'utc_offset_seconds': 28800,
        'current_units': {'time': 'iso8601', 'interval': 'seconds', 'temperature_2m': '°C',
                          'apparent_temperature': '°C', 'precipitation': 'mm',
                          'weather_code': 'wmo code', 'wind_speed_10m': 'km/h'},
        'daily_units': {'time': 'iso8601', 'weather_code': 'wmo code',
                        'temperature_2m_min': '°C', 'temperature_2m_max': '°C',
                        'precipitation_probability_max': '%'},
        'current': {'time': now.replace(tzinfo=None, second=0).isoformat(timespec='minutes'),
                    'interval': 900, 'temperature_2m': 29.5, 'apparent_temperature': 33.2,
                    'precipitation': 0.0, 'weather_code': 2, 'wind_speed_10m': 7.5},
        'daily': {'time': [(now.date() + timedelta(days=i)).isoformat() for i in range(3)],
                  'weather_code': [2, 61, 3], 'temperature_2m_min': [24, 25, 24],
                  'temperature_2m_max': [31, 32, 30], 'precipitation_probability_max': [20, 70, 30]},
    }


class WeatherServiceTests(unittest.TestCase):
    def make_service(self, payload=None, *, status=200, error=None, raw=None):
        self.calls, self.clients, self.options = [], [], []
        self.tick, self.now = 10.0, NOW
        self.payload = weather_payload() if payload is None else payload
        def handle(request):
            self.calls.append(request)
            if error:
                raise error
            return httpx.Response(status, content=raw) if raw is not None else httpx.Response(status, json=self.payload)
        def factory(**options):
            self.options.append(options)
            client = httpx.Client(transport=httpx.MockTransport(handle), **options)
            self.clients.append(client)
            return client
        return WeatherService(http_factory=factory, clock=lambda: self.tick, now=lambda: self.now)

    def test_valid_city_forecast_and_requested_fields_units_timezone(self):
        service = self.make_service()
        weather = service.get_weather()
        self.assertEqual(weather.temperature_c, 29.5)
        self.assertEqual(weather.apparent_c, 33.2)
        self.assertEqual(weather.condition, 'Partly cloudy')
        self.assertEqual(weather.forecast[1].precipitation_probability, 70)
        self.assertEqual(weather.reported_at.utcoffset(), timedelta(hours=8))
        self.assertEqual(len(weather.forecast), 3)
        request = self.calls[0]
        self.assertEqual((request.method, request.url.host, request.url.path),
                         ('GET', 'api.open-meteo.com', '/v1/forecast'))
        self.assertEqual(request.url.params['timezone'], 'Asia/Manila')
        self.assertEqual(request.url.params['forecast_days'], '3')
        self.assertNotIn('apikey', request.url.params)
        self.assertNotIn('authorization', request.headers)
        self.assertEqual(self.options, [dict(timeout=8, follow_redirects=False, trust_env=False)])
        self.assertTrue(self.clients[0].is_closed)

    def test_apparent_temperature_is_optional_but_core_fields_are_required(self):
        payload = weather_payload()
        payload['current'].pop('apparent_temperature')
        self.assertIsNone(parse_weather(payload, now=NOW).apparent_c)
        for section, field in [('current', 'temperature_2m'), ('current', 'precipitation'),
                               ('daily', 'temperature_2m_min'), ('daily', 'precipitation_probability_max')]:
            payload = weather_payload()
            del payload[section][field]
            self.assertIsNone(self.make_service(payload).get_weather())

    def test_timeout_network_and_provider_errors_return_unavailable(self):
        for error in (httpx.ReadTimeout('private-provider-body'), httpx.ConnectError('private-provider-body')):
            service = self.make_service(error=error)
            self.assertIsNone(service.get_weather())
            self.assertEqual(len(self.calls), 1)
            self.assertTrue(self.clients[0].is_closed)
        for status in (301, 400, 429, 500):
            self.assertIsNone(self.make_service({'reason': 'private-provider-body'}, status=status).get_weather())

    def test_malformed_or_oversized_response_is_unavailable(self):
        for raw in (b'not json', b'[]', b'null', b'"private-provider-body"', b'x' * 128001):
            self.assertIsNone(self.make_service(raw=raw).get_weather())
        self.assertIsNone(self.make_service({'error': True}).get_weather())

    def test_strict_numeric_units_dates_and_forecast_validation(self):
        patches = [
            ('current', 'temperature_2m', True), ('current', 'precipitation', -1),
            ('current', 'weather_code', True), ('current', 'weather_code', '61'),
            ('current', 'interval', 0), ('current', 'wind_speed_10m', None),
            ('current', 'time', '2026-10-22'), ('current', 'time', 'bad'),
            ('current', 'time', '2026-10-22T15:00+00:00'),
            ('current_units', 'temperature_2m', '°F'), ('daily_units', 'precipitation_probability_max', 'mm'),
            ('daily', 'temperature_2m_min', [40, 25, 24]),
            ('daily', 'weather_code', [0]), ('daily', 'temperature_2m_max', None),
            ('daily', 'precipitation_probability_max', [101, 70, 30]),
            ('daily', 'time', ['2026-10-23', '2026-10-24', '2026-10-25']),
        ]
        for section, field, value in patches:
            with self.subTest(section=section, field=field, value=value):
                payload = weather_payload()
                payload[section][field] = value
                self.assertIsNone(self.make_service(payload).get_weather())
        for field, value in [('timezone', 'UTC'), ('utc_offset_seconds', 0),
                             ('latitude', 52), ('longitude', -122)]:
            payload = weather_payload()
            payload[field] = value
            self.assertIsNone(self.make_service(payload).get_weather())
        for value in (float('nan'), float('inf'), float('-inf')):
            payload = weather_payload()
            payload['current']['temperature_2m'] = value
            with self.assertRaises(WeatherValidationError):
                parse_weather(payload, now=NOW)

    def test_code_mapping_has_truthful_unknown_fallback(self):
        for code, label in [(0, 'Clear sky'), (61, 'Slight rain'), (95, 'Thunderstorm'),
                            (99, 'Thunderstorm with heavy hail'), (4, 'Condition unavailable')]:
            self.assertEqual(condition_label(code), label)

    def test_cache_expires_and_failed_refresh_does_not_serve_stale_weather(self):
        service = self.make_service()
        first = service.get_weather()
        self.tick += 299
        self.assertIs(service.get_weather(), first)
        self.assertEqual(len(self.calls), 1)
        self.tick += 2
        self.payload = {'malformed': True}
        self.assertIsNone(service.get_weather())
        self.assertEqual(len(self.calls), 2)
        self.tick += 59
        self.assertIsNone(service.get_weather())
        self.assertEqual(len(self.calls), 2)
        self.tick += 2
        self.payload = weather_payload()
        self.assertIsNotNone(service.get_weather())
        self.assertEqual(len(self.calls), 3)

    def test_midnight_and_old_timestamps_cannot_reuse_yesterdays_forecast(self):
        service = self.make_service()
        self.assertIsNotNone(service.get_weather())
        self.now = NOW + timedelta(days=1)
        self.assertIsNone(service.get_weather())
        self.assertEqual(len(self.calls), 2)
        for hours in (-2, 1):
            payload = weather_payload()
            payload['current']['time'] = (NOW + timedelta(hours=hours)).replace(tzinfo=None).isoformat()
            self.assertIsNone(self.make_service(payload).get_weather())
