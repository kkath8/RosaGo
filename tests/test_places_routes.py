"""Public catalog Flask integration with fake services and network guards."""
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
import runpy
import socket
import time
import unittest
from unittest.mock import Mock, patch

from flask import before_render_template, g, render_template, url_for

from places_client import PublicPlacesClient
from places_service import (
    CATEGORIES, Place, PlacesService, PlacesValidationError,
    PlacesUnavailableError, PlacesConsistencyError,
)


class PlacesRouteTests(unittest.TestCase):
    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname',
                      'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        guard = patch.object(PublicPlacesClient, 'database_client',
                             side_effect=AssertionError('Real catalog client forbidden.'))
        self.public_client = guard.start()
        self.addCleanup(guard.stop)
        self.addCleanup(self.public_client.assert_not_called)
        self.shared = Mock()
        with (
            patch('dotenv.load_dotenv'),
            patch.dict(os.environ, SUPABASE_URL='https://fixture.invalid',
                       SUPABASE_KEY='sb_publishable_route_fixture', FLASK_SECRET_KEY='offline-route-fixture'),
            patch('supabase.create_client', return_value=self.shared) as sdk,
        ):
            namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'app.py'))
        self.assertEqual(sdk.call_count, 1)  # Existing registration initialization only.
        self.app = namespace['app']
        self.app.testing = True
        self.assertIsInstance(self.app.extensions['rosago_places'], PlacesService)
        self.service = Mock(spec_set=['list_published', 'get_published_by_slug'])
        self.app.extensions['rosago_places'] = self.service
        self.place = Place('00000000-0000-0000-0000-000000000001', 'Synthetic place',
            'synthetic-place', 'Synthetic description', 'nature', 'Synthetic address',
            14.0, 121.0, 'https://images.invalid/private-image',
            datetime(2026, 10, 11, tzinfo=timezone.utc), datetime(2026, 10, 11, tzinfo=timezone.utc))
        self.service.list_published.return_value = (self.place,)
        self.service.get_published_by_slug.return_value = self.place
        dependencies = self.app.extensions['rosago_normal_auth']
        self.original_store = dependencies.store
        self.handle = self.original_store.create(
            user_id='fixture-user', user_email='fixture@example.invalid',
            access_token='private-access-token', refresh_token='private-refresh-token',
            access_expires_at=time.time() + 3600, session_id='fixture-session')
        self.record = self.original_store.resolve(self.handle)
        self.auth_guards = []
        for obj in (dependencies.store, dependencies.coordinator, dependencies.adapters):
            for name in dir(type(obj)):
                if not name.startswith('_') and callable(getattr(obj, name, None)):
                    guard = patch.object(obj, name, side_effect=AssertionError('Auth access forbidden.'))
                    mocked = guard.start()
                    self.addCleanup(guard.stop)
                    self.addCleanup(mocked.assert_not_called)
                    self.auth_guards.append(mocked)
        self.client = self.app.test_client()
        self.render = Mock(wraps=render_template)
        guard = patch.dict(self.app.view_functions['places_list'].__globals__, render_template=self.render)
        guard.start()
        self.addCleanup(guard.stop)
        self.contexts = []
        def capture(sender, template, context, **extra):
            self.assertNotIn('auth', g)
            self.contexts.append(context.copy())
        before_render_template.connect(capture, self.app, weak=False)
        self.addCleanup(before_render_template.disconnect, capture, self.app)

    def tearDown(self):
        self.assertEqual(self.shared.mock_calls, [])
        for guard in self.auth_guards:
            guard.assert_not_called()

    def get(self, path):
        response = self.client.get(path)
        self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        return response

    def test_logged_out_list_and_exact_template_boundary(self):
        response = self.get('/places')
        self.assertEqual(response.status_code, 200)
        self.service.list_published.assert_called_once_with(category=None)
        self.render.assert_called_once_with('places/list.html', places=(self.place,),
            categories=tuple(sorted(CATEGORIES)), selected_category=None)
        self.assertIn(b'/places/synthetic-place', response.data)
        self.assertIn(b'Explore Santa Rosa', response.data)
        for key in ('client', 'token', 'provider_response', 'auth', 'service'):
            self.assertNotIn(key, self.contexts[0])

    def test_valid_stale_and_legacy_sessions_do_not_affect_either_route(self):
        for state in ({'auth_session_id': self.handle}, {'auth_session_id': 'stale-handle'},
                      {'user_id': 'legacy-user', 'user_email': 'legacy@example.invalid'}):
            with self.client.session_transaction() as session:
                session.clear()
                session.update(state)
            for path in ('/places', '/places/synthetic-place'):
                with self.subTest(state=tuple(state), path=path):
                    self.assertEqual(self.get(path).status_code, 200)
                    with self.client.session_transaction() as session:
                        self.assertEqual(dict(session), state)
        # All store methods, including touch/revoke/create/resolve, were guarded.
        self.assertEqual(self.service.list_published.call_count, 3)
        self.assertEqual(self.service.get_published_by_slug.call_count, 3)

    def test_empty_catalog_is_success(self):
        self.service.list_published.return_value = ()
        response = self.get('/places')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Places are on the way', response.data)
        self.assertIn(b'Verified place information from the Santa Rosa City Tourism Office is '
                      b'pending. Please check back later.', response.data)

    def test_empty_categories_are_success_without_claiming_catalog_is_empty(self):
        self.service.list_published.return_value = ()
        for category, label in (('attraction', 'Attractions'), ('dining', 'Dining'),
                                ('shopping', 'Shopping'), ('accommodation', 'Accommodation'),
                                ('nature', 'Nature'), ('heritage', 'Heritage')):
            with self.subTest(category=category):
                self.service.reset_mock()
                response = self.get('/places?category=' + category)
                self.assertEqual(response.status_code, 200)
                self.service.list_published.assert_called_once_with(category=category)
                self.assertIn(('No places listed in ' + label + ' yet').encode(), response.data)
                self.assertIn(b'Try another category or return to all places.', response.data)
                self.assertNotIn(b'Places are on the way', response.data)
                self.assertNotIn(b'City Tourism Office', response.data)

    def test_all_categories_pass_exactly_once(self):
        for category in CATEGORIES:
            self.service.reset_mock()
            response = self.get('/places?category=' + category)
            self.assertEqual(response.status_code, 200)
            self.service.list_published.assert_called_once_with(category=category)
            self.assertEqual(self.render.call_args.kwargs['selected_category'], category)

    def test_invalid_category_rejected_before_service(self):
        for query in ('category=', 'category=NATURE', 'category=%20nature%20',
                      'category=unsupported', 'category=nature&category=nature',
                      'category=nature&category=dining'):
            response = self.get('/places?' + query)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data, b'Invalid place category.')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.service.list_published.assert_not_called()
        self.render.assert_not_called()

    def test_unrelated_query_controls_are_ignored(self):
        response = self.get('/places?limit=999&offset=5&order=name&select=*&status=draft')
        self.assertEqual(response.status_code, 200)
        self.service.list_published.assert_called_once_with(category=None)

    def test_detail_success_exact_context_and_slug_delegation(self):
        response = self.get('/places/SYNTHETIC-PLACE')
        self.assertEqual(response.status_code, 200)
        self.service.get_published_by_slug.assert_called_once_with('SYNTHETIC-PLACE')
        self.render.assert_called_once_with('places/detail.html', place=self.place)
        self.assertIn(b'Synthetic description', response.data)

    def test_missing_detail_is_fixed_404(self):
        self.service.get_published_by_slug.return_value = None
        response = self.get('/places/missing')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, b'Place not found.')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.render.assert_not_called()

    def test_all_error_mappings_ignore_exception_messages_and_notes(self):
        for path, method, validation_status, validation_message in (
            ('/places', self.service.list_published, 400, b'Invalid place category.'),
            ('/places/invalid--slug', self.service.get_published_by_slug, 404, b'Place not found.'),
        ):
            for kind, status, message in (
                (PlacesValidationError, validation_status, validation_message),
                (PlacesUnavailableError, 503, b'Places are temporarily unavailable.'),
                (PlacesConsistencyError, 500, b'Unable to display places.'),
            ):
                error = kind()
                error.args = ('private-provider-body https://fixture.invalid private-access-token',)
                error.add_note('private-provider-note')
                method.side_effect = error
                response = self.get(path)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.data, message)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            method.side_effect = None
        self.render.assert_not_called()

    def test_post_rejected_and_endpoint_names_stable(self):
        for path in ('/places', '/places/synthetic-place'):
            response = self.client.post(path)
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        self.assertEqual(self.service.mock_calls, [])
        with self.app.test_request_context():
            self.assertEqual(url_for('places_list'), '/places')
            self.assertEqual(url_for('places_detail', slug='synthetic-place'), '/places/synthetic-place')

    def test_html_escaping_no_images_scripts_or_sensitive_data(self):
        unsafe = '<script>synthetic & text</script>'
        place = replace(self.place, name=unsafe, description=unsafe, address=unsafe)
        self.service.list_published.return_value = (place,)
        self.service.get_published_by_slug.return_value = place
        for path in ('/places', '/places/synthetic-place'):
            response = self.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'&lt;script&gt;synthetic &amp; text&lt;/script&gt;', response.data)
            for forbidden in (b'<script', b'<img', b'images.invalid', b'sb_publishable_',
                              b'private-access-token', b'private-refresh-token'):
                self.assertNotIn(forbidden, response.data)

    def test_programming_errors_are_not_relabelled(self):
        for path, method in (('/places', self.service.list_published),
                             ('/places/synthetic-place', self.service.get_published_by_slug)):
            error = RuntimeError('programming failure')
            method.side_effect = error
            with self.assertRaises(RuntimeError) as raised:
                self.get(path)
            self.assertIs(raised.exception, error)


if __name__ == '__main__':
    unittest.main()
