"""Public catalog Flask integration with fake services and network guards."""
from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import runpy
import socket
import time
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from flask import before_render_template, g, render_template, url_for

from places_client import PublicPlacesClient
from destination_weather_metadata import UNKNOWN, WeatherMetadata
from test_public_layout import Document, assert_shared_scripts
from test_tourism_weather_identity import current_catalog_rows, catalog_place
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
            14.0, 121.0, None,
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
        self.service.list_published.assert_called_once_with(category=None, limit=50, offset=0)
        self.render.assert_called_once_with('places/list.html', places=(self.place,),
            categories=tuple(sorted(CATEGORIES)), selected_category=None)
        self.assertIn(b'/places/synthetic-place', response.data)
        self.assertIn(b'Explore Santa Rosa', response.data)
        for key in ('client', 'token', 'provider_response', 'auth', 'service'):
            self.assertNotIn(key, self.contexts[0])

    def test_tourism_metadata_detail_is_escaped_cautious_and_hides_provenance(self):
        from dataclasses import replace
        self.service.get_published_by_slug.return_value = replace(self.place,
            tourism_type='Local', tourism_category='Museum <script>unsafe</script>',
            tourism_opening_hours_raw='11:00 AM*', tourism_closing_hours_raw='Verify',
            tourism_hours_status='verify_required', tourism_source='internal-source-marker',
            tourism_source_row=987654, latitude=None, longitude=None)
        response = self.get('/places/synthetic-place')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        for text in ('Tourism Information', '<td>Local</td>', 'Museum &lt;script&gt;unsafe&lt;/script&gt;',
                     'Operating hours require verification.'):
            self.assertIn(text, body)
        for text in ('<script>unsafe</script>', 'internal-source-marker', '987654', 'verify_required',
                     'Opening Hours', 'Closing Hours', '>Verify<'):
            self.assertNotIn(text, body)

    def test_common_type_and_legacy_null_metadata_render_without_coordinates(self):
        from dataclasses import replace
        for classification in (None, 'Common'):
            item = replace(self.place, latitude=None, longitude=None, tourism_type=classification)
            self.service.list_published.return_value = (item,)
            self.service.get_published_by_slug.return_value = item
            listing = self.get('/places')
            detail = self.get('/places/synthetic-place')
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(detail.status_code, 200)
            self.assertIn(b'Synthetic place', listing.data)
            if classification:
                self.assertIn(b'<td>Common</td>', detail.data)
            else:
                self.assertNotIn(b'City Tourism category:', detail.data)
                self.assertNotIn(b'Hours provided by City Tourism', detail.data)

    def test_compact_tourism_cards_preserve_application_categories(self):
        for classification, category, source_category, label in (
                ('Local', 'attraction', 'Theme Park / Recreation', 'Attractions'),
                ('Common', 'dining', 'Filipino Restaurant', 'Dining')):
            item = replace(self.place, category=category, tourism_type=classification,
                           tourism_category=source_category)
            self.service.list_published.return_value = (item,)
            page = Document(self.get('/places').get_data(as_text=True))
            self.assertEqual(page.find('p', **{'class': 'place-category'})[0].text, label)
            self.assertEqual(page.find('p', **{'class': 'destination-tourism-summary'})[0].text,
                             classification + ' · ' + source_category)
        self.service.list_published.return_value = (replace(self.place, tourism_category='Museum <script>x</script>'),)
        body = self.get('/places').get_data(as_text=True)
        self.assertIn('Museum &lt;script&gt;x&lt;/script&gt;', body)
        self.assertNotIn('<script>x</script>', body)
        self.assertNotIn('Local', Document(body).find('p', **{'class': 'destination-tourism-summary'})[0].text)
        self.assertNotIn('Common', Document(body).find('p', **{'class': 'destination-tourism-summary'})[0].text)

    def test_hours_states_and_legacy_null_hours_are_cautious(self):
        for state, opening, closing, expected in (
                ('unverified', '11:00 AM*', '12:00 AM*', 'Hours provided by City Tourism; verification recommended.'),
                ('verify_required', 'Verify', 'Verify', 'Operating hours require verification.'),
                ('not_supplied', None, None, 'Operating hours not supplied.'),
                (None, '11:00 AM*', None, 'Hours provided by City Tourism; verification recommended.')):
            item = replace(self.place, tourism_type='Local', tourism_opening_hours_raw=opening,
                           tourism_closing_hours_raw=closing, tourism_hours_status=state)
            self.service.get_published_by_slug.return_value = item
            body = self.get('/places/synthetic-place').get_data(as_text=True)
            self.assertIn(expected, body)
            if state in ('unverified', None):
                self.assertIn('Opening Hours</th><td>11:00 AM*', body)
                if closing:
                    self.assertIn('Closing Hours</th><td>12:00 AM*', body)
            else:
                self.assertNotIn('Opening Hours', body)
                self.assertNotIn('Closing Hours', body)
            self.assertEqual(item.tourism_opening_hours_raw, opening)
            self.assertEqual(item.tourism_closing_hours_raw, closing)
        self.service.get_published_by_slug.return_value = replace(self.place, tourism_type='Local')
        body = self.get('/places/synthetic-place').get_data(as_text=True)
        self.assertIn('Tourism Information', body)
        self.assertNotIn('Operating Hours', body)

    def test_current_curated_weather_is_visitor_facing_and_hides_all_provenance(self):
        expected = {'enchanted-kingdom': 'Mix of indoor/covered and outdoor areas',
                    'sm-city-santa-rosa': 'Primarily indoor', 'robinson-s-santa-rosa': 'Primarily indoor'}
        for row in current_catalog_rows():
            if row['slug'] not in expected:
                continue
            self.service.get_published_by_slug.return_value = catalog_place(row)
            body = self.get('/places/' + row['slug']).get_data(as_text=True)
            self.assertIn('Weather setting</th><td>' + expected[row['slug']], body)
            for internal in ('Curated weather exposure', 'source_note', 'source_url', 'verified_on',
                             'RosaGo-curated', '2026-10-26', 'enchantedkingdom.ph',
                             'smsupermalls.com', 'robinsonsmalls.com', 'fingerprint'):
                self.assertNotIn(internal, body)

    def test_unknown_weather_hidden_and_remaining_verified_labels_are_safe(self):
        body = self.get('/places/synthetic-place').get_data(as_text=True)
        self.assertNotIn('Weather setting', body)
        self.assertNotIn('Curated weather exposure', body)
        for exposure, label in (('covered', 'Mostly covered'), ('outdoor', 'Primarily outdoor')):
            metadata = WeatherMetadata(exposure, 'https://fixture.invalid/private-evidence',
                                       'Private research marker', '2026-10-26')
            with patch.dict(self.app.view_functions['places_detail'].__globals__,
                            load_weather_catalog=lambda: Mock(for_place=Mock(return_value=metadata))):
                body = self.get('/places/synthetic-place').get_data(as_text=True)
            self.assertIn('Weather setting</th><td>' + label, body)
            for private in ('Private research marker', 'private-evidence', '2026-10-26'):
                self.assertNotIn(private, body)

    def test_map_link_requires_both_coordinates_including_valid_zero_values(self):
        for latitude, longitude, visible in ((None, None, False), (None, 121.0, False),
                                             (14.0, None, False), (14.0, 121.0, True), (0.0, 0.0, True)):
            self.service.get_published_by_slug.return_value = replace(self.place, latitude=latitude, longitude=longitude)
            body = self.get('/places/synthetic-place').get_data(as_text=True)
            self.assertEqual('Open Map' in body, visible)
            self.assertEqual(bool([link for link in Document(body).find('a', href='/map?destination=synthetic-place')
                                   if link.text == 'Open Map']), visible)

    def test_rosago_only_places_have_no_invented_tourism_or_weather_information(self):
        examples = {'arambulo-ancestral-house', 'city-auditorium',
                    'city-of-santa-rosa-multi-purpose-complex', 'toyota-santa-rosa'}
        for row in current_catalog_rows():
            if row['slug'] not in examples:
                continue
            item = catalog_place(row)
            self.service.list_published.return_value = (item,)
            self.service.get_published_by_slug.return_value = item
            listing = self.get('/places').get_data(as_text=True)
            detail = self.get('/places/' + item.slug).get_data(as_text=True)
            self.assertIn(item.name, listing)
            self.assertIn(item.name, detail)
            self.assertFalse(Document(listing).find('p', **{'class': 'destination-tourism-summary'}))
            for text in ('Tourism Information', 'Operating Hours', 'Weather setting'):
                self.assertNotIn(text, detail)

    def test_real_service_filters_both_drafts_out_of_explore_and_details(self):
        rows = [dict(image_url=None, created_at='2026-10-26T00:00:00Z', updated_at='2026-10-26T00:00:00Z',
                     status='published') | r for r in current_catalog_rows()]
        rows.extend(dict(rows[0], id=f'99999999-0000-0000-0000-{n:012x}',
                         slug=f'rosago-test-v1-old-{n}', name=f'RosaGo Test archived {n}', status='archived')
                    for n in range(1, 13))
        query = Mock()
        for method in ('select', 'eq', 'order', 'range', 'retry', 'limit'):
            getattr(query, method).return_value = query
        def execute():
            selected = rows
            for predicate in query.eq.call_args_list:
                field, value = predicate.args
                selected = [r for r in selected if r[field] == value]
            return SimpleNamespace(data=selected)
        query.execute.side_effect = execute
        @contextmanager
        def factory():
            yield Mock(table=Mock(return_value=query))
        self.app.extensions['rosago_places'] = PlacesService(factory, tourism_metadata_enabled=True)
        body = self.get('/places').get_data(as_text=True)
        self.assertEqual(len(Document(body).find('article', **{'class': 'place-card'})), 34)
        for name in ("City of Santa Rosa People's Park", 'Centennial Garden'):
            self.assertNotIn(name, body)
        self.assertNotIn('RosaGo Test archived', body)
        for slug in ('city-of-santa-rosa-peoples-park', 'centennial-garden',
                     *(f'rosago-test-v1-old-{n}' for n in range(1, 13))):
            query.reset_mock()
            self.assertEqual(self.get('/places/' + slug).status_code, 404)
            if slug.startswith('rosago-test-v1-'):
                query.execute.assert_not_called()
            else:
                self.assertIn(('status', 'published'), [c.args for c in query.eq.call_args_list])
        query.reset_mock()
        dining = self.get('/places?category=dining').get_data(as_text=True)
        self.assertIn('Kanin Club', dining)
        self.assertIn('Common', dining)
        self.assertIn('Filipino Restaurant', dining)
        self.assertEqual(len(Document(dining).find('article', **{'class': 'place-card'})), 6)
        query.reset_mock()
        detail = self.get('/places/kanin-club').get_data(as_text=True)
        for text in ('Kanin Club', 'Dining', '<td>Common</td>', 'Filipino Restaurant',
                     'Opening Hours</th><td>10:00 AM*', 'Closing Hours</th><td>10:00 PM*',
                     'Hours provided by City Tourism; verification recommended.'):
            self.assertIn(text, detail)
        for text in ('Open Map', 'Weather setting', 'Curated weather exposure'):
            self.assertNotIn(text, detail)

    def test_prototype_layout_keeps_real_detail_and_trip_actions(self):
        body = self.get('/places/synthetic-place').get_data(as_text=True)
        page = Document(body)
        self.assertTrue(page.find('div', **{'class': 'destination-detail-grid'}))
        self.assertTrue(page.find('table', **{'class': 'destination-facts'}))
        self.assertEqual([n.attrs['href'] for n in page.find('a') if n.text == 'Add to Trip'],
                         ['/user/trips/add-place/synthetic-place'])
        self.assertTrue(page.find('a', href='/places', **{'class': 'secondary-button back-link'}))
        for unsupported in ('Entrance cost', 'Good for'):
            self.assertNotIn(unsupported, body)
        for category in CATEGORIES:
            self.service.get_published_by_slug.return_value = replace(self.place, category=category)
            page = Document(self.get('/places/synthetic-place').get_data(as_text=True))
            self.assertEqual(len([n for n in page.find('svg', **{'aria-hidden': 'true'}) if page.find('article')[0] in n.ancestors]), 1)
            self.assertEqual(page.find('img'), [])

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
        self.assertIn(b'No destinations are available yet. Please check back later.', response.data)

    def test_empty_categories_are_success_without_claiming_catalog_is_empty(self):
        self.service.list_published.return_value = ()
        for category, label in (('attraction', 'Attractions'), ('dining', 'Dining'),
                                ('shopping', 'Shopping'), ('accommodation', 'Accommodation'),
                                ('nature', 'Nature'), ('heritage', 'Heritage')):
            with self.subTest(category=category):
                self.service.reset_mock()
                response = self.get('/places?category=' + category)
                self.assertEqual(response.status_code, 200)
                self.service.list_published.assert_called_once_with(category=category, limit=50, offset=0)
                self.assertIn(('No places listed in ' + label + ' yet').encode(), response.data)
                self.assertIn(b'Try another category or return to all places.', response.data)
                self.assertNotIn(b'Places are on the way', response.data)
                self.assertNotIn(b'City Tourism Office', response.data)

    def test_all_categories_pass_exactly_once(self):
        for category in CATEGORIES:
            self.service.reset_mock()
            response = self.get('/places?category=' + category)
            self.assertEqual(response.status_code, 200)
            self.service.list_published.assert_called_once_with(category=category, limit=50, offset=0)
            self.assertEqual(self.render.call_args.kwargs['selected_category'], category)

    def test_invalid_category_rejected_before_service(self):
        for query in ('category=', 'category=NATURE', 'category=%20nature%20',
                      'category=unsupported', 'category=nature&category=nature',
                      'category=nature&category=dining'):
            response = self.get('/places?' + query)
            self.assertEqual(response.status_code, 400)
            self.assertIn(b'Invalid place category.', response.data)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.service.list_published.assert_not_called()
        self.assertTrue(all(call.args[0] == 'places/error.html' for call in self.render.call_args_list))

    def test_unrelated_query_controls_are_ignored(self):
        response = self.get('/places?limit=999&offset=5&order=name&select=*&status=draft')
        self.assertEqual(response.status_code, 200)
        self.service.list_published.assert_called_once_with(category=None, limit=50, offset=0)

    def test_detail_success_exact_context_and_slug_delegation(self):
        response = self.get('/places/SYNTHETIC-PLACE')
        self.assertEqual(response.status_code, 200)
        self.service.get_published_by_slug.assert_called_once_with('SYNTHETIC-PLACE')
        self.render.assert_called_once_with('places/detail.html', place=self.place,
                                           destination_weather=UNKNOWN)
        self.assertIn(b'Synthetic description', response.data)

    def test_missing_detail_is_fixed_404(self):
        self.service.get_published_by_slug.return_value = None
        response = self.get('/places/missing')
        self.assertEqual(response.status_code, 404)
        self.assertIn(b'Place not found.', response.data)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertTrue(all(call.args[0] == 'places/error.html' for call in self.render.call_args_list))

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
                self.assertIn(message, response.data)
                self.assertNotIn(b'private-provider', response.data)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            method.side_effect = None
        self.assertTrue(all(call.args[0] == 'places/error.html' for call in self.render.call_args_list))

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
            assert_shared_scripts(self,Document(response.get_data(as_text=True)))
            for forbidden in (b'<img', b'images.invalid', b'sb_publishable_',
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
