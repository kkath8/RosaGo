"""Offline interactive map contracts using the guarded public-route fixture."""
from dataclasses import replace
import json
from pathlib import Path
import unittest
from flask import render_template_string, url_for

from places_service import PlacesConsistencyError, PlacesUnavailableError
from test_public_layout import Document, assert_shared_scripts, NAVIGATION
import test_places_routes


class MapRouteTests(unittest.TestCase):
    # This fixture blocks real network/client/auth access, supplies synthetic Place
    # values, and observes the actual render context and cookie writes.
    setUp = test_places_routes.PlacesRouteTests.setUp
    tearDown = test_places_routes.PlacesRouteTests.tearDown
    get = test_places_routes.PlacesRouteTests.get

    def test_unlocated_places_do_not_create_map_pins_or_load_tiles(self):
        self.service.list_published.return_value = (
            replace(self.place, latitude=None, longitude=None),)
        response = self.get('/map')
        self.assertEqual(response.status_code, 200)
        self.render.assert_called_once_with('map.html', markers=[])
        page = Document(response.get_data(as_text=True))
        assert_shared_scripts(self,page)
        self.assertIn('No map pins are available yet.', page.find('main')[0].text)

    def test_empty_catalog_renders_text_only_with_minimal_context(self):
        self.service.list_published.return_value = ()
        response = self.get('/map')
        self.assertEqual(response.status_code, 200)
        self.service.list_published.assert_called_once_with(category=None, limit=50, offset=0)
        self.service.get_published_by_slug.assert_not_called()
        self.render.assert_called_once_with('map.html', markers=[])
        page = Document(response.get_data(as_text=True))
        self.assertEqual([node.text for node in page.find('h1')], ['Map & Transportation'])
        self.assertEqual([node.text for node in page.find('h2') if page.find('main')[0] in node.ancestors], ['Places are on the way'])
        self.assertIn('No map pins are available yet.', page.find('main')[0].text)
        self.assertEqual([node.text for node in page.find('a', href='/places')
                          if page.find('main')[0] in node.ancestors], ['Browse places'])

    def test_populated_catalog_exposes_exact_minimal_payload_and_text_list(self):
        self.place = replace(self.place, image_url="https://images.invalid/not-in-map-payload")
        self.service.list_published.return_value = (self.place,)
        response = self.get('/map')
        self.assertEqual(response.status_code, 200)
        self.service.list_published.assert_called_once_with(category=None, limit=50, offset=0)
        expected = dict(name=self.place.name, detail_url='/places/synthetic-place',
                        category=self.place.category, address=self.place.address, tourism_type=None,
                        latitude=self.place.latitude, longitude=self.place.longitude)
        self.render.assert_called_once_with('map.html', markers=[expected])
        html = response.get_data(as_text=True)
        page = Document(html)
        payload = json.loads(page.find('script', id='map-data')[0].text)
        self.assertEqual(payload, [expected])
        self.assertEqual(set(payload[0]), {'name', 'detail_url', 'category', 'address', 'latitude', 'longitude', 'tourism_type'})
        listing = page.find('ul', **{'class': 'map-place-list'})[0]
        self.assertEqual([node.text for node in page.find('a') if listing in node.ancestors], [self.place.name])
        self.assertIn(self.place.address, listing.text)
        self.assertIn('Nature', listing.text)
        self.assertEqual(len(page.find('div', id='places-map', role='region')), 1)
        self.assertEqual(len(page.find('noscript')), 1)
        self.assertEqual(len(page.find('a', href='https://www.openstreetmap.org/copyright')), 1)
        self.assertIn('external map service', html)
        self.assertNotIn('Places are on the way', html)
        self.assertNotIn('City Tourism Office', html)
        for value in (self.place.id, self.place.description,
                      self.place.image_url, self.place.created_at.isoformat(),
                      self.place.updated_at.isoformat(), '2026-10-11'):
            self.assertNotIn(value, html)
        context = self.contexts[0]
        self.assertEqual(context['markers'], [expected])
        for key in ('places', 'place', 'client', 'service', 'provider_response', 'token', 'auth'):
            self.assertNotIn(key, context)

    def test_shared_layout_conditional_local_assets_and_active_map(self):
        for places in ((), (self.place,)):
            self.service.list_published.return_value = places
            response = self.get('/map')
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            page = Document(html)
            self.assertEqual(len(page.find('main')), 1)
            self.assertEqual(len(page.find('main', id='main-content', tabindex='-1')), 1)
            self.assertEqual(page.find('a')[0].attrs['href'], '#main-content')
            self.assertEqual(len(page.find('h1')), 1)
            self.assertEqual(len(page.find('footer')), 1)
            styles = ['/static/css/theme.css', '/static/css/site.css']
            if places:
                styles.append('/static/vendor/leaflet/leaflet.css')
            styles.extend(['/static/css/destination-images.css', '/static/css/workspace-ui.css'])
            self.assertEqual([node.attrs['href'] for node in page.find('link', rel='stylesheet') if node.attrs['href'].startswith('/static/')], styles)
            scripts = page.find('script')
            if places:
                self.assertEqual([node.attrs.get('src') for node in scripts], [
                    '/static/js/theme.js', '/static/vendor/leaflet/leaflet.js',
                    '/static/js/map.js', '/static/js/destination-images.js', '/static/js/personal-state.js',
                    '/static/js/user-ui.js', '/static/js/account-management.js', None])
                self.assertNotIn('defer', scripts[0].attrs)  # Theme applies before paint.
                for script in scripts[1:-1]:
                    self.assertIn('defer', script.attrs)
                self.assertEqual(scripts[-1].attrs, {'id': 'map-data', 'type': 'application/json'})
                self.assertEqual(len(page.find('meta', name='referrer', content='strict-origin-when-cross-origin')), 1)
                self.assertIn('hidden', page.find('p', id='map-failure')[0].attrs)
                self.assertIn('hidden', page.find('p', id='map-tile-failure')[0].attrs)
                self.assertNotIn(response.headers.get('Referrer-Policy'), ('no-referrer', 'same-origin'))
            else:
                assert_shared_scripts(self,page)
                self.assertEqual(page.find('div', id='places-map'), [])
                for forbidden in ('leaflet', 'map.js', 'map-data', 'tile.openstreetmap', 'map-place-list'):
                    self.assertNotIn(forbidden, html)
            nav = page.find('nav', **{'aria-label': 'Main navigation'})[0]
            links = [node for node in page.find('a') if nav in node.ancestors and not any(a.attrs.get('class')=='header-account' for a in node.ancestors)]
            self.assertEqual([(node.text.strip(), node.attrs['href']) for node in links],
                             NAVIGATION)
            self.assertEqual([(node.text, node.attrs['aria-current']) for node in links if 'aria-current' in node.attrs],
                             [('Map & Transport', 'page')])
            for tag in ('img', 'iframe', 'canvas', 'object', 'embed'):
                self.assertEqual(page.find(tag), [])
            route_forms = page.find('form', id='route-form')
            self.assertEqual(len(route_forms), 1 if places else 0)
            if places:
                self.assertEqual(route_forms[0].attrs['action'], '/api/route')
                self.assertEqual(route_forms[0].attrs['method'], 'post')
            for node in page.elements:
                self.assertNotIn(node.attrs.get('role'), ('application', 'alert'))
                self.assertNotIn('style', node.attrs)
                self.assertFalse(any(attr.lower().startswith('on') for attr in node.attrs))
                for attr in ('href', 'src'):
                    if attr in node.attrs:
                        self.assertTrue(node.attrs[attr].startswith(('/', '#')) or
                                        node.attrs[attr] == 'https://www.openstreetmap.org/copyright' or node.attrs[attr].startswith(('https://fonts.googleapis.com','https://fonts.gstatic.com')))
                        self.assertFalse(node.attrs[attr].startswith('//'))
            for forbidden in ('tile.openstreetmap', 'geolocation',
                              '/auth/status', 'sb_publishable_', 'private-access-token',
                              'private-refresh-token', 'fixture.invalid'):
                self.assertNotIn(forbidden, html)
            self.assertEqual(page.stack, [])

    def test_sessions_do_not_change_rendering_or_trigger_auth(self):
        for places in ((), (self.place,)):
            self.service.list_published.return_value = places
            baseline = self.get('/map').data
            for state in ({'auth_session_id': self.handle}, {'auth_session_id': 'stale-handle'},
                          {'user_id': 'legacy-user', 'user_email': 'legacy@example.invalid'}):
                with self.client.session_transaction() as session:
                    session.clear()
                    session.update(state)
                self.service.reset_mock()
                response = self.get('/map')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, baseline)
                self.service.list_published.assert_called_once_with(category=None, limit=50, offset=0)
                with self.client.session_transaction() as session:
                    self.assertEqual(dict(session), state)
            with self.client.session_transaction() as session:
                session.clear()

    def test_service_failures_are_sanitized_and_not_empty_states(self):
        for kind, status, body in (
            (PlacesUnavailableError, 503, b'Places are temporarily unavailable.'),
            (PlacesConsistencyError, 500, b'Unable to display places.'),
        ):
            error = kind()
            error.args = ('private-provider-body private-access-token https://fixture.invalid',)
            error.add_note('private-record-note')
            self.service.list_published.side_effect = error
            self.service.reset_mock()
            response = self.get('/map')
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.data, body)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.service.list_published.assert_called_once_with(category=None, limit=50, offset=0)
        self.render.assert_not_called()

    def test_programming_and_rendering_errors_propagate(self):
        error = RuntimeError('programming sentinel')
        self.service.list_published.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self.get('/map')
        self.assertIs(raised.exception, error)
        self.render.assert_not_called()
        self.service.list_published.side_effect = None
        for error in (RuntimeError('template sentinel'), PlacesUnavailableError(), PlacesConsistencyError()):
            self.render.side_effect = error
            with self.assertRaises(type(error)) as raised:
                self.get('/map')
            self.assertIs(raised.exception, error)

    def test_post_rejected_endpoint_stable_and_home_map_available(self):
        response = self.client.post('/map')
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        with self.app.test_request_context():
            self.assertEqual(url_for('map_index'), '/map')
        page = Document(self.get('/').get_data(as_text=True))
        quick = page.find('nav', **{'aria-label': 'Main navigation'})[0]
        links = [node for node in page.find('a', href='/map') if quick in node.ancestors]
        self.assertEqual([node.text.strip() for node in links], ['Map & Transport'])
        self.service.list_published.assert_called_once_with(category=None, limit=3, offset=0)

    def test_shared_template_autoescaping_remains_enabled(self):
        self.assertTrue(self.app.jinja_env.autoescape('map.html'))
        # Exercise the inherited title block without changing templates on disk.
        with self.app.test_request_context('/map'):
            # Use Flask's rendering pipeline so shared context processors supply
            # website_settings just as they do on the actual Map route.
            html = render_template_string(
                "{% extends 'map.html' %}{% block title %}{{ text }}{% endblock %}",
                markers=[], text='<script>unsafe & text</script>')
        self.assertIn('&lt;script&gt;unsafe &amp; text&lt;/script&gt;', html)
        assert_shared_scripts(self,Document(html))

    def test_hostile_marker_text_cannot_break_json_or_create_markup(self):
        hostile = '"quoted" <img src=x onerror=alert(1)> </script><script>alert(1)</script> & \u00f1 \u2028'
        place = replace(self.place, name=hostile, address=hostile)
        self.service.list_published.return_value = (place,)
        response = self.get('/map')
        html = response.get_data(as_text=True)
        page = Document(html)
        self.assertEqual([node.attrs.get('src') for node in page.find('script')], [
            '/static/js/theme.js', '/static/vendor/leaflet/leaflet.js',
            '/static/js/map.js', '/static/js/destination-images.js', '/static/js/personal-state.js',
            '/static/js/user-ui.js', '/static/js/account-management.js', None])
        self.assertEqual(len(page.find('script', id='map-data', type='application/json')), 1)
        self.assertEqual(page.find('img'), [])
        data = page.find('script', id='map-data')[0].text
        self.assertNotIn('<', data)
        self.assertEqual(json.loads(data)[0]['name'], hostile)
        self.assertEqual(json.loads(data)[0]['address'], hostile)
        self.assertIn('&lt;img', html)
        listing = page.find('ul', **{'class': 'map-place-list'})[0]
        self.assertIn(hostile, listing.text)

    def test_original_map_precedes_list_and_uses_only_payload_places(self):
        page = Document(self.get('/map').get_data(as_text=True))
        workspace = page.find('div', **{'class': 'map-workspace'})[0]
        panel = page.find('section', **{'class': 'map-destination-panel'})[0]
        canvas = page.find('section', **{'class': 'map-canvas-panel'})[0]
        self.assertIn(workspace, panel.ancestors)
        self.assertIn(workspace, canvas.ancestors)
        self.assertLess(page.elements.index(canvas), page.elements.index(panel))
        scroller = page.find('div', **{'class': 'map-list-scroll'})[0]
        self.assertEqual(scroller.attrs['tabindex'], '0')
        self.assertEqual(scroller.attrs['aria-label'], 'Destination list')
        self.assertEqual([node.text for node in page.find('span', **{'class': 'map-category-badge'})], ['Nature'])
        self.assertEqual([node.attrs['href'] for node in page.find('a') if scroller in node.ancestors],
                         ['/places/synthetic-place'])
        self.assertNotIn('test records are synthetic examples', page.find('main')[0].text)
        self.assertNotRegex(page.find('main')[0].text.lower(),
                            r'ratings|reviews|prices|current location')
        self.assertIn('Estimates exclude live traffic', page.find('main')[0].text)
        self.service.list_published.assert_called_once_with(category=None, limit=50, offset=0)
        self.assertEqual(page.stack, [])

    def test_vendored_assets_are_local_pinned_and_integrity_recorded(self):
        import hashlib
        root = Path(__file__).resolve().parents[1] / 'static/vendor/leaflet'
        manifest = json.loads((root / 'SHA256SUMS.json').read_text())
        for name, digest in manifest.items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)
            with self.client.get('/static/vendor/leaflet/' + name) as response:
                self.assertEqual(response.status_code, 200)
        self.assertIn(b'1.9.4', (root / 'leaflet.js').read_bytes())
        self.assertIn('Redistribution and use', (root / 'LICENSE').read_text())


if __name__ == '__main__':
    unittest.main()
