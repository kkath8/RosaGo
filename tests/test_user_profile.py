"""Offline /user integration through the coordinator and real profile reader."""
from contextlib import contextmanager
import unittest
from unittest.mock import Mock, patch

from flask import before_render_template, g, session
import httpx
from jinja2 import ChoiceLoader, DictLoader, pass_context
from test_public_layout import Document

from normal_auth_coordinator import AuthenticatedContext, SessionBusy, ClientUnavailable
from normal_auth_flask import normal_authenticated
from profile_service import get_own_profile, ProfileConsistencyError, ProfileUnavailableError, UserProfile
import test_registration


def assert_account_layout(test, response, heading, active):
    test.assertEqual(response.status_code, 200)
    html = response.get_data(as_text=True)
    page = Document(html)
    test.assertEqual([node.text for node in page.find('h1')], [heading])
    test.assertEqual(len(page.find('main', id='main-content', tabindex='-1')), 1)
    test.assertEqual(len(page.find('main')), 1)
    test.assertEqual(page.find('a')[0].attrs['href'], '#main-content')
    test.assertEqual(len(page.find('footer')), 1)
    test.assertEqual([node.attrs['href'] for node in page.find('link', rel='stylesheet')],
                     ['/static/css/site.css'])
    nav = page.find('nav', **{'aria-label': 'Main navigation'})[0]
    links = [node for node in page.find('a') if nav in node.ancestors]
    test.assertEqual([(node.text.strip(), node.attrs['href']) for node in links],
                     [('Home', '/'), ('Explore', '/places'), ('Map', '/map'), ('Account', '/user')])
    test.assertEqual([(node.text.strip(), node.attrs['aria-current']) for node in links
                      if 'aria-current' in node.attrs], [('Account', active)])
    for tag in ('script', 'img', 'iframe'):
        test.assertEqual(page.find(tag), [])
    for value in ('/auth/status', 'fixture-access', 'fixture-refresh', 'fixture-session',
                  'user-123', 'sb_publishable_', 'supabase.co'):
        test.assertNotIn(value, html)
    test.assertEqual(page.stack, [])
    return page


def install_shared_isolation_probe(test):
    original = test.app.jinja_loader
    sources = {}
    observed = []
    for name in ('base.html', 'partials/navbar.html', 'partials/footer.html'):
        source = original.get_source(test.app.jinja_env, name)[0]
        sources[name] = '{{ shared_probe(' + repr(name) + ') }}' + source

    @pass_context
    def probe(context, name):
        test.assertNotIn('auth', g)
        test.assertFalse(test.owned[-1].is_closed)
        auth = (getattr(test, 'update', None) and test.update.call_args) or test.service.call_args
        authority = auth.args[0]
        for values in (context.get_all(), vars(g._get_current_object()), dict(session)):
            for key, value in values.items():
                test.assertNotIn(key, ('auth', 'client', 'access_token', 'refresh_token',
                                       'provider_session', 'claims'))
                test.assertNotIsInstance(value, AuthenticatedContext)
                test.assertIsNot(value, authority.client)
                if isinstance(value, str):
                    test.assertNotIn(value, ('fixture-access', 'fixture-refresh', 'fixture-session'))
        observed.append(name)
        return ''

    test.app.jinja_env.loader = ChoiceLoader([DictLoader(sources), original])
    test.app.jinja_env.globals['shared_probe'] = probe
    test.app.jinja_env.cache.clear()
    return observed


