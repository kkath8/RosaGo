"""Public layout contracts, using synthetic catalog data and no network."""
from html.parser import HTMLParser
import os
from pathlib import Path
import runpy
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from places_client import PublicPlacesClient


ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    """Collect elements and their ancestors without an HTML dependency."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.stack = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = SimpleNamespace(tag=tag, attrs=dict(attrs), text='',
                               ancestors=tuple(self.stack))
        self.elements.append(node)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img',
                       'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_data(self, data):
        for node in self.stack:
            node.text += data

    def find(self, tag, **attrs):
        return [node for node in self.elements if node.tag == tag
                and all(node.attrs.get(key) == value for key, value in attrs.items())]


class PublicLayoutTests(unittest.TestCase):
    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname',
                      'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
            (PublicPlacesClient, ('database_client',)),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        self.shared = Mock()
        with (
            patch('dotenv.load_dotenv'),
            patch.dict(os.environ, SUPABASE_URL='https://fixture.invalid',
                       SUPABASE_KEY='sb_publishable_layout_fixture',
                       FLASK_SECRET_KEY='offline-layout-fixture'),
            patch('supabase.create_client', return_value=self.shared),
        ):
            self.app = runpy.run_path(str(ROOT / 'app.py'))['app']
        self.app.testing = True
        self.addCleanup(self.shared.assert_not_called)
        dependencies = self.app.extensions['rosago_normal_auth']
        for obj in (dependencies.store, dependencies.coordinator, dependencies.adapters):
            for name in dir(type(obj)):
                if not name.startswith('_') and callable(getattr(obj, name, None)):
                    guard = patch.object(obj, name, side_effect=AssertionError('Auth lookup forbidden.'))
                    mocked = guard.start()
                    self.addCleanup(guard.stop)
                    self.addCleanup(mocked.assert_not_called)
        self.place = SimpleNamespace(name='Synthetic place', slug='synthetic-place',
            category='nature', address='Synthetic address', description='Synthetic description',
            image_url='https://images.invalid/unused.jpg')
        self.service = Mock(spec_set=['list_published', 'get_published_by_slug'])
        self.service.list_published.return_value = (self.place,)
        self.service.get_published_by_slug.return_value = self.place
        self.app.extensions['rosago_places'] = self.service
        self.client = self.app.test_client()
        self.paths = ('/', '/places', '/places/synthetic-place')

    def tearDown(self):
        self.assertEqual(self.shared.mock_calls, [])

    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        return Document(response.get_data(as_text=True))

    def test_shared_landmarks_skip_link_and_local_stylesheet(self):
        for path in self.paths:
            with self.subTest(path=path):
                page = self.page(path)
                self.assertEqual(len(page.find('html', lang='en')), 1)
                self.assertEqual(len(page.find('meta', name='viewport')), 1)
                self.assertEqual(len(page.find('body', **{'class': 'public-site'})), 1)
                self.assertEqual(len(page.find('main')), 1)
                self.assertEqual(len(page.find('main', id='main-content', tabindex='-1')), 1)
                self.assertEqual(page.find('a')[0].attrs['href'], '#main-content')
                self.assertEqual(len(page.find('h1')), 1)
                self.assertTrue(page.find('title')[0].text.strip())
                self.assertEqual(len(page.find('footer')), 1)
                self.assertIn('RosaGo', page.find('footer')[0].text)
                styles = page.find('link', rel='stylesheet')
                self.assertEqual([node.attrs['href'] for node in styles], ['/static/css/site.css'])
                self.assertEqual(page.stack, [])
                for tag in ('script', 'img', 'iframe', 'object', 'embed', 'style'):
                    self.assertEqual(page.find(tag), [])
                for node in page.elements:
                    for attr in ('href', 'src', 'action', 'poster'):
                        if attr in node.attrs:
                            self.assertTrue(node.attrs[attr].startswith(('/', '#')))
                            self.assertFalse(node.attrs[attr].startswith('//'))
        with self.client.get('/static/css/site.css') as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'text/css')

    def test_navigation_destinations_and_active_section(self):
        for path, current_label, current_value in (
            ('/', 'Home', 'page'), ('/places', 'Explore', 'page'),
            ('/places/synthetic-place', 'Explore', 'true'),
        ):
            with self.subTest(path=path):
                page = self.page(path)
                navs = page.find('nav', **{'aria-label': 'Main navigation'})
                self.assertEqual(len(navs), 1)
                links = [node for node in page.find('a') if navs[0] in node.ancestors]
                self.assertEqual([(node.text.strip(), node.attrs['href']) for node in links],
                                 [('Home', '/'), ('Explore', '/places'), ('Account', '/user')])
                active = [node for node in links if 'aria-current' in node.attrs]
                self.assertEqual([(node.text.strip(), node.attrs['aria-current']) for node in active],
                                 [(current_label, current_value)])
                # Native links remain available without scripting or a hidden menu.
                for node in links:
                    for ancestor in (*node.ancestors, node):
                        self.assertNotIn('hidden', ancestor.attrs)
                        self.assertNotEqual(ancestor.attrs.get('aria-hidden'), 'true')
                        self.assertNotIn('tabindex', ancestor.attrs)

    def test_home_actions_do_not_load_catalog(self):
        self.service.list_published.side_effect = AssertionError('Home must not load places.')
        self.service.get_published_by_slug.side_effect = AssertionError('Home must not load a place.')
        page = self.page('/')
        main = page.find('main')[0]
        links = [node.attrs['href'] for node in page.find('a') if main in node.ancestors]
        self.assertEqual(links, ['/places'] + [
            '/places?category=' + category for category in
            ('attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage')
        ])
        self.assertEqual(self.service.mock_calls, [])

    def test_home_hero_copy_and_only_primary_cta(self):
        page = self.page('/')
        hero = page.find('section', **{'aria-labelledby': 'home-title'})[0]
        self.assertEqual([node.text.strip() for node in page.find('p', **{'class': 'eyebrow'})
                          if hero in node.ancestors], ['Santa Rosa, Laguna'])
        self.assertEqual([node.text for node in page.find('h1')],
                         ['Discover Santa Rosa with RosaGo'])
        self.assertEqual(page.find('br'), [])
        self.assertIn("RosaGo is a Smart Tourism System for Santa Rosa, Laguna. Start with "
                      "Explore to browse the city's place catalog by category.", hero.text)
        links = [node for node in page.find('a') if hero in node.ancestors]
        self.assertEqual([(node.text, node.attrs['href']) for node in links],
                         [('Explore Places', '/places')])
        self.assertEqual(page.find('button'), [])
        self.assertEqual(len(page.find('a', **{'class': 'site-button'})), 1)

    def test_home_category_labels_destinations_and_availability(self):
        page = self.page('/')
        nav = page.find('nav', **{'aria-labelledby': 'home-categories-title'})[0]
        lists = [node for node in page.find('ul') if nav in node.ancestors]
        self.assertEqual(len(lists), 1)
        items = [node for node in page.find('li') if lists[0] in node.ancestors]
        self.assertEqual(len(items), 6)
        links = [node for node in page.find('a') if nav in node.ancestors]
        self.assertEqual([(node.text, node.attrs['href']) for node in links], [
            ('Attractions', '/places?category=attraction'),
            ('Dining', '/places?category=dining'),
            ('Shopping', '/places?category=shopping'),
            ('Accommodation', '/places?category=accommodation'),
            ('Nature', '/places?category=nature'),
            ('Heritage', '/places?category=heritage'),
        ])
        for node in links:
            self.assertEqual(node.ancestors[-1].tag, 'li')
            self.assertNotIn('aria-current', node.attrs)
            self.assertNotIn('tabindex', node.attrs)
        section = page.find('section', **{'aria-labelledby': 'home-categories-title'})[0]
        self.assertIn('Choose a category to open Explore.', section.text)
        self.assertIn('Verified place information from the Santa Rosa City Tourism Office is '
                      'pending. Some categories may not have listings yet.', section.text)

    def test_home_four_sections_and_heading_associations(self):
        page = self.page('/')
        main = page.find('main')[0]
        sections = page.find('section')
        self.assertEqual(len(sections), 4)
        expected = [
            ('h1', 'home-title', 'Discover Santa Rosa with RosaGo'),
            ('h2', 'home-categories-title', 'Explore by category'),
            ('h2', 'home-capabilities-title', 'What RosaGo offers'),
            ('h2', 'home-about-title', 'About RosaGo'),
        ]
        for section, (tag, heading_id, text) in zip(sections, expected):
            self.assertIs(section.ancestors[-1], main)
            self.assertEqual(section.attrs.get('aria-labelledby'), heading_id)
            headings = page.find(tag, id=heading_id)
            self.assertEqual(len(headings), 1)
            self.assertIn(section, headings[0].ancestors)
            self.assertEqual(headings[0].text, text)
        self.assertEqual([node.text for node in page.find('h2')],
                         [entry[2] for entry in expected[1:]])
        about = sections[-1]
        self.assertIn('RosaGo is a student capstone project developing a Smart Tourism System '
                      'focused on Santa Rosa, Laguna. It brings place discovery and planned '
                      'visitor tools into one platform.', about.text)

    def test_home_capabilities_have_truthful_noninteractive_statuses(self):
        page = self.page('/')
        section = page.find('section', **{'aria-labelledby': 'home-capabilities-title'})[0]
        lists = [node for node in page.find('ul') if section in node.ancestors]
        self.assertEqual(len(lists), 1)
        items = [node for node in page.find('li') if lists[0] in node.ancestors]
        expected = [
            ('Explore places', 'Available \u2014 catalog pending',
             'Browse by category and open place details when listings are available.'),
            ('Interactive map', 'Planned', 'See where places are located across the city.'),
            ('Trip planning', 'Planned', 'Organize places into a visit itinerary.'),
            ('Personalized recommendations', 'Planned', 'Find suggestions based on your interests.'),
            ('Tourism AI assistant', 'Planned', 'Ask questions to help prepare for a visit.'),
        ]
        self.assertEqual(len(items), len(expected))
        for item, (name, status, description) in zip(items, expected):
            self.assertEqual([node.text for node in page.find('strong') if item in node.ancestors],
                             [name])
            self.assertEqual([node.text for node in page.find('span') if item in node.ancestors],
                             [status])
            self.assertEqual([node.text for node in page.find('p') if item in node.ancestors],
                             [description])
        for node in page.elements:
            if section in node.ancestors:
                self.assertNotIn(node.tag, ('a', 'button', 'input', 'select', 'textarea'))
                self.assertNotIn('tabindex', node.attrs)
                self.assertNotIn(node.attrs.get('role'), ('button', 'link'))

    def test_home_has_no_poi_previews_statistics_or_provider_data(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        page = Document(html)
        for forbidden in ('Featured Places', self.place.name, self.place.address,
                          self.place.description, self.place.slug, self.place.image_url,
                          '/auth/status', 'fixture.invalid', 'sb_publishable_',
                          'access_token', 'refresh_token', 'provider_response',
                          'private@example.invalid'):
            self.assertNotIn(forbidden, html)
        for tag in ('article', 'img', 'picture', 'script', 'iframe', 'object', 'embed'):
            self.assertEqual(page.find(tag), [])
        self.assertNotRegex(page.find('main')[0].text, r'\d')
        for node in page.elements:
            self.assertNotIn('style', node.attrs)
            self.assertNotIn('srcset', node.attrs)
            self.assertFalse(any(attr.lower().startswith('on') for attr in node.attrs))
        css = (ROOT / 'static/css/site.css').read_text(encoding='utf-8')
        self.assertNotRegex(css.lower(), r'@import|url\s*\(|https?://')
        self.assertEqual(self.service.mock_calls, [])

    def test_category_selection_and_empty_state(self):
        for query, label in (('', 'All'), ('?category=nature', 'Nature')):
            page = self.page('/places' + query)
            nav = page.find('nav', **{'aria-label': 'Place categories'})[0]
            selected = [node for node in page.find('a', **{'aria-current': 'page'})
                        if nav in node.ancestors]
            self.assertEqual([node.text.strip() for node in selected], [label])
            self.assertEqual(len(page.find('a', href='/places/synthetic-place')), 1)
        self.service.list_published.return_value = ()
        for query, message in (
            ('', 'No published places are available yet.'),
            ('?category=nature', 'No published places are available in this category yet.'),
        ):
            page = self.page('/places' + query)
            self.assertIn(message, page.find('main')[0].text)
            self.assertEqual(page.find('article'), [])

    def test_detail_content_back_link_and_escaping(self):
        unsafe = '<script>synthetic & text</script>'
        self.place.name = self.place.address = self.place.description = unsafe
        for path in self.paths[1:]:
            page = self.page(path)
            self.assertEqual(page.find('script'), [])
            self.assertIn(unsafe, page.find('main')[0].text)
            self.assertNotIn('images.invalid', page.find('body')[0].text)
        page = self.page('/places/synthetic-place')
        self.assertEqual(page.find('h1')[0].text, unsafe)
        self.assertEqual(len(page.find('a', **{'class': 'back-link', 'href': '/places'})), 1)
        self.assertIn('About this place', page.find('article')[0].text)

    def test_public_layout_does_not_lookup_or_mutate_auth_state(self):
        baseline = {path: self.client.get(path).data for path in self.paths}
        for state in ({'auth_session_id': 'stale-handle'},
                      {'user_id': 'legacy-user', 'user_email': 'private@example.invalid'}):
            with self.client.session_transaction() as session:
                session.update(state)
            for path in self.paths:
                with self.subTest(state=state, path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data, baseline[path])
                    self.assertEqual(response.headers.getlist('Set-Cookie'), [])
                    with self.client.session_transaction() as session:
                        self.assertEqual(dict(session), state)
            with self.client.session_transaction() as session:
                session.clear()


if __name__ == '__main__':
    unittest.main()
