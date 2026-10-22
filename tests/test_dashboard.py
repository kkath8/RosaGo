"""Offline dashboard integration with the existing real auth coordinator."""
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from flask import before_render_template, g
from normal_auth_coordinator import SessionBusy, ClientUnavailable
from trip_service import TripUnavailableError, TripConsistencyError
from test_public_layout import Document
import test_registration


class DashboardTests(unittest.TestCase):
    def setUp(self):
        test_registration.RegistrationTests.setUp(self)
        self.dependencies = self.app.extensions['rosago_normal_auth']
        self.catalog = Mock()
        self.catalog.list_published.return_value = ()
        self.app.extensions['rosago_places'] = self.catalog
        self.closed = []
        @contextmanager
        def clients(token):
            client = Mock()
            try:
                yield client
            finally:
                client.close()
                self.closed.append(True)
        self.dependencies.coordinator._clients = clients
        self.trip = SimpleNamespace(id='aaaaaaaa-0000-0000-0000-000000000002',
                                    name='<script>My trip</script>', visit_date=date(2026, 12, 5))
        def read(auth, **kwargs):
            self.assertIs(g.auth, auth)
            self.assertEqual(auth.user_id, 'user-123')
            self.assertEqual(kwargs, dict(limit=3, offset=0))
            self.assertEqual(self.closed, [])
            return (self.trip,)
        self.reader = Mock(side_effect=read)
        guard = patch.dict(self.app.view_functions['index'].__globals__, list_user_trips=self.reader)
        guard.start()
        self.addCleanup(guard.stop)

    def page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')
        html = response.get_data(as_text=True)
        for value in ('fixture-access', 'fixture-refresh', 'fixture-session', 'user-123',
                      'access_token', 'refresh_token', 'sb_publishable_'):
            self.assertNotIn(value, html)
        return Document(html)

    def test_authenticated_trips_and_render_isolation(self):
        test_registration.seed_normal_session(self)
        observed = []
        def probe(sender, template, context, **extra):
            self.assertNotIn('auth', g)
            self.assertEqual(self.closed, [True])
            self.assertNotIn('auth', context)
            self.assertNotIn('client', context)
            observed.append(template.name)
        with before_render_template.connected_to(probe, self.app):
            page = self.page()
        self.reader.assert_called_once()
        self.assertEqual(observed, ['index.html'])
        self.assertEqual(page.find('script'), [])
        self.assertEqual(page.find('time')[0].attrs['datetime'], '2026-12-05')
        self.assertEqual(page.find('a', href='/user/trips/' + self.trip.id)[0].text, self.trip.name)
        self.assertNotIn('Sign in to view your trips', page.find('main')[0].text)

    def test_missing_date_and_empty_trips(self):
        test_registration.seed_normal_session(self)
        self.trip.visit_date = None
        self.assertIn('Date not set', self.page().find('main')[0].text)
        self.reader.side_effect = None
        self.reader.return_value = ()
        self.assertIn('You have no trips yet', self.page().find('main')[0].text)

    def test_anonymous_legacy_and_stale_sessions_do_not_read_trips(self):
        for state in ({}, {'user_id': 'user-123', 'user_email': 'fake@example.invalid'},
                      {'auth_session_id': 'stale'}, {'password_recovery_id': 'recovery-only'}):
            with self.client.session_transaction() as session:
                session.clear()
                session.update(state)
            page = self.page()
            self.assertIn('Sign in to view your trips', page.find('main')[0].text)
            self.reader.assert_not_called()
            self.assertNotIn('fake@example.invalid', page.find('body')[0].text)

    def test_auth_and_trip_failures_are_not_empty_states(self):
        test_registration.seed_normal_session(self)
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                page = self.page()
                self.assertIn('Trips are temporarily unavailable', page.find('main')[0].text)
                self.reader.assert_not_called()
        for error in (TripUnavailableError(), TripConsistencyError()):
            self.reader.side_effect = error
            text = self.page().find('main')[0].text
            self.assertIn('Trips are temporarily unavailable', text)
            self.assertNotIn('You have no trips yet', text)


if __name__ == '__main__':
    unittest.main()
