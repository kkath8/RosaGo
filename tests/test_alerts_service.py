"""Deterministic reminder boundaries using synthetic weather and saved trips."""
from dataclasses import replace
from datetime import timedelta
import unittest

from alerts_service import weather_alerts, trip_alerts
from trip_service import Trip
from weather_service import parse_weather
from test_weather_service import weather_payload, NOW


class AlertsServiceTests(unittest.TestCase):
    def weather(self):
        return parse_weather(weather_payload(), now=NOW)

    def test_forecast_probability_threshold_and_severity(self):
        weather = self.weather()
        forecast = tuple(replace(day, precipitation_probability=probability)
                         for day, probability in zip(weather.forecast, (59, 60, 100)))
        alerts = weather_alerts(replace(weather, forecast=forecast))
        self.assertEqual(len(alerts), 2)
        self.assertTrue(all(alert.kind == 'weather' and alert.severity == 'caution' for alert in alerts))
        self.assertIn('60%', alerts[0].message)
        self.assertEqual(alerts[0].day, NOW.date() + timedelta(days=1))

    def test_reported_precipitation_and_rain_code_are_not_official_warnings(self):
        weather = self.weather()
        for changes in (dict(precipitation_mm=0.2), dict(weather_code=61), dict(weather_code=95)):
            with self.subTest(changes=changes):
                alerts = weather_alerts(replace(weather, **changes))
                self.assertEqual(alerts[0].severity, 'caution')
                self.assertIn('Open-Meteo', alerts[0].message)
                self.assertNotIn('warning', alerts[0].message.lower())
        alerts = weather_alerts(replace(weather, precipitation_mm=1, weather_code=61))
        self.assertEqual(sum('current' in a.title.lower() or 'reported' in a.title.lower() for a in alerts), 1)
        self.assertIn('15-minute interval', alerts[0].message)

    def test_no_alert_weather_and_unavailable_weather(self):
        weather = self.weather()
        forecast = tuple(replace(day, precipitation_probability=0) for day in weather.forecast)
        self.assertEqual(weather_alerts(replace(weather, weather_code=0, precipitation_mm=0, forecast=forecast)), ())
        self.assertEqual(weather_alerts(None), ())

    def test_today_upcoming_past_undated_and_outside_window(self):
        def trip(number, delta):
            return Trip(f'00000000-0000-0000-0000-{number:012d}', f'Trip {number}',
                        None if delta is None else NOW.date() + timedelta(days=delta), NOW, NOW)
        trips = [trip(1, -1), trip(2, None), trip(3, 8), trip(4, 7), trip(5, 0), trip(6, 1)]
        alerts = trip_alerts(trips, today=NOW.date())
        self.assertEqual([a.title for a in alerts], ['Your trip is today', 'Upcoming saved trip', 'Upcoming saved trip'])
        self.assertEqual([a.trip_id for a in alerts], [trips[4].id, trips[5].id, trips[3].id])
        self.assertTrue(all(a.kind == 'trip' and a.severity == 'info' for a in alerts))
        self.assertEqual(trip_alerts([], today=NOW.date()), ())
