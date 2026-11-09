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


NAVIGATION = [('Dashboard','/'),('Explore','/places'),('Planner','/user/planner'),('My Trips','/user/trips'),('Map & Transport','/map'),('AI Assistant','/user/assistant'),('Saved Places','/saved'),('Visited Places','/visited'),('Budget Planner','/budget'),('Profile','/user'),('Settings','/user/settings'),('Alerts','/user/alerts'),('Help','/help'),('Terms','/terms'),('Privacy','/privacy')]


def assert_shared_scripts(test, page):
    scripts = page.find('script')
    theme = [n for n in scripts if n.attrs.get('src') == '/static/js/theme.js']
    test.assertEqual(len(theme),1)
    test.assertNotIn('defer',theme[0].attrs) # Apply saved presentation before paint.
    scripts = [n for n in scripts if n not in theme]
    expected = ['/static/js/destination-images.js','/static/js/personal-state.js','/static/js/user-ui.js','/static/js/account-management.js']
    if page.find('form', id='budget-plan-form'):
        expected[:0] = ['/static/js/budget-plan.js','/static/js/budget-ui.js']
    if page.find('section', **{'class':'itinerary-page recommendations-page'}):
        expected.insert(0,'/static/js/recommendations.js')
    if page.find('dialog', id='trip-chooser'):
        expected.insert(0, '/static/js/trip-chooser.js')
    if page.find('section', **{'class': 'itinerary-page preview-page'}):
        expected.insert(0, '/static/js/itinerary-preview.js')
    if page.find('section', **{'data-chat-panel': None, 'class': 'conversation-panel'}):
        expected.insert(0, '/static/js/assistant-chat.js')
    test.assertEqual([n.attrs.get('src') for n in scripts], expected)
    for node in scripts:
        test.assertEqual(node.text.strip(), '')
        test.assertIn('defer', node.attrs)


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
        self.place = SimpleNamespace(id='00000000-0000-0000-0000-000000000001', name='Synthetic place', slug='synthetic-place',
            category='nature', address='Synthetic address', description='Synthetic description',
            image_url='https://images.invalid/unused.jpg', latitude=None, longitude=None)
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
                if path != '/': self.place.image_url = None
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
                self.assertEqual([node.attrs['href'] for node in styles if node.attrs['href'].startswith('/static/')], ['/static/css/theme.css','/static/css/site.css'] + (['/static/css/budget-dashboard.css'] if path == '/' else ['/static/css/tourism.css', '/static/css/trip-chooser.css']) + ['/static/css/destination-images.css','/static/css/workspace-ui.css'])
                self.assertEqual(page.stack, [])
                assert_shared_scripts(self, page)
                for tag in ('iframe', 'object', 'embed', 'style'):
                    self.assertEqual(page.find(tag), [])
                for node in page.elements:
                    for attr in ('href', 'src', 'action', 'poster'):
                        if attr in node.attrs:
                            self.assertTrue(node.attrs[attr].startswith(('/', '#', 'https://fonts.googleapis.com', 'https://fonts.gstatic.com', 'https://open-meteo.com/')))
                            self.assertFalse(node.attrs[attr].startswith('//'))
        with self.client.get('/static/css/site.css') as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'text/css')

    def test_navigation_destinations_and_active_section(self):
        for path, current_label, current_value in (
            ('/', 'Dashboard', 'page'), ('/places', 'Explore', 'page'),
            ('/places/synthetic-place', 'Explore', 'true'),
        ):
            with self.subTest(path=path):
                page = self.page(path)
                navs = page.find('nav', **{'aria-label': 'Main navigation'})
                self.assertEqual(len(navs), 1)
                links = [node for node in page.find('a') if navs[0] in node.ancestors and not any(a.attrs.get('class')=='header-account' for a in node.ancestors)]
                self.assertEqual([(node.text.strip(), node.attrs['href']) for node in links],
                                 NAVIGATION)
                active = [node for node in links if 'aria-current' in node.attrs]
                self.assertEqual([(node.text.strip(), node.attrs['aria-current']) for node in active],
                                 [(current_label, current_value)])
                # Native links remain available without scripting or a hidden menu.
                for node in links:
                    for ancestor in (*node.ancestors, node):
                        self.assertNotIn('hidden', ancestor.attrs)
                        self.assertNotEqual(ancestor.attrs.get('aria-hidden'), 'true')
                        self.assertNotIn('tabindex', ancestor.attrs)

    def test_header_has_no_global_search_or_events_and_explore_keeps_search(self):
        for path in self.paths:
            page=self.page(path)
            self.assertEqual(page.find('input',id='shell-search'),[])
            self.assertEqual(page.find('a',href='/events'),[])
            self.assertEqual(page.find('a',href='/user/transport'),[])
            self.assertTrue(page.find('a',href='/map'))
            self.assertTrue(page.find('button',**{'aria-label':'Open Trip Bag'}))
        page=self.page('/places')
        self.assertTrue(page.find('input',id='explore-query',name='q'))
        self.assertTrue(page.find('form',action='/places',method='get'))

    def test_mobile_more_keeps_ai_and_existing_options_without_duplicate_dashboard(self):
        for path in self.paths:
            with self.subTest(path=path):
                page = self.page(path)
                menu = page.find('dialog', id='more-dialog')[0]
                links = [node for node in page.find('a') if menu in node.ancestors]
                self.assertEqual([(node.text.strip(), node.attrs['href']) for node in links],
                    [*NAVIGATION[5:], ('Log in', '/login')])
                self.assertFalse(page.find('section', **{'aria-labelledby': 'more-quick-actions-title'}))
                trigger = page.find('button', **{'data-open-dialog': 'more-dialog'})[0]
                self.assertEqual(trigger.attrs['aria-controls'], 'more-dialog')
                self.assertEqual(trigger.attrs['aria-haspopup'], 'dialog')
                self.assertEqual(trigger.attrs['aria-expanded'], 'false')

    def test_mobile_tabs_order_routes_icons_and_active_destination_section(self):
        for path in self.paths:
            with self.subTest(path=path):
                page = self.page(path)
                nav = page.find('nav', **{'aria-label': 'Mobile navigation'})[0]
                items = [node for node in page.elements if nav in node.ancestors
                    and node.tag in ('a', 'button')]
                self.assertEqual([node.text.strip() for node in items],
                    ['Dashboard', 'Explore', 'Plan', 'Trips', 'Map', 'More'])
                self.assertEqual([node.attrs['href'] for node in items[:-1]],
                    ['/', '/places', '/user/planner', '/user/trips', '/map'])
                self.assertTrue(any(node.attrs.get('href') == '#icon-home'
                    for node in page.find('use') if items[0] in node.ancestors))
                current = [(node.text.strip(), node.attrs['aria-current'])
                    for node in items if 'aria-current' in node.attrs]
                self.assertEqual(current, [('Dashboard', 'page')] if path == '/' else
                    [('Explore', 'true' if path.startswith('/places/') else 'page')])

    def test_mobile_parent_sections_stay_active_on_user_modules(self):
        for path, label in [('/user/planner', 'Plan'), ('/user/trips', 'Trips'),
                            ('/map', 'Map'), ('/user/assistant', 'More'), ('/saved', 'More')]:
            with self.subTest(path=path), self.app.test_request_context(path):
                page = Document(self.app.jinja_env.get_template('partials/mobile_navigation.html').render())
                nav = page.find('nav', **{'aria-label': 'Mobile navigation'})[0]
                current = [node.text.strip() for node in page.elements
                    if nav in node.ancestors and 'aria-current' in node.attrs]
                self.assertEqual(current, [label])

    def test_dashboard_bounded_places_and_real_links(self):
        page = self.page('/')
        self.service.list_published.assert_called_once_with(category=None, limit=3, offset=0)
        self.service.get_published_by_slug.assert_not_called()
        self.assertEqual([n.text for n in page.find('h1')], ['Plan your next trip to Santa Rosa'])
        self.assertTrue(page.find('a', href='/places/synthetic-place'))
        self.assertIn(self.place.address, page.find('main')[0].text)
        quick = page.find('nav', **{'aria-label':'Dashboard quick actions'})[0]
        self.assertEqual([n.attrs['href'] for n in page.find('a') if quick in n.ancestors], ['/user/planner','/places','/user/trips','/map','/user/alerts','/user/assistant'])
        self.assertEqual(len(page.find('header', **{'class':'site-header'})), 1)
        self.assertIn('Sign in to view your trips', page.find('main')[0].text)
        for heading in ('Plan by mood','Popular places','Santa Rosa Arch','Upcoming Trips'):
            self.assertTrue(any(n.text == heading for n in page.find('h2')))

    def test_dashboard_empty_failure_and_escaping(self):
        from places_service import PlacesUnavailableError, PlacesConsistencyError
        self.service.list_published.return_value = ()
        self.assertIn('No published places are available yet', self.page('/').find('main')[0].text)
        for error in (PlacesUnavailableError(), PlacesConsistencyError()):
            self.service.list_published.side_effect = error
            page = self.page('/')
            self.assertIn('Places are temporarily unavailable', page.find('main')[0].text)
            self.assertNotIn('No published places', page.find('main')[0].text)
        self.service.list_published.side_effect = None
        self.place.name = self.place.address = '<script>unsafe</script>'
        self.place.image_url = 'https://images.invalid/unused.jpg'
        self.service.list_published.return_value = (self.place,)
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', html)
        assert_shared_scripts(self, Document(html))
        self.assertNotIn(self.place.image_url, html)

    def test_dashboard_personal_features_have_no_invented_metrics(self):
        page = self.page('/')
        self.assertIn('not a popularity ranking', page.find('main')[0].text)
        self.assertNotRegex(page.find('main')[0].text.lower(), r'ratings|money spent|[0-9]+ visitors')
        self.assertEqual(page.find('iframe'), [])
        for key in ('saved','visited','unread'):
            self.assertTrue(page.find('b', **{'data-count':key}))
        assert_shared_scripts(self,page)

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
            ('', 'Places are on the way'),
            ('?category=nature', 'No places listed in Nature yet'),
        ):
            page = self.page('/places' + query)
            self.assertIn(message, page.find('main')[0].text)
            self.assertEqual(page.find('article'), [])
            empty = page.find('section', **{'aria-labelledby': 'empty-title'})[0]
            self.assertEqual([node.text for node in page.find('h2') if empty in node.ancestors],
                             [message])
            self.assertNotIn('aria-live', empty.attrs)
            self.assertNotIn('role', empty.attrs)
            links = [node for node in page.find('a') if empty in node.ancestors]
            self.assertEqual([(node.text, node.attrs['href']) for node in links],
                             [('Browse all places', '/places')] if query else [])

    def test_places_filters_have_ordered_semantic_links_and_one_active_item(self):
        filters = [('All', None), ('Attractions', 'attraction'), ('Dining', 'dining'),
                   ('Shopping', 'shopping'), ('Accommodation', 'accommodation'),
                   ('Nature', 'nature'), ('Heritage', 'heritage'), ('Industrial Tourism', 'industrial')]
        for label, category in filters:
            with self.subTest(category=category):
                page = self.page('/places' + ('?category=' + category if category else ''))
                nav = page.find('nav', **{'aria-label': 'Place categories'})[0]
                lists = [node for node in page.find('ul') if nav in node.ancestors]
                self.assertEqual(len(lists), 1)
                links = [node for node in page.find('a') if nav in node.ancestors]
                self.assertEqual([(node.text, node.attrs['href']) for node in links],
                                 [(text, '/places' + ('?category=' + value if value else ''))
                                  for text, value in filters])
                active = [node for node in links if 'aria-current' in node.attrs]
                self.assertEqual([(node.text, node.attrs['aria-current']) for node in active],
                                 [(label, 'page')])
                for link in links:
                    self.assertEqual(link.ancestors[-1].tag, 'li')
                    self.assertIs(link.ancestors[-2], lists[0])

    def test_places_result_list_fields_and_single_detail_link(self):
        self.place.category = 'attraction'
        self.place.image_url = None
        page = self.page('/places')
        results = page.find('ul', **{'class': 'places-grid'})
        self.assertEqual(len(results), 1)
        articles = page.find('article')
        self.assertEqual(len(articles), 1)
        article = articles[0]
        self.assertEqual(article.ancestors[-1].tag, 'li')
        self.assertIs(article.ancestors[-2], results[0])
        self.assertEqual([node.text for node in page.find('p') if article in node.ancestors],
                         ['Attractions', self.place.address, self.place.description])
        headings = [node for node in page.find('h2') if article in node.ancestors]
        self.assertEqual([node.text for node in headings], [self.place.name])
        links = [node for node in page.find('a') if article in node.ancestors]
        self.assertEqual([(node.text, node.attrs['href']) for node in links],
                         [('View Details ' + chr(8594), '/places/synthetic-place'),
                          ('+ Add to Trip', '/user/trips/add-place/synthetic-place')])
        self.assertEqual(links[0].attrs['aria-label'], 'View details for ' + self.place.name)

    def test_places_excerpts_preserve_short_text_and_word_boundaries(self):
        for description in ('Short description.', 'a ' * 109 + 'ab',
                            'a ' * 109 + 'abc', 'Complete words for a long description. ' * 20):
            with self.subTest(length=len(description)):
                self.place.description = description
                page = self.page('/places')
                article = page.find('article')[0]
                excerpt = [node.text for node in page.find('p') if article in node.ancestors][-1]
                if len(description) <= 220:
                    self.assertEqual(excerpt, description)
                    self.assertFalse(excerpt.endswith('...'))
                else:
                    self.assertTrue(excerpt.endswith('...'))
                    self.assertLessEqual(len(excerpt), 220)
                    self.assertGreater(len(excerpt), 180)
                    self.assertTrue(description.startswith(excerpt[:-3] + ' '))
                detail = self.page('/places/synthetic-place')
                self.assertEqual(detail.find('p', **{'class': 'destination-description'})[0].text, description)

    def test_places_excerpt_escapes_untrusted_text_and_detail_keeps_full_text(self):
        unsafe = '<script>synthetic & text</script>'
        self.place.description = unsafe + ' ordinary words' * 40 + '\n<script>tail</script>'
        for path in ('/places', '/places/synthetic-place'):
            html = self.client.get(path).get_data(as_text=True)
            self.assertIn('&lt;script&gt;synthetic &amp; text&lt;/script&gt;', html)
            page = Document(html)
            assert_shared_scripts(self, page)
            if path == '/places':
                self.assertNotIn('&lt;script&gt;tail&lt;/script&gt;', html)
                self.assertIn('...', page.find('article')[0].text)
            else:
                self.assertIn('&lt;script&gt;tail&lt;/script&gt;', html)
                self.assertEqual(page.find('p', **{'class': 'destination-description'})[0].text, self.place.description)

    def test_detail_location_hierarchy_and_metadata_boundaries(self):
        self.place.image_url = None
        self.place.latitude, self.place.longitude = 14.123456, 121.654321
        self.place.id = 'private-place-id'
        self.place.created_at = self.place.updated_at = '2099-12-31T23:59:59Z'
        self.place.description = 'First paragraph.\nSecond paragraph.'
        self.place.category = 'attraction'
        page = self.page('/places/synthetic-place')
        article = page.find('article')[0]
        self.assertEqual([node.text for node in page.find('h1')], [self.place.name])
        self.assertEqual([node.text for node in page.find('h2') if page.find('main')[0] in node.ancestors], ['Private Notes'])
        table = page.find('table', **{'class': 'destination-facts'})[0]
        self.assertEqual([node.text for node in page.find('th') if table in node.ancestors], ['Address', 'Category', 'Environment'])
        self.assertEqual([node.text for node in page.find('td') if table in node.ancestors], [self.place.address, 'Attractions', 'Not recorded'])
        self.assertEqual(page.find('p', **{'class': 'destination-description'})[0].text, self.place.description)
        self.assertEqual(article.text.count(self.place.address), 1)
        self.assertEqual(len(page.find('a', **{'class': 'secondary-button back-link', 'href': '/places'})), 1)
        for path in ('/places', '/places/synthetic-place'):
            html = self.client.get(path).get_data(as_text=True)
            rendered = Document(html)
            for value in (str(self.place.latitude), str(self.place.longitude),
                          self.place.created_at, '/auth/status'):
                self.assertNotIn(value, html)
            assert_shared_scripts(self, rendered)
            images = rendered.find('img')
            self.assertEqual(len(images), 1)
            self.assertEqual(images[0].attrs['src'], '/static/img/destination-placeholder.svg')
            for tag in ('iframe', 'address', 'canvas'):
                self.assertEqual(rendered.find(tag), [])
            self.assertNotIn('leaflet', html.lower())
            if path.endswith('synthetic-place'):
                self.assertEqual(len(rendered.find('a', href='/map?destination=synthetic-place')), 1)
            self.assertNotRegex(rendered.find('main')[0].text.lower(),
                                r'ratings|opening hours|prices|reviews|amenities')

    def test_detail_content_back_link_and_escaping(self):
        unsafe = '<script>synthetic & text</script>'
        self.place.image_url = None
        self.place.name = self.place.address = self.place.description = unsafe
        for path in self.paths[1:]:
            page = self.page(path)
            assert_shared_scripts(self, page)
            self.assertIn(unsafe, page.find('main')[0].text)
            self.assertNotIn('images.invalid', page.find('body')[0].text)
        page = self.page('/places/synthetic-place')
        self.assertEqual(page.find('h1')[0].text, unsafe)
        self.assertEqual(len(page.find('a', **{'class': 'secondary-button back-link', 'href': '/places'})), 1)
        self.assertIn('Place Information', page.find('article')[0].text)

    def test_prototype_visuals_use_existing_images_or_shared_placeholder(self):
        for image_url in (None, '', 'javascript:alert(1)', 'https://images.invalid/existing.jpg'):
            self.place.image_url = image_url
            for path in ('/places', '/places/synthetic-place'):
                page = self.page(path)
                visuals = page.find('div', **{'class': 'destination-visual'})
                self.assertEqual(len(visuals), 1)
                images = page.find('img')
                if image_url and image_url.startswith('https://'):
                    self.assertEqual([n.attrs['src'] for n in images], [image_url])
                    self.assertEqual(images[0].attrs['alt'], self.place.name)
                    self.assertEqual(images[0].attrs['referrerpolicy'], 'no-referrer')
                    self.assertFalse([n for n in page.find('svg') if visuals[0] in n.ancestors])
                else:
                    self.assertEqual([n.attrs['src'] for n in images], ['/static/img/destination-placeholder.svg'])
                    self.assertIn('destination-photo-placeholder', images[0].attrs['class'])
                    self.assertTrue('unavailable' in images[0].attrs['alt'])
                self.assertIn('Nature', page.find('main')[0].text)
                assert_shared_scripts(self, page)
                for tag in ('iframe',):
                    self.assertEqual(page.find(tag), [])
                self.assertNotRegex(page.find('main')[0].text.lower(),
                                    r'ratings|reviews|stars|visitors|prices|opening hours|popular')
                for node in page.elements:
                    self.assertFalse(any(attr.lower().startswith('on') for attr in node.attrs))
        css = (ROOT / 'static/css/site.css').read_text(encoding='utf-8')
        self.assertNotRegex(css.lower(), r'https?://')
        self.assertIn('@import url("design-tokens.css")', css)

    def test_global_prototype_layout_uses_real_routes_and_data(self):
        for path in self.paths:
            page = self.page(path)
            body = page.find('body')[0]
            self.assertNotIn('data-presentation', body.attrs)
            self.assertTrue(page.find('header', **{'class': 'site-header'}))
            self.assertEqual(page.find('aside', **{'class': 'site-sidebar'}), [])
            if path.startswith('/places/'):
                self.assertFalse(page.find('nav', **{'aria-label': 'Breadcrumb'}))
                self.assertTrue(page.find('nav', **{'aria-label': 'Destination navigation'}))
            elif path == '/places':
                self.assertFalse(page.find('nav', **{'aria-label': 'Breadcrumb'}))
                self.assertIn('Explore Santa Rosa', page.find('h1')[0].text)
        self.assertEqual(self.client.get('/static/css/tourism.css').status_code, 200)
        css = (ROOT / 'static/css/tourism.css').read_text(encoding='utf-8')
        self.assertIn('grid-template-columns: 1.1fr 1fr', css)
        self.assertIn('@media (max-width: 860px)', css)
        self.assertNotRegex(css, r'@import|https?://|url\s*\(')
        for file in ('templates/places/list.html', 'templates/places/detail.html',
                     'templates/partials/place_visual.html'):
            template = (ROOT / file).read_text(encoding='utf-8')
            for sample in ('Enchanted Kingdom', 'Kanin Club', 'CIBO', 'localStorage', '#explore', 'Entrance cost'):
                self.assertNotIn(sample, template)

    def test_development_records_are_excluded_without_mutating_identifiers(self):
        self.place.slug = 'rosago-test-v1-nature'
        self.assertNotIn('rosago-test-v1-nature', self.client.get('/places').get_data(as_text=True))
        self.assertEqual(self.client.get('/places/rosago-test-v1-nature').status_code,404)
        self.assertEqual(self.place.slug,'rosago-test-v1-nature')
        self.place.slug = 'ordinary-place'
        self.assertEqual(self.client.get('/places/ordinary-place').status_code,200)

    def test_places_error_pages_preserve_status_and_safe_navigation(self):
        from places_service import PlacesUnavailableError, PlacesConsistencyError
        for path, method in (('/places', self.service.list_published),
                             ('/places/synthetic-place', self.service.get_published_by_slug)):
            for error, status in ((PlacesUnavailableError(), 503), (PlacesConsistencyError(), 500)):
                error.add_note('private-provider-message')
                method.side_effect = error
                response = self.client.get(path)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                html = response.get_data(as_text=True)
                self.assertNotIn('private-provider-message', html)
                page = Document(html)
                self.assertEqual(len(page.find('h1')), 1)
                self.assertEqual(len(page.find('main')), 1)
                self.assertIn('Back to Explore', page.find('main')[0].text)
                self.assertEqual(page.stack, [])
            method.side_effect = None

    def test_public_detail_add_link_preserves_public_boundary(self):
        page = self.page('/places/synthetic-place')
        self.assertEqual([node.text for node in page.find('a', href='/user/trips/add-place/synthetic-place')], ['Add to Trip'])
        main = page.find('main')[0]
        self.assertEqual([n.attrs for n in page.find('form') if main in n.ancestors], [{'data-place-note': self.place.id}])
        self.assertTrue(all(not node.attrs.get('value') for node in page.find('input', name='csrf_token')))
        self.assertEqual(page.find('input', name='trip_id'), [])

    def test_public_layout_does_not_lookup_or_mutate_auth_state(self):
        baseline = {path: self.client.get(path).data for path in self.paths[1:]}
        for state in ({'auth_session_id': 'stale-handle'},
                      {'user_id': 'legacy-user', 'user_email': 'private@example.invalid'}):
            with self.client.session_transaction() as session:
                session.update(state)
            for path in self.paths[1:]:
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
