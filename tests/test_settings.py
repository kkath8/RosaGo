import test_registration
"""Browser-session settings validation and real protected-route integration."""
import unittest
from unittest.mock import Mock, patch

from flask import before_render_template, g
from werkzeug.datastructures import MultiDict

from normal_auth_coordinator import AuthenticatedContext, SessionBusy, ClientUnavailable
from settings_service import (SESSION_KEY, SettingsValidationError, get_settings, validate_settings)
from test_public_layout import Document, assert_shared_scripts
from test_weather_service import NOW, weather_payload
from weather_service import parse_weather
import test_trip_routes as trips


class SettingsValidationTests(unittest.TestCase):
    def test_default_and_supported_display_values(self):
        default = get_settings({})
        self.assertEqual(default.alerts_display, 'all')
        self.assertTrue(default.show_weather and default.show_trips)
        trips_only = validate_settings({'alerts_display': 'trips', 'personalized': True, 'location_enabled': True})
        self.assertTrue(trips_only.show_trips)
        self.assertFalse(trips_only.show_weather)
        weather_only = validate_settings({'alerts_display': 'weather'})
        self.assertTrue(weather_only.show_weather)
        self.assertFalse(weather_only.show_trips)

    def test_invalid_unsupported_and_protected_settings_rejected(self):
        for values in (None, [], {}, {'alerts_display': True}, {'alerts_display': 'unsupported'},
                       {'alerts_display': ' all '}, {'alerts_display': 'all', 'id': 'other-user'},
                       {'transportation': 'private_car'}, {'admin': True}, {'email': 'changed@example.invalid'}):
            with self.subTest(values=values), self.assertRaises(SettingsValidationError):
                validate_settings(values)
            self.assertEqual(get_settings({SESSION_KEY: values}).alerts_display, 'all')


