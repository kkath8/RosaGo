"""Final UI entry points retain authentication, isolation, and truthful controls."""
import json
import unittest
from unittest.mock import Mock, patch
from flask import before_render_template, g
from normal_auth_coordinator import AuthenticatedContext
from test_public_layout import Document, NAVIGATION
import test_trip_routes as trips


class FinalUiTests(unittest.TestCase):
    tearDown = trips.TripRouteTests.tearDown
    seed = trips.TripRouteTests.seed

    def setUp(self):
        trips.TripRouteTests.setUp(self)
        self.app.extensions['rosago_weather'] = Mock(get_weather=Mock(return_value=None))
        namespace = self.app.view_functions['alerts'].__wrapped__.__globals__
        guard = patch.dict(namespace, list_upcoming_trips=Mock(return_value=()))
        guard.start()
        self.addCleanup(guard.stop)

    def test_new_pages_are_private_get_only_and_authority_isolated(self):
        self.app.extensions['rosago_places'] = Mock(list_published=Mock(return_value=()))
        seen = []
        def inspect(sender, template, context, **kwargs):
            self.assertNotIn('auth', g)
            self.assertFalse(any(isinstance(value, AuthenticatedContext) for value in context.values()))
            seen.append(template.name)
        for endpoint in ('planner', 'alerts', 'settings'):
            path = '/user/' + endpoint
            with before_render_template.connected_to(inspect, self.app):
                response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
            page = Document(response.get_data(as_text=True))
            self.assertEqual(len(page.find('h1')), 1)
            self.assertEqual(page.stack, [])
            for secret in ('private-access', 'private-refresh', trips.OWNER):
                self.assertNotIn(secret, response.get_data(as_text=True))
            active = [n for n in page.find('a') if n.attrs.get('aria-current') == 'page']
            self.assertEqual(active[0].attrs['href'], path)
            self.assertEqual(self.client.post(path).status_code, 403 if endpoint == 'settings' else 405)
        self.assertEqual(len(seen), 3)
        for service in self.services.values():
            service.assert_not_called()
        with self.client.session_transaction() as session:
            session.clear()
        for endpoint in ('planner', 'alerts', 'settings'):
            self.assertEqual(self.client.get('/user/' + endpoint).status_code, 302)

    def test_planning_modes_use_existing_actions_and_unsupported_controls_are_removed(self):
        page = Document(self.client.get('/user/planner').get_data(as_text=True))
        form = page.find('form', action='/user/itinerary/start')[0]
        self.assertEqual(form.attrs['method'], 'post')
        csrf = [n for n in page.find('input', name='csrf_token') if form in n.ancestors]
        self.assertEqual(csrf[0].attrs['value'], self.csrf)
        self.assertTrue(page.find('a', href='/user/trips/new'))
        manual = Document(self.client.get('/user/trips/new').get_data(as_text=True))
        self.assertTrue(manual.find('form', action='/user/trips'))
        self.assertFalse([n for n in manual.find('button') if 'Organize' in n.text])
        self.assertTrue(manual.find('a', href='/user/planner'))
        alerts = self.client.get('/user/alerts').get_data(as_text=True)
        alert_page = Document(alerts)
        weather = alert_page.find('section', id='weather')[0]
        self.assertIn('Weather information is temporarily unavailable.', weather.text)
        self.assertEqual(json.loads(alert_page.find('script', id='notifications-data')[0].text), [])
        self.assertEqual([node.text for node in alert_page.find('li', **{'class': 'notification-empty'})],
                         ['No notifications right now.'])
        for service in self.services.values():
            service.assert_not_called()

    def test_private_page_families_share_one_header_and_real_navigation(self):
        self.app.extensions['rosago_places'] = Mock(list_published=Mock(return_value=()))
        expected = tuple(path for label, path in NAVIGATION)
        for path in ('/user/planner', '/user/alerts',
                     '/user/settings', '/user/trips', '/user/trips/new'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                page = Document(response.get_data(as_text=True))
                self.assertEqual(len(page.find('header', **{'class': 'site-header'})), 1)
                navigation = page.find('nav', **{'class': 'site-nav'})
                self.assertEqual(len(navigation), 1)
                links = [n.attrs['href'] for n in page.find('a')
                         if navigation[0] in n.ancestors]
                self.assertEqual(tuple(links), expected)
                self.assertFalse(page.find('aside', **{'class': 'site-header'}))
