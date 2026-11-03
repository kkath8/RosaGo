"""Authenticated Alerts and bounded own-trip reminder reads, entirely offline."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import before_render_template, g

from normal_auth_coordinator import AuthenticatedContext
from trip_service import list_upcoming_trips, TripUnavailableError, TripConsistencyError
from weather_service import parse_weather
from test_public_layout import Document
from test_weather_service import NOW, weather_payload
import test_trip_routes as trips
import test_trip_service as trip_service_tests


class AlertsRouteTests(unittest.TestCase):
    tearDown = trips.TripRouteTests.tearDown
    seed = trips.TripRouteTests.seed

    def setUp(self):
        trips.TripRouteTests.setUp(self)
        self.weather = Mock(get_weather=Mock(return_value=parse_weather(weather_payload(), now=NOW)))
        self.app.extensions['rosago_weather'] = self.weather
        self.today_trip = replace(self.trip, visit_date=NOW.date())
        self.upcoming = Mock(return_value=(self.today_trip,))
        namespace = self.app.view_functions['alerts'].__wrapped__.__globals__
        guard = patch.dict(namespace, list_upcoming_trips=self.upcoming, manila_now=lambda: NOW)
        guard.start()
        self.addCleanup(guard.stop)

    def test_authentication_precedes_weather_and_trip_reads(self):
        for state in ({}, {'user_id': trips.OWNER}, {'auth_session_id': 'stale-handle'}):
            with self.client.session_transaction() as session:
                session.clear()
                session.update(state)
            self.assertEqual(self.client.get('/user/alerts').status_code, 302)
        self.weather.get_weather.assert_not_called()
        self.upcoming.assert_not_called()

    def test_weather_today_trip_forecast_and_private_render_boundary(self):
        contexts = []
        def inspect(sender, template, context, **kwargs):
            self.assertNotIn('auth', g)
            self.assertFalse(any(isinstance(value, AuthenticatedContext) for value in context.values()))
            contexts.append(context)
        with before_render_template.connected_to(inspect, self.app):
            response = self.client.get('/user/alerts')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')
        page = Document(response.get_data(as_text=True))
        self.assertEqual([node.text for node in page.find('h1')], ['Alerts'])
        self.assertEqual(page.stack, [])
        self.assertIn('29.5 °C', response.get_data(as_text=True))
        self.assertIn('3-Day Forecast', response.get_data(as_text=True))
        self.assertIn('Your trip is today', response.get_data(as_text=True))
        self.assertTrue(page.find('a', href='/user/trips/' + self.trip.id))
        self.assertIn('My &lt;trip&gt;', response.get_data(as_text=True))
        self.upcoming.assert_called_once()
        self.assertEqual(self.upcoming.call_args.kwargs, dict(today=NOW.date(), days=7, limit=51))
        self.assertEqual(self.upcoming.call_args.args[0].user_id, trips.OWNER)
        for secret in ('private-access', 'private-refresh', trips.OWNER, 'fixture@example.invalid'):
            self.assertNotIn(secret, response.get_data(as_text=True))
        self.assertEqual(self.client.post('/user/alerts').status_code, 405)

    def test_unavailable_weather_does_not_hide_saved_trip_reminders(self):
        self.weather.get_weather.return_value = None
        response = self.client.get('/user/alerts')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Weather information is temporarily unavailable', html)
        self.assertIn('Your trip is today', html)
        self.assertNotIn('No weather reminders for the returned forecast', html)
        self.assertNotIn('°C', html)

    def test_trip_failure_does_not_hide_weather_or_claim_no_trips(self):
        for error in (TripUnavailableError(), TripConsistencyError()):
            error.args = ('private-provider-error',)
            self.upcoming.side_effect = error
            html = self.client.get('/user/alerts').get_data(as_text=True)
            self.assertIn('Trip reminders are temporarily unavailable', html)
            self.assertIn('29.5 °C', html)
            self.assertNotIn('No saved trips are scheduled', html)
            self.assertNotIn('private-provider-error', html)

    def test_no_trips_quiet_weather_and_page_limit_are_truthful(self):
        weather = self.weather.get_weather.return_value
        self.weather.get_weather.return_value = replace(weather,
            forecast=tuple(replace(day, precipitation_probability=0) for day in weather.forecast))
        self.upcoming.return_value = ()
        html = self.client.get('/user/alerts').get_data(as_text=True)
        self.assertIn('No notifications right now.', html)
        self.assertNotIn('weather-notice',html)
        self.upcoming.return_value = tuple(replace(self.today_trip,
            id=f'00000000-0000-0000-0000-{index:012d}') for index in range(1, 52))
        page = Document(self.client.get('/user/alerts').get_data(as_text=True))
        section = page.find('section', **{'aria-labelledby': 'notifications-title'})[0]
        links = [node for node in page.find('a') if section in node.ancestors and node.text == 'View Trip']
        self.assertEqual(len(links), 50)
        self.assertIn('Showing the first 50 dated trips', section.text)


class UpcomingTripQueryTests(unittest.TestCase):
    setUp = trip_service_tests.TripServiceTests.setUp

    def query(self, rows):
        query = Mock(spec=['select', 'eq', 'gte', 'lte', 'order', 'range', 'retry', 'execute'])
        for method in ('select', 'eq', 'gte', 'lte', 'order', 'range', 'retry'):
            getattr(query, method).return_value = query
        query.execute.return_value = SimpleNamespace(data=rows)
        self.queries.append(query)
        return query

    def test_query_uses_owner_and_visit_date_window_not_creation_date(self):
        query = self.query([trip_service_tests.trip(visit_date=NOW.date().isoformat())])
        result = list_upcoming_trips(self.context, today=NOW.date())
        self.assertEqual(result[0].visit_date, NOW.date())
        query.eq.assert_called_once_with('user_id', trip_service_tests.OWNER)
        query.gte.assert_called_once_with('visit_date', '2026-10-22')
        query.lte.assert_called_once_with('visit_date', '2026-10-29')
        self.assertEqual(query.order.call_args_list[0].args, ('visit_date',))
        query.range.assert_called_once_with(0, 50)
        query.retry.assert_called_once_with(False)
        self.client.rpc.assert_not_called()

    def test_null_past_future_foreign_and_duplicate_rows_are_rejected(self):
        base = trip_service_tests.trip(visit_date=NOW.date().isoformat())
        for rows in ([base | {'visit_date': None}], [base | {'visit_date': '2026-10-21'}],
                     [base | {'visit_date': '2026-10-30'}], [base | {'user_id': trip_service_tests.OTHER}],
                     [base, base]):
            self.query(rows)
            with self.subTest(rows=rows), self.assertRaises(TripConsistencyError):
                list_upcoming_trips(self.context, today=NOW.date())