class SettingsRouteTests(unittest.TestCase):
    tearDown = trips.TripRouteTests.tearDown
    seed = trips.TripRouteTests.seed

    def setUp(self):
        trips.TripRouteTests.setUp(self)
        self.weather = Mock(get_weather=Mock(return_value=parse_weather(weather_payload(), now=NOW)))
        self.app.extensions['rosago_weather'] = self.weather
        self.upcoming = Mock(return_value=())
        self.namespace = self.app.view_functions['settings'].__wrapped__.__globals__
        guard = patch.dict(self.namespace, list_upcoming_trips=self.upcoming, manila_now=lambda: NOW)
        guard.start()
        self.addCleanup(guard.stop)

    def post(self, choice='all', **kwargs):
        return self.client.post('/user/settings', data={'csrf_token': self.csrf, 'alerts_display': choice}, **kwargs)

    def test_authentication_stale_sessions_and_retryable_auth_failures(self):
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                self.assertEqual(self.client.get('/user/settings').status_code, 503)
                self.assertEqual(self.post().status_code, 503)
        for state in ({}, {'user_id': trips.OWNER}, {'auth_session_id': 'stale-handle'}):
            with self.client.session_transaction() as session:
                session.clear()
                session.update(state)
            self.assertEqual(self.client.get('/user/settings').status_code, 302)
            self.assertEqual(self.post().status_code, 302)
            with self.client.session_transaction() as session:
                self.assertNotIn(SESSION_KEY, session)
        self.weather.get_weather.assert_not_called()
        self.upcoming.assert_not_called()

    def test_get_existing_shell_private_headers_csrf_and_no_authority_in_jinja(self):
        def inspect(sender, template, context, **kwargs):
            self.assertNotIn('auth', g)
            self.assertFalse(any(isinstance(value, AuthenticatedContext) for value in context.values()))
        with before_render_template.connected_to(inspect, self.app):
            response = self.client.get('/user/settings')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')
        html = response.get_data(as_text=True)
        page = Document(html)
        self.assertEqual([n.text for n in page.find('h1')], ['Settings'])
        self.assertEqual(page.stack, [])
        form = page.find('form', action='/user/settings')[0]
        self.assertEqual(form.attrs['method'], 'post')
        self.assertEqual(page.find('input', name='csrf_token')[0].attrs['value'], self.csrf)
        self.assertTrue(page.find('input', name='alerts_display', value='all'))
        self.assertTrue(page.find('a', href='/help'))
        self.assertTrue(page.find('a', href='/forgot-password'))
        self.assertIn('Account-wide settings sync is not available.', html)
        for secret in ('private-access', 'private-refresh', trips.OWNER, self.handle):
            self.assertNotIn(secret, html)
        self.weather.get_weather.assert_not_called()
        self.upcoming.assert_not_called()
        self.assertEqual(self.client.put('/user/settings').status_code, 405)

    def test_valid_update_persists_in_same_browser_session_without_database_write(self):
        response = self.post('trips', headers={'Origin': 'http://localhost'})
        self.assertEqual((response.status_code, response.location), (303, '/user/settings'))
        with self.client.session_transaction() as session:
            self.assertEqual(session[SESSION_KEY], {'alerts_display': 'trips', 'personalized': True, 'location_enabled': True})
            self.assertEqual(session['auth_session_id'], self.handle)
        page = Document(self.client.get('/user/settings').get_data(as_text=True))
        self.assertTrue(page.find('input', name='alerts_display', value='trips'))
        self.assertIn('Settings updated successfully.', page.find('main')[0].text)
        self.assertEqual(self.client.get('/user/settings').status_code, 200)
        for service in self.services.values():
            service.assert_not_called()
        with self.client.session_transaction() as session:
            self.assertEqual(set(session), {'auth_session_id', SESSION_KEY})

    def test_invalid_values_duplicates_extra_identity_and_unknown_settings_do_not_mutate(self):
        self.assertEqual(self.post('trips').status_code, 303)
        for choice in ('', 'unsupported', 'ALL', ' all ', '<script>alert(1)</script>'):
            response = self.post(choice)
            self.assertEqual(response.status_code, 400)
            self.assertIn(b'Choose a supported Alerts display option.', response.data)
            assert_shared_scripts(self,Document(response.get_data(as_text=True)))
        for extra in ('id', 'user_id', 'email', 'created_at', 'role', 'transportation', 'weather_enabled'):
            response = self.client.post('/user/settings', data={'csrf_token': self.csrf,
                'alerts_display': 'weather', extra: 'other'})
            self.assertEqual(response.status_code, 400)
        duplicate = MultiDict([('csrf_token', self.csrf), ('alerts_display', 'all'), ('alerts_display', 'weather')])
        self.assertEqual(self.client.post('/user/settings', data=duplicate).status_code, 400)
        self.assertEqual(self.client.post('/user/settings', data='x' * 5000,
                         content_type='application/x-www-form-urlencoded').status_code, 400)
        with self.client.session_transaction() as session:
            self.assertEqual(session[SESSION_KEY], {'alerts_display': 'trips', 'personalized': True, 'location_enabled': True})

    def test_csrf_and_same_origin_checks_precede_changes(self):
        for data in ({}, {'csrf_token': 'bad', 'alerts_display': 'trips'},
                     MultiDict([('csrf_token', self.csrf)] * 2 + [('alerts_display', 'trips')])):
            self.assertEqual(self.client.post('/user/settings', data=data).status_code, 403)
        for origin in ('null', '', 'https://foreign.invalid', 'http://localhost.evil'):
            self.assertEqual(self.post('trips', headers={'Origin': origin}).status_code, 403)
        with self.client.session_transaction() as session:
            self.assertNotIn(SESSION_KEY, session)

    def test_trips_only_hides_weather_and_skips_weather_fetch(self):
        self.post('trips')
        response = self.client.get('/user/alerts')
        self.assertEqual(response.status_code, 200)
        page = Document(response.get_data(as_text=True))
        self.assertEqual(page.find('section', **{'aria-labelledby': 'weather-title'}), [])
        self.assertEqual(page.find('section', **{'aria-labelledby': 'weather-reminders-title'}), [])
        self.assertTrue(page.find('section', **{'aria-labelledby': 'notifications-title'}))
        self.weather.get_weather.assert_not_called()
        self.upcoming.assert_called_once()
        self.assertIn('hidden by your preferences', page.find('main')[0].text)

    def test_weather_only_hides_trip_reminders_and_skips_trip_read(self):
        self.post('weather')
        response = self.client.get('/user/alerts')
        self.assertEqual(response.status_code, 200)
        page = Document(response.get_data(as_text=True))
        self.assertTrue(page.find('section', **{'aria-labelledby': 'weather-title'}))
        self.assertEqual(page.find('section', **{'aria-labelledby': 'trip-reminders-title'}), [])
        self.upcoming.assert_not_called()
        self.weather.get_weather.assert_called_once()

    def test_default_all_restores_both_features_and_bad_cookie_is_safe(self):
        self.post('trips')
        self.post('all')
        page = Document(self.client.get('/user/alerts').get_data(as_text=True))
        self.assertTrue(page.find('section', **{'aria-labelledby': 'weather-title'}))
        self.assertTrue(page.find('section', **{'aria-labelledby': 'notifications-title'}))
        with self.client.session_transaction() as session:
            session[SESSION_KEY] = {'alerts_display': 'unsupported', 'role': 'admin'}
        page = Document(self.client.get('/user/settings').get_data(as_text=True))
        self.assertTrue(page.find('input', name='alerts_display', value='all'))

    def test_logout_clears_display_choice_and_fresh_browser_starts_without_it(self):
        self.post('weather')
        with patch.dict(self.namespace, logout_normal_session=Mock(return_value=None)):
            self.assertEqual(test_registration.post_user_logout(self).status_code, 303)
        with self.client.session_transaction() as session:
            self.assertEqual(dict(session), {})
        self.assertEqual(self.client.get('/user/settings').status_code, 302)
        fresh_client = self.app.test_client()
        with fresh_client.session_transaction() as session:
            self.assertEqual(get_settings(session).alerts_display, 'all')
