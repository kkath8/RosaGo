"""Offline map foundation: reuse the guarded public-route fixture, not its tests."""
import unittest
from flask import url_for

from places_service import PlacesConsistencyError, PlacesUnavailableError
from test_public_layout import Document
import test_places_routes


class MapRouteTests(unittest.TestCase):
    # This fixture blocks real network/client/auth access, supplies synthetic Place
    # values, and observes the actual render context and cookie writes.
    setUp = test_places_routes.PlacesRouteTests.setUp
    tearDown = test_places_routes.PlacesRouteTests.tearDown
    get = test_places_routes.PlacesRouteTests.get

    def test_empty_catalog_renders_text_only_with_minimal_context(self):
        self.service.list_published.return_value = ()
        response = self.get('/map')
        self.assertEqual(response.status_code, 200)
        self.service.list_published.assert_called_once_with(category=None, limit=50, offset=0)
        self.service.get_published_by_slug.assert_not_called()
        self.render.assert_called_once_with('map.html', has_places=False)
        page = Document(response.get_data(as_text=True))
        self.assertEqual([node.text for node in page.find('h1')], ['Explore Santa Rosa on the map'])
        self.assertEqual([node.text for node in page.find('h2')], ['Places are on the way'])
        self.assertIn('Verified place information from the Santa Rosa City Tourism Office is '
                      'pending. Please check back later.', page.find('main')[0].text)
        self.assertEqual([node.text for node in page.find('a', href='/places')
                          if page.find('main')[0] in node.ancestors], ['Browse places'])

    def test_populated_catalog_exposes_only_boolean_state(self):
        response = self.get('/map')
        self.assertEqual(response.status_code, 200)
        self.service.list_published.assert_called_once_with(category=None, limit=50, offset=0)
        self.render.assert_called_once_with('map.html', has_places=True)
        html = response.get_data(as_text=True)
        self.assertIn('The interactive map is not available yet. You can continue browsing '
                      'the available places in Explore.', html)
        self.assertNotIn('Places are on the way', html)
        self.assertNotIn('City Tourism Office', html)
        for value in (self.place.id, self.place.name, self.place.slug, self.place.address,
                      self.place.description, str(self.place.latitude), str(self.place.longitude),
                      self.place.image_url, self.place.created_at.isoformat(),
                      self.place.updated_at.isoformat(), '2026-10-11'):
            self.assertNotIn(value, html)
        context = self.contexts[0]
        self.assertIs(context['has_places'], True)
        for key in ('places', 'place', 'client', 'service', 'provider_response', 'token', 'auth'):
            self.assertNotIn(key, context)

    def test_shared_layout_no_map_assets_or_unsupported_controls(self):
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
            self.assertEqual([node.attrs['href'] for node in page.find('link', rel='stylesheet')],
                             ['/static/css/site.css'])
            nav = page.find('nav', **{'aria-label': 'Main navigation'})[0]
            links = [node for node in page.find('a') if nav in node.ancestors]
            self.assertEqual([(node.text.strip(), node.attrs['href']) for node in links],
                             [('Home', '/'), ('Explore', '/places'), ('Account', '/user')])
            self.assertEqual(page.find('a', href='/map'), [])
            for tag in ('script', 'img', 'iframe', 'canvas', 'object', 'embed', 'button', 'input', 'form'):
                self.assertEqual(page.find(tag), [])
            for node in page.elements:
                self.assertNotIn(node.attrs.get('role'), ('application', 'region', 'alert'))
                self.assertNotIn(node.attrs.get('id'), ('map', 'map-container', 'map-data'))
                self.assertNotIn('style', node.attrs)
                self.assertFalse(any(attr.lower().startswith('on') for attr in node.attrs))
                for attr in ('href', 'src'):
                    if attr in node.attrs:
                        self.assertTrue(node.attrs[attr].startswith(('/', '#')))
                        self.assertFalse(node.attrs[attr].startswith('//'))
            for forbidden in ('leaflet', 'tile.openstreetmap', 'geolocation', 'application/json',
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

    def test_post_rejected_endpoint_stable_and_home_still_planned(self):
        response = self.client.post('/map')
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        with self.app.test_request_context():
            self.assertEqual(url_for('map_index'), '/map')
        page = Document(self.get('/').get_data(as_text=True))
        rows = [node for node in page.find('li') if 'Interactive map' in node.text]
        self.assertEqual(len(rows), 1)
        self.assertEqual([node.text for node in page.find('span') if rows[0] in node.ancestors],
                         ['Planned'])
        self.assertEqual(page.find('a', href='/map'), [])
        self.assertEqual(self.service.mock_calls, [])

    def test_shared_template_autoescaping_remains_enabled(self):
        self.assertTrue(self.app.jinja_env.autoescape('map.html'))
        # Exercise the inherited title block with hostile text, without changing
        # the route's boolean-only template contract or any template on disk.
        with self.app.test_request_context('/map'):
            template = self.app.jinja_env.from_string(
                "{% extends 'map.html' %}{% block title %}{{ text }}{% endblock %}")
            html = template.render(has_places=False, text='<script>unsafe & text</script>')
        self.assertIn('&lt;script&gt;unsafe &amp; text&lt;/script&gt;', html)
        self.assertEqual(Document(html).find('script'), [])


if __name__ == '__main__':
    unittest.main()