class UserProfileTests(unittest.TestCase):
    def setUp(self):
        test_registration.RegistrationTests.setUp(self)
        self.dependencies = self.app.extensions['rosago_normal_auth']
        self.requests, self.owned, self.events = [], [], []
        self.data = [dict(id='user-123', first_name=' Ana ', last_name=' Cruz ',
                          created_at='2026-10-10T01:02:03Z')]
        self.provider_status = 200
        self.provider_error = None
        self.route_globals = self.app.view_functions['user_index'].__wrapped__.__globals__
        self.service = Mock(side_effect=self.read_profile)
        service_patch = patch.dict(self.route_globals, get_own_profile=self.service)
        service_patch.start()
        self.addCleanup(service_patch.stop)
        self.dependencies.adapters._http_factory = self.http_factory

        @contextmanager
        def client(token):
            previous = g.get('auth')
            self.events.append('enter')
            try:
                with self.dependencies.adapters.database_client(token) as sdk:
                    owned = self.owned[-1]
                    yield sdk
            finally:
                self.assertIs(g.get('auth'), previous)
                self.assertTrue(owned.is_closed)
                self.events.append('close')
        self.dependencies.coordinator._clients = client

    def http_factory(self, **kwargs):
        http = httpx.Client(transport=httpx.MockTransport(self.provider), **kwargs)
        self.owned.append(http)
        return http

    def provider(self, request):
        self.assertIn('auth', g)
        self.assertFalse(self.owned[-1].is_closed)
        self.requests.append(request)
        self.events.append('query')
        if self.provider_error:
            raise self.provider_error
        return httpx.Response(self.provider_status, json=self.data)

    def read_profile(self, context):
        self.assertIs(context, g.auth)
        self.assertEqual(context.user_id, 'user-123')
        self.assertFalse(self.owned[-1].is_closed)
        self.events.append('service')
        return get_own_profile(context)

    def seed(self):
        return test_registration.seed_normal_session(self, 'verified@example.invalid')

    def assert_authority_preserved(self, handle):
        with self.client.session_transaction() as current:
            self.assertEqual(current['auth_session_id'], handle)
        self.assertIsNotNone(self.dependencies.store.resolve(handle))

    def tearDown(self):
        for http in self.owned:
            self.assertTrue(http.is_closed)
        self.supabase.assert_not_called()
        self.assertEqual(self.supabase.mock_calls, [])
        for request in self.requests:
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.path, '/rest/v1/profiles')
            self.assertEqual(dict(request.url.params), dict(
                select='id,first_name,last_name,created_at', id='eq.user-123', limit='2'))
            self.assertEqual(request.headers['Authorization'], 'Bearer fixture-access')
            self.assertEqual(request.headers['apikey'], 'sb_publishable_synthetic_test_fixture')
            self.assertEqual(request.headers['Accept-Profile'], 'public')

    def test_greeting_name_combinations_and_verified_email(self):
        self.seed()
        for first, last, greeting in (
            (' Ana ', ' Cruz ', 'Welcome, Ana Cruz'), ('Ana', None, 'Welcome, Ana'),
            (None, 'Cruz', 'Welcome, Cruz'), (None, None, 'Welcome to RosaGO'),
        ):
            with self.subTest(first=first, last=last):
                self.data[0].update(first_name=first, last_name=last, email='untrusted@example.invalid')
                response = self.client.get('/user')
                self.assertEqual(response.status_code, 200)
                self.assertIn(greeting.encode(), response.data)
                self.assertIn(b'Signed in as verified@example.invalid', response.data)
                self.assertNotIn(b'untrusted@example.invalid', response.data)
                self.assertNotIn(b'2026-10-10', response.data)
                self.assertNotIn(b'profile information is currently unavailable', response.data)
                self.assertIn(b'action="/logout"', response.data)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(len(self.requests), 4)

    def test_account_layout_edit_link_and_unchanged_post_logout(self):
        self.seed()
        page = assert_account_layout(self, self.client.get('/user'), 'Account', 'page')
        self.assertEqual([node.text for node in page.find('a', href='/user/profile/edit')],
                         ['Edit Profile'])
        forms = page.find('form')
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0].attrs['method'], 'post')
        self.assertEqual(forms[0].attrs['action'], '/logout')
        self.assertEqual(page.find('a', href='/logout'), [])
        buttons = page.find('button')
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].text, 'Logout')
        self.assertEqual(buttons[0].attrs['type'], 'submit')
        self.assertNotIn('name', buttons[0].attrs)
        self.assertIn(forms[0], buttons[0].ancestors)
        self.assertEqual(page.find('input'), [])
        self.service.assert_called_once()
        self.assertEqual(len(self.requests), 1)

    def test_shared_templates_have_no_auth_authority_or_extra_operations(self):
        self.seed()
        observed = install_shared_isolation_probe(self)
        with patch.object(self.dependencies.coordinator, 'authenticated',
                          wraps=self.dependencies.coordinator.authenticated) as authenticated:
            response = self.client.get('/user')
        self.assertEqual(response.status_code, 200)
        authenticated.assert_called_once()
        self.service.assert_called_once()
        self.assertEqual(observed, ['base.html', 'partials/navbar.html', 'partials/footer.html'])
        self.assertEqual(self.events, ['enter', 'service', 'query', 'close'])

    def test_missing_profile_is_200_without_logout_or_creation(self):
        handle = self.seed()
        self.data = []
        response = self.client.get('/user')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome to RosaGO', response.data)
        self.assertIn(b'Your profile information is currently unavailable.', response.data)
        self.assertIn(b'verified@example.invalid', response.data)
        self.assert_authority_preserved(handle)
        self.assertEqual(len(self.requests), 1)

    def test_browser_ids_and_legacy_email_cannot_control_lookup(self):
        self.seed()
        with self.client.session_transaction() as current:
            current.update(user_id='cookie-other', user_email='cookie@example.invalid')
        response = self.client.get('/user?user_id=query-other&profile_id=other',
                                   data={'user_id': 'form-other', 'email': 'form@example.invalid'})
        self.assertEqual(response.status_code, 200)
        self.service.assert_called_once()
        context = self.service.call_args.args[0]
        self.assertEqual(context.user_id, 'user-123')
        self.assertIn(b'Welcome, Ana Cruz', response.data)
        self.assertIn(b'verified@example.invalid', response.data)
        for value in (b'cookie-other', b'cookie@example.invalid', b'query-other', b'form@example.invalid'):
            self.assertNotIn(value, response.data)
        self.assertEqual(len(self.requests), 1)

    def test_unauthenticated_legacy_and_recovery_only_never_query(self):
        for data in ({}, {'user_id': 'user-123', 'user_email': 'legacy@example.invalid'},
                     {'pending_recovery_id': 'pending', 'password_recovery_id': 'grant'}):
            with self.client.session_transaction() as current:
                current.clear()
                current.update(data)
            response = self.client.get('/user')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['Location'], '/login?login_required=1')
        self.service.assert_not_called()
        self.assertEqual(self.owned, [])
        self.assertEqual(self.requests, [])

    def test_auth_entry_failures_do_not_call_profile_service(self):
        handle = self.seed()
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                response = self.client.get('/user')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers['Retry-After'], '1')
            self.assert_authority_preserved(handle)
        self.service.assert_not_called()
        self.assertEqual(self.owned, [])

    def test_provider_errors_are_sanitized_503_and_preserve_authority(self):
        handle = self.seed()
        for status in (403, 503):
            self.provider_status = status
            self.data = dict(code='42501', message='private-provider-detail',
                             details='fixture-access SQL-private', hint='private-hint')
            response = self.client.get('/user')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertNotIn('Location', response.headers)
            for value in (b'private', b'fixture-access', b'user-123', b'Ana'):
                self.assertNotIn(value, response.data)
            self.assert_authority_preserved(handle)
        self.assertEqual(len(self.requests), 2)

    def test_network_failure_is_sanitized_503(self):
        handle = self.seed()
        self.provider_error = httpx.ReadTimeout('fixture-access private-diagnostic')
        response = self.client.get('/user')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private', response.data)
        self.assertNotIn(b'fixture-access', response.data)
        self.assert_authority_preserved(handle)

    def test_malformed_duplicate_and_wrong_identity_are_generic_500(self):
        handle = self.seed()
        row = self.data[0]
        for data in ([row | {'id': 'wrong-private-id'}], [row, row],
                     [row | {'first_name': ['private-name']}], [{}]):
            self.data = data
            response = self.client.get('/user')
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            for value in (b'private', b'user-123', b'Ana', b'fixture-access'):
                self.assertNotIn(value, response.data)
            self.assert_authority_preserved(handle)

    def test_service_render_and_cleanup_order_and_minimal_template_contract(self):
        self.seed()
        original = self.route_globals['render_template']
        def render(template, **kwargs):
            self.assertNotIn('auth', g)
            self.assertFalse(self.owned[-1].is_closed)
            self.assertEqual(template, 'user/index.html')
            self.assertEqual(set(kwargs), {'profile', 'user_email'})
            self.assertIsInstance(kwargs['profile'], UserProfile)
            self.events.append('render')
            return original(template, **kwargs)
        with self.app.app_context():
            with patch.dict(self.route_globals, render_template=render):
                self.assertEqual(self.client.get('/user').status_code, 200)
            self.assertNotIn('auth', g)
        self.assertEqual(self.events, ['enter', 'service', 'query', 'render', 'close'])

    def install_isolation_probe(self, error=None):
        original = self.app.jinja_loader
        source, _, _ = original.get_source(self.app.jinja_env, 'user/index.html')
        # Execute inside Jinja, including its implicit global g, not a mocked
        # render_template call. The probe emits no credentials or diagnostics.
        probe = "{{ check_isolation(g, g.auth is undefined) }}"
        self.app.jinja_env.loader = ChoiceLoader([
            DictLoader({'user/index.html': probe + source}), original])
        self.app.jinja_env.cache.clear()
        def check_isolation(template_g, auth_undefined):
            self.assertTrue(auth_undefined)
            self.assertNotIn('auth', template_g)
            self.assertFalse(self.owned[-1].is_closed)
            self.events.append('jinja')
            if error is not None:
                raise error
            return ''
        self.app.jinja_env.globals['check_isolation'] = check_isolation

    def test_effective_template_context_excludes_auth_and_client(self):
        self.seed()
        self.install_isolation_probe()
        observed = []
        def inspect(sender, template, context, **extra):
            self.assertIs(context['g'], g._get_current_object())
            self.assertNotIn('auth', context['g'])
            self.assertNotIn('auth', self.app.jinja_env.globals['g'])
            self.assertIsInstance(context['profile'], UserProfile)
            self.assertEqual(context['user_email'], 'verified@example.invalid')
            auth = self.service.call_args.args[0]
            # Inspect effective context and request-local storage for aliases,
            # as well as the template's actual lookup above.
            for values in (context, vars(context['g']), dict(session)):
                for key, value in values.items():
                    self.assertNotIn(key, ('auth', 'client', 'access_token',
                                          'refresh_token', 'claims', 'provider_session'))
                    self.assertFalse(isinstance(value, AuthenticatedContext))
                    self.assertIsNot(value, auth.client)
                    if isinstance(value, str):
                        self.assertNotIn(value, ('fixture-access', 'fixture-refresh', 'fixture-session'))
            observed.append(True)
        with before_render_template.connected_to(inspect, self.app):
            response = self.client.get('/user')
        self.assertEqual(observed, [True])
        self.assertIn(b'Welcome, Ana Cruz', response.data)
        self.assertIn(b'verified@example.invalid', response.data)
        self.assertEqual(self.events, ['enter', 'service', 'query', 'jinja', 'close'])

    def test_actual_jinja_failure_propagates_and_cleans_up(self):
        self.seed()
        error = RuntimeError('template sentinel')
        self.install_isolation_probe(error)
        with self.app.app_context():
            with self.assertRaises(RuntimeError) as raised:
                self.client.get('/user')
            self.assertIs(raised.exception, error)
            self.assertNotIn('auth', g)
        self.assertEqual(self.events, ['enter', 'service', 'query', 'jinja', 'close'])

    def test_nested_auth_restored_after_render_success_and_failure(self):
        handle = self.seed()
        for error in (None, RuntimeError('nested template sentinel')):
            with self.subTest(failure=error is not None):
                self.install_isolation_probe(error)
                with self.app.test_request_context('/user'):
                    session['auth_session_id'] = handle
                    with normal_authenticated() as outer:
                        outer_http = self.owned[-1]
                        if error is None:
                            self.assertIn('Welcome, Ana Cruz', self.app.view_functions['user_index']())
                        else:
                            with self.assertRaises(RuntimeError) as raised:
                                self.app.view_functions['user_index']()
                            self.assertIs(raised.exception, error)
                        self.assertIs(g.auth, outer)
                        self.assertFalse(outer_http.is_closed)
                        self.assertTrue(self.owned[-1].is_closed)
                    self.assertNotIn('auth', g)
                    self.assertTrue(outer_http.is_closed)

    def test_names_are_escaped_and_no_credentials_are_rendered(self):
        self.seed()
        self.data[0].update(first_name='<script>alert(1)</script>', last_name=None)
        response = self.client.get('/user')
        self.assertIn(b'&lt;script&gt;', response.data)
        self.assertNotIn(b'<script>', response.data)
        for value in (b'fixture-access', b'fixture-refresh', b'fixture-session', b'user-123'):
            self.assertNotIn(value, response.data)

    def test_unrelated_service_programming_error_propagates_and_cleans_up(self):
        self.seed()
        error = RuntimeError('application sentinel')
        self.service.side_effect = error
        with self.app.app_context():
            with self.assertRaises(RuntimeError) as raised:
                self.client.get('/user')
            self.assertIs(raised.exception, error)
            self.assertNotIn('auth', g)
        self.assertEqual(self.events, ['enter', 'close'])

    def test_template_errors_including_profile_error_types_propagate(self):
        self.seed()
        for error in (RuntimeError('template sentinel'), ProfileConsistencyError(), ProfileUnavailableError()):
            with patch.dict(self.route_globals, render_template=Mock(side_effect=error)):
                with self.assertRaises(type(error)) as raised:
                    self.client.get('/user')
                self.assertIs(raised.exception, error)


if __name__ == '__main__':
    unittest.main()
