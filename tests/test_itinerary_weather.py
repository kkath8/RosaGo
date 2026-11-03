"""Offline policy and authenticated weather-review flows; no live provider calls."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import unittest
from unittest.mock import Mock, patch

import httpx

import test_itinerary_adjustment as adjustment
import test_itinerary_preview_routes as preview
import test_alerts_routes as alerts
import test_weather_service as weather_tests
from itinerary_weather import forecast_review, before_requested_start, STRONG_CONCERN_CODES
from settings_service import SESSION_KEY
from test_public_layout import Document
from weather_service import parse_weather

NOW = weather_tests.NOW


class WeatherPolicyTests(unittest.TestCase):
    def setUp(self):
        self.weather = parse_weather(weather_tests.weather_payload(), now=NOW)
        self.tomorrow = NOW.date() + timedelta(days=1)

    def test_quiet_forecast_has_no_concern(self):
        review = forecast_review(self.weather, (NOW.date(),), now=NOW)
        self.assertEqual(review.concerns, ())
        self.assertEqual(review.unavailable_dates, ())
        self.assertEqual(review.outside_range, ())

    def test_probability_boundary_and_rain_code_are_deterministic(self):
        base = self.weather.forecast[1]
        for probability, code, count in [(59, 0, 0), (60, 0, 1), (100, 0, 1), (0, 61, 1), (0, 51, 1)]:
            day = replace(base, precipitation_probability=probability, weather_code=code)
            weather = replace(self.weather, forecast=(self.weather.forecast[0], day, self.weather.forecast[2]))
            review = forecast_review(weather, (self.tomorrow,), now=NOW)
            self.assertEqual(len(review.concerns), count)
            if count:
                self.assertEqual(review.concerns[0].severity, 'caution')
                self.assertEqual(review.concerns[0].day, self.tomorrow)
                self.assertEqual(review.concerns[0].probability, probability)

    def test_strong_codes_take_priority_over_probability(self):
        for code in STRONG_CONCERN_CODES:
            day = replace(self.weather.forecast[1], weather_code=code, precipitation_probability=0)
            weather = replace(self.weather, forecast=(self.weather.forecast[0], day, self.weather.forecast[2]))
            review = forecast_review(weather, (self.tomorrow,), now=NOW)
            self.assertEqual(review.concerns[0].severity, 'strong')
            self.assertIn('Severe weather may affect', review.concerns[0].title)

    def test_partial_out_of_range_and_missing_forecasts_never_claim_quiet(self):
        outside = NOW.date() + timedelta(days=3)
        review = forecast_review(self.weather, (outside, self.tomorrow), now=NOW)
        self.assertEqual(review.outside_range, (outside,))
        self.assertEqual(len(review.concerns), 1)
        review = forecast_review(None, (outside, self.tomorrow), now=NOW)
        self.assertEqual(review.outside_range, (outside,))
        self.assertEqual(review.unavailable_dates, (self.tomorrow,))
        weather = replace(self.weather, forecast=(self.weather.forecast[0], self.weather.forecast[2]))
        self.assertEqual(forecast_review(weather, (self.tomorrow,), now=NOW).unavailable_dates, (self.tomorrow,))

    def test_stale_unknown_codes_and_date_mismatch_fail_safely(self):
        for changes in (dict(fetched_at=NOW-timedelta(minutes=6)), dict(reported_at=NOW-timedelta(minutes=91)),
                        dict(fetched_at=NOW+timedelta(minutes=6))):
            review = forecast_review(replace(self.weather, **changes), (self.tomorrow,), now=NOW)
            self.assertEqual(review.unavailable_dates, (self.tomorrow,))
            self.assertEqual(review.concerns, ())
        weather = replace(self.weather, forecast=(replace(self.weather.forecast[0], weather_code=4),) + self.weather.forecast[1:])
        self.assertEqual(forecast_review(weather, (NOW.date(),), now=NOW).unavailable_dates, (NOW.date(),))
        self.assertEqual(forecast_review(self.weather, (self.tomorrow,), now=NOW+timedelta(days=1)).unavailable_dates, (self.tomorrow,))

    def test_only_itinerary_dates_are_evaluated_not_current_rain(self):
        weather = replace(self.weather, weather_code=95, precipitation_mm=50)
        review = forecast_review(weather, (NOW.date()+timedelta(days=2),), now=NOW)
        self.assertEqual(review.concerns, ())


class PreviewWeatherTests(unittest.TestCase):
    tearDown = preview.PreviewRouteTests.tearDown
    seed = preview.PreviewRouteTests.seed
    assert_context = preview.PreviewRouteTests.assert_context
    read_current = preview.PreviewRouteTests.read_current
    store_preview = preview.PreviewRouteTests.store_preview
    edit_preview = preview.PreviewRouteTests.edit_preview
    ready = preview.PreviewRouteTests.ready
    save = adjustment.AdjustmentRoutes.save
    post = adjustment.AdjustmentRoutes.post

    def setUp(self):
        adjustment.AdjustmentRoutes.setUp(self)
        self.current = replace(self.current, preferences=self.current.preferences | dict(
            start_date=(NOW.date()+timedelta(days=1)).isoformat(),
            end_date=(NOW.date()+timedelta(days=2)).isoformat(), daily_start_time='08:00:00'))
        self.ready(self.places[:4])
        self.weather = Mock(get_weather=Mock(return_value=parse_weather(weather_tests.weather_payload(), now=NOW)))
        self.app.extensions['rosago_weather'] = self.weather
        guard = patch.dict(self.namespace, manila_now=lambda: NOW)
        guard.start(); self.addCleanup(guard.stop)

    def test_rain_review_uses_itinerary_date_and_never_mutates_or_calls_gemini(self):
        before = deepcopy(self.current)
        response = self.client.get(preview.PREVIEW)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Weather may affect your itinerary', response.data)
        self.assertIn(b'Oct 23, 2026', response.data)
        self.assertIn(b'Slight rain (weather code 61)', response.data)
        self.assertIn(b'70%', response.data)
        self.assertIn(b'href="#preview-days">Review Itinerary', response.data)
        self.assertIn(b'no verified destination weather-suitability', response.data)
        self.assertNotIn(b'Use Suggested Itinerary', response.data)
        self.assertNotIn(b'Review Suggested Adjustment', response.data)
        self.assertEqual(self.current, before)
        self.mutate.assert_not_called(); self.store.assert_not_called(); self.edit.assert_not_called()
        self.provider.interpret_adjustment.assert_not_called(); self.provider.explain.assert_not_called()
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_quiet_weather_has_no_weather_alert_or_proposal(self):
        snapshot = self.weather.get_weather.return_value
        self.weather.get_weather.return_value = replace(snapshot, forecast=tuple(
            replace(day, weather_code=0, precipitation_probability=0) for day in snapshot.forecast))
        response = self.client.get(preview.PREVIEW)
        self.assertNotIn(b'preview-weather-title', response.data)
        self.assertNotIn(b'Weather may affect your itinerary', response.data)
        self.assertNotIn(b'Review Suggested Adjustment', response.data)

    def test_strong_forecast_uses_stronger_nonofficial_advisory(self):
        snapshot = self.weather.get_weather.return_value
        self.weather.get_weather.return_value = replace(snapshot, forecast=tuple(
            replace(day, weather_code=95) for day in snapshot.forecast))
        response = self.client.get(preview.PREVIEW)
        self.assertIn(b'Severe weather may affect the itinerary', response.data)
        self.assertIn(b'not a destination observation or official warning', response.data)
        self.assertNotIn(b'unsafe destination', response.data)

    def test_timeout_error_and_malformed_provider_data_leave_preview_usable(self):
        for error, status, raw in [(httpx.ReadTimeout('private-secret'), 200, None),
                (None, 503, None), (None, 200, b'not-json')]:
            def factory(**options):
                def respond(request):
                    self.assertEqual(request.url.params['latitude'], '14.31222')
                    self.assertNotIn('authorization', request.headers)
                    if error:
                        raise error
                    return httpx.Response(status, content=raw) if raw else httpx.Response(status, json={})
                return httpx.Client(transport=httpx.MockTransport(respond), **options)
            from weather_service import WeatherService
            self.app.extensions['rosago_weather'] = WeatherService(http_factory=factory, now=lambda: NOW)
            before = deepcopy(self.current)
            response = self.client.get(preview.PREVIEW)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Weather is temporarily unavailable', response.data)
            self.assertEqual(len(Document(response.get_data(as_text=True)).find('article', **{'class': 'preview-stop'})), 4)
            self.assertNotIn(b'private-secret', response.data)
            self.assertEqual(self.current, before)
        self.mutate.assert_not_called()

    def test_missing_place_coordinates_use_city_forecast_without_replacements(self):
        self.places = tuple(replace(place, latitude=None, longitude=None) for place in self.places)
        self.catalog.list_published.return_value = self.places
        self.ready(self.places[:4])
        response = self.client.get(preview.PREVIEW)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Santa Rosa city forecast', response.data)
        self.assertIn(b'Rain may affect', response.data)
        self.mutate.assert_not_called()

    def test_outside_range_and_partial_coverage_are_honest(self):
        self.current = replace(self.current, preferences=self.current.preferences | dict(
            end_date=(NOW.date()+timedelta(days=4)).isoformat()))
        self.ready(self.places[:4])
        response = self.client.get(preview.PREVIEW)
        self.assertIn(b'current three-day forecast range', response.data)
        self.assertNotIn(b'No meaningful weather concern detected', response.data)

    def test_requested_start_cutoff_in_manila_not_an_invented_start_lifecycle(self):
        self.current = replace(self.current, preferences=self.current.preferences | dict(start_date=NOW.date().isoformat()))
        self.ready(self.places[:4])
        constraints = self.current.preview.plan.constraints
        start = NOW.replace(hour=8, minute=0, second=0)
        self.assertTrue(before_requested_start(constraints, start-timedelta(seconds=1)))
        self.assertFalse(before_requested_start(constraints, start))
        response = self.client.get(preview.PREVIEW)
        self.assertNotIn(b'preview-weather-title', response.data)
        self.weather.get_weather.assert_not_called()

    def test_session_preference_hides_weather_and_avoids_weather_request(self):
        with self.client.session_transaction() as session:
            session[SESSION_KEY] = {'alerts_display': 'trips'}
        response = self.client.get(preview.PREVIEW)
        self.assertNotIn(b'preview-weather-title', response.data)
        self.weather.get_weather.assert_not_called()
        with self.client.session_transaction() as session:
            session[SESSION_KEY] = {'alerts_display': 'weather'}
        self.assertIn(b'preview-weather-title', self.client.get(preview.PREVIEW).data)
        self.weather.get_weather.assert_called_once()

    def test_owner_expiry_lifecycle_and_catalog_validation_precede_weather(self):
        original = self.current
        for changes in (dict(state='saved'), dict(state='expired'),
                        dict(expires_at=NOW.replace(year=2000))):
            self.current = replace(original, **changes)
            self.assertEqual(self.client.get(preview.PREVIEW).status_code, 409)
        self.current = original
        foreign = preview.PREVIEW.replace(self.current.draft_id, '00000000-0000-0000-0000-000000000099')
        self.assertEqual(self.client.get(foreign).status_code, 404)
        self.catalog.list_published.return_value = ()
        self.assertEqual(self.client.get(preview.PREVIEW).status_code, 409)
        self.weather.get_weather.assert_not_called()
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get(preview.PREVIEW).status_code, 302)

    def test_check_preserves_explanations_and_conversation_updates_latest_revision(self):
        self.provider.explain.return_value = {'explanations': [dict(place_id=self.places[0].id, reason='Existing reason')]}
        response = self.client.post(preview.PREVIEW+'/explain', headers=preview.ORIGIN,
            data=dict(csrf_token=self.csrf, expected_revision='3'))
        self.assertIn(b'Existing reason', response.data)
        self.assertIn(b'Rain may affect', response.data)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.current.revision, 4)
        self.assertIn(b'Rain may affect', response.data)
        self.assertNotIn(b'Existing reason', response.data)
        # A weather review does not grant an old tab authority to overwrite revision 4.
        self.assertEqual(self.post(dict(csrf_token=self.csrf, expected_revision='3', message='Only one place')).status_code, 409)
        self.mutate.assert_called_once()
        self.assertEqual(self.current.revision, 4)

    def test_no_weather_accept_endpoint_and_existing_mutation_guards_remain(self):
        before = deepcopy(self.current)
        self.assertEqual(self.client.post(preview.PREVIEW+'/weather/accept', data={'revision': '3'}).status_code, 404)
        self.assertEqual(self.post(dict(csrf_token='bad', expected_revision='3', message='One place')).status_code, 403)
        self.assertEqual(self.post(headers={'Origin': 'https://foreign.invalid'}).status_code, 403)
        self.assertEqual(self.current, before)
        self.mutate.assert_not_called()


class SavedTripWeatherTests(unittest.TestCase):
    setUp = alerts.AlertsRouteTests.setUp
    tearDown = alerts.AlertsRouteTests.tearDown
    seed = alerts.AlertsRouteTests.seed

    def test_date_correlated_in_app_alert_is_escaped_and_links_to_owned_trip(self):
        self.upcoming.return_value = (replace(self.today_trip, name='<img src=x>',
                                             visit_date=NOW.date()+timedelta(days=1)),)
        response = self.client.get('/user/alerts')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Rain may affect your trip', response.data)
        self.assertIn(b'&lt;img src=x&gt;', response.data)
        self.assertIn(b'View Trip', response.data)
        self.assertEqual(Document(response.get_data(as_text=True)).find('img'), [])
        self.weather.get_weather.assert_called_once()
        self.upcoming.assert_called_once()

    def test_today_not_claimed_pretrip_and_out_of_range_is_explicit(self):
        response = self.client.get('/user/alerts')
        self.assertNotIn(b'Trip weather</h3>', response.data)
        self.upcoming.return_value = (replace(self.today_trip, visit_date=NOW.date()+timedelta(days=5)),)
        response = self.client.get('/user/alerts')
        self.assertIn(b'Forecast not available yet', response.data)
        self.assertNotIn(b'No meaningful weather concern detected', response.data)

    def test_missing_weather_does_not_hide_trip_or_fabricate_clear_forecast(self):
        self.upcoming.return_value = (replace(self.today_trip, visit_date=NOW.date()+timedelta(days=1)),)
        self.weather.get_weather.return_value = None
        response = self.client.get('/user/alerts')
        self.assertIn(b'Weather information is temporarily unavailable', response.data)
        self.assertIn(b'View Trip', response.data)
        self.assertNotIn(b'No meaningful weather concern detected', response.data)

    def test_alert_preference_remains_session_only(self):
        with self.client.session_transaction() as session:
            session[SESSION_KEY] = {'alerts_display': 'trips'}
        self.assertNotIn(b'trip-weather-title', self.client.get('/user/alerts').data)
        self.weather.get_weather.assert_not_called()
        self.upcoming.reset_mock()
        with self.client.session_transaction() as session:
            session[SESSION_KEY] = {'alerts_display': 'weather'}
        self.assertNotIn(b'trip-weather-title', self.client.get('/user/alerts').data)
        self.upcoming.assert_not_called()
