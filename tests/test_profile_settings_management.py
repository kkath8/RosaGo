"""Validated website configuration and safe defaults over existing fixtures."""
from dataclasses import replace
import unittest
import test_settings as settings_tests
import test_itinerary_quiz_routes as quiz
from settings_service import SESSION_KEY, validate_settings, SettingsValidationError
from test_public_layout import Document


class ManagementSettingsTests(unittest.TestCase):
    setUp=settings_tests.SettingsRouteTests.setUp
    tearDown=settings_tests.SettingsRouteTests.tearDown
    seed=settings_tests.SettingsRouteTests.seed

    def modern(self, **values):
        return self.client.post('/user/settings',headers={'Origin':'http://localhost'},data=dict(
            csrf_token=self.csrf,alerts_display='none',personalized='false',location_enabled='false')|values)

    def test_master_notifications_off_uses_existing_alerts_gate(self):
        self.assertEqual(self.modern().status_code,303)
        response=self.client.get('/user/alerts')
        self.assertEqual(response.status_code,200)
        page=Document(response.get_data(as_text=True))
        self.assertFalse(page.find('section',**{'aria-labelledby':'weather-title'}))
        self.assertFalse(page.find('section',**{'aria-labelledby':'trip-reminders-title'}))
        self.weather.get_weather.assert_not_called();self.upcoming.assert_not_called()
        with self.client.session_transaction() as session:
            self.assertEqual(session[SESSION_KEY],dict(alerts_display='none',personalized=False,location_enabled=False))

    def test_location_and_personalization_are_exposed_without_authority(self):
        self.modern(alerts_display='all')
        page=Document(self.client.get('/user/settings').get_data(as_text=True))
        body=page.find('body')[0]
        self.assertEqual(body.attrs['data-personalized'],'false')
        self.assertEqual(body.attrs['data-location-enabled'],'false')
        self.assertTrue(page.find('a',href='/forgot-password'))
        for route in ('/help','/privacy','/terms'):
            self.assertTrue(page.find('a',href=route))
        text=page.find('main')[0].text
        for unsupported in ('Traffic Alerts','Delete Account','Active Sessions','Filipino','Backup and restore'):
            self.assertNotIn(unsupported,text)
        self.assertNotIn('Travel Interests',text)

    def test_invalid_booleans_and_extra_authority_never_mutate(self):
        self.modern()
        for values in (dict(personalized='yes'),dict(location_enabled='1'),dict(email='forged@example.invalid')):
            self.assertEqual(self.modern(**values).status_code,400)
        with self.client.session_transaction() as session:
            self.assertFalse(session[SESSION_KEY]['location_enabled'])
            self.assertFalse(session[SESSION_KEY]['personalized'])
        self.assertEqual(self.modern(csrf_token='wrong').status_code,403)
        for key in ('personalized','location_enabled'):
            with self.assertRaises(SettingsValidationError):validate_settings(dict(alerts_display='all')|{key:'false'})

    def test_appearance_has_two_immediate_device_theme_actions_before_styles(self):
        page=Document(self.client.get('/user/settings').get_data(as_text=True))
        buttons=[n for n in page.find('button') if 'data-set-theme' in n.attrs]
        self.assertEqual([n.attrs['data-set-theme'] for n in buttons],['light','dark'])
        self.assertTrue(all(n.attrs['type']=='button' and 'aria-pressed' in n.attrs for n in buttons))
        self.assertNotIn('consistent light theme',page.find('main')[0].text)
        theme=page.find('script',src='/static/js/theme.js')[0]
        first_style=page.find('link',rel='stylesheet')[0]
        self.assertLess(page.elements.index(theme),page.elements.index(first_style))
        self.assertNotIn('defer',theme.attrs)

    def test_legacy_alert_update_preserves_other_settings(self):
        self.modern()
        self.client.post('/user/settings',data=dict(csrf_token=self.csrf,alerts_display='weather'))
        with self.client.session_transaction() as session:
            self.assertEqual(session[SESSION_KEY],dict(alerts_display='weather',personalized=False,location_enabled=False))


class PlannerDefaultBoundaryTests(unittest.TestCase):
    setUp=quiz.QuizRouteTests.setUp
    tearDown=quiz.QuizRouteTests.tearDown
    seed=quiz.QuizRouteTests.seed
    protected=quiz.QuizRouteTests.protected

    def test_only_new_empty_draft_is_eligible_for_automatic_defaults(self):
        reader=self.drafts['get_itinerary_draft'];reader.side_effect=None
        reader.return_value=replace(self.draft,preferences=None)
        fresh=self.client.get(quiz.QUIZ)
        self.assertIn(b'data-profile-defaults-eligible="true"',fresh.data)
        reader.return_value=self.draft
        existing=self.client.get(quiz.QUIZ)
        self.assertIn(b'data-profile-defaults-eligible="false"',existing.data)
        self.drafts['update_itinerary_draft_preferences'].assert_not_called()

    def test_personalization_off_does_not_disable_manual_planning(self):
        with self.client.session_transaction() as session:
            session[SESSION_KEY]=dict(alerts_display='all',personalized=False,location_enabled=True)
        response=self.client.get(quiz.QUIZ)
        page=Document(response.get_data(as_text=True))
        self.assertEqual(page.find('body')[0].attrs['data-personalized'],'false')
        self.assertTrue(page.find('form',**{'class':'itinerary-form'}))
        self.assertTrue(any('data-apply-profile-defaults' in n.attrs and 'disabled' in n.attrs for n in page.find('button')))
