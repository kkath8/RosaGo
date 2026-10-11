"""Offline edit routes through real auth scopes, profile services and SDK transport."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from flask import before_render_template, g, session
import httpx
from jinja2 import ChoiceLoader, DictLoader
from werkzeug.datastructures import MultiDict

from normal_auth_coordinator import AuthenticatedContext, SessionBusy, ClientUnavailable
from normal_auth_flask import normal_authenticated
from normal_auth_store import NormalAuthSession
from profile_service import update_own_profile, ProfileConsistencyError, ProfileUnavailableError
import test_user_profile
from test_public_layout import Document


class UserProfileEditTests(unittest.TestCase):
    path = '/user/profile/edit'
    http_factory = test_user_profile.UserProfileTests.http_factory
    read_profile = test_user_profile.UserProfileTests.read_profile
    seed = test_user_profile.UserProfileTests.seed
    assert_authority_preserved = test_user_profile.UserProfileTests.assert_authority_preserved

    def setUp(self):
        test_user_profile.UserProfileTests.setUp(self)
        self.update = Mock(side_effect=self.write_profile)
        edit_patch = patch.dict(self.route_globals, update_own_profile=self.update)
        edit_patch.start()
        self.addCleanup(edit_patch.stop)
        self.handle = self.seed()
        self.csrf = self.dependencies.store.resolve(self.handle).csrf

    def write_profile(self, context, **values):
        self.assertIs(context, g.auth)
        self.assertEqual(context.user_id, 'user-123')
        self.assertEqual(set(values), {'first_name', 'last_name'})
        self.assertFalse(self.owned[-1].is_closed)
        self.events.append('update')
        return update_own_profile(context, **values)

    def provider(self, request):
        self.assertIn('auth', g)
        self.assertFalse(self.owned[-1].is_closed)
        self.requests.append(request)
        self.events.append(request.method)
        if self.provider_error:
            raise self.provider_error
        if request.method == 'PATCH' and self.provider_status == 200 and self.data:
            self.data = [self.data[0] | json.loads(request.content)]
        return httpx.Response(self.provider_status, json=self.data)

    def tearDown(self):
        self.supabase.assert_not_called()
        self.assertEqual(self.supabase.mock_calls, [])
        for http in self.owned:
            self.assertTrue(http.is_closed)
        for request in self.requests:
            self.assertIn(request.method, ('GET', 'PATCH'))
            self.assertEqual(request.url.path, '/rest/v1/profiles')
            expected = dict(id='eq.user-123', select='id,first_name,last_name,created_at')
            if request.method == 'GET':
                expected['limit'] = '2'
            else:
                self.assertEqual(set(json.loads(request.content)), {'first_name', 'last_name'})
                self.assertIn('return=representation', request.headers['Prefer'])
            self.assertEqual(dict(request.url.params), expected)
            self.assertEqual(request.headers['Authorization'], 'Bearer fixture-access')
            self.assertEqual(request.headers['apikey'], 'sb_publishable_synthetic_test_fixture')

    def form(self, **changes):
        return dict(csrf_token=self.csrf, first_name='Ana', last_name='Cruz') | changes

    def assert_protected(self, response):
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')

    def assert_no_profile_operation(self):
        self.service.assert_not_called()
        self.update.assert_not_called()
        self.assertEqual(self.requests, [])

    def test_get_prepopulates_verified_values_and_csrf(self):
        self.data[0]['email'] = 'untrusted@example.invalid'
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        for expected in ('value="Ana"', 'value="Cruz"', 'name="csrf_token"',
                         'value="' + self.csrf + '"', 'verified@example.invalid'):
            self.assertIn(expected.encode(), response.data)
        for secret in ('fixture-access', 'fixture-refresh', 'fixture-session',
                       'user-123', self.handle, '2026-10-10', 'untrusted@example.invalid'):
            self.assertNotIn(secret.encode(), response.data)
        self.assert_protected(response)
        self.service.assert_called_once()
        self.update.assert_not_called()
        self.assertIn(b'href="/user/profile/edit"', self.client.get('/user').data)

    def test_shared_edit_layout_referrer_and_exact_form_contract(self):
        response = self.client.get(self.path)
        page = test_user_profile.assert_account_layout(self, response, 'Edit Profile', 'true')
        self.assert_protected(response)
        self.assertEqual(len(page.find('meta', name='referrer', content='same-origin')), 1)
        forms = page.find('form')
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0].attrs, {'method': 'post', 'action': self.path})
        inputs = page.find('input')
        self.assertEqual([node.attrs['name'] for node in inputs],
                         ['csrf_token', 'first_name', 'last_name'])
        csrf = page.find('input', name='csrf_token')
        self.assertEqual(len(csrf), 1)
        self.assertEqual(csrf[0].attrs['type'], 'hidden')
        self.assertEqual(csrf[0].attrs['value'], self.csrf)
        guidance = page.find('p', id='name-guidance')
        self.assertEqual([node.text for node in guidance],
                         ['Names may be blank. Use up to 100 characters per name.'])
        for field, field_id, autocomplete, value, label in (
            ('first_name', 'first-name', 'given-name', 'Ana', 'First Name'),
            ('last_name', 'last-name', 'family-name', 'Cruz', 'Last Name'),
        ):
            node = page.find('input', name=field)[0]
            self.assertEqual(node.attrs['id'], field_id)
            self.assertEqual(node.attrs['autocomplete'], autocomplete)
            self.assertEqual(node.attrs['value'], value)
            self.assertEqual(node.attrs['aria-describedby'], 'name-guidance')
            self.assertEqual([n.text for n in page.find('label', **{'for': field_id})], [label])
            for attr in ('required', 'maxlength', 'autofocus', 'aria-invalid'):
                self.assertNotIn(attr, node.attrs)
        for node in inputs:
            self.assertIn(forms[0], node.ancestors)
        buttons = page.find('button')
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].text, 'Save Changes')
        self.assertEqual(buttons[0].attrs['type'], 'submit')
        self.assertNotIn('name', buttons[0].attrs)
        self.assertIn(forms[0], buttons[0].ancestors)
        self.assertEqual([node.text for node in page.find('a', href='/user')
                          if forms[0].ancestors[-1] in node.ancestors], ['Cancel / Back to profile'])
        self.service.assert_called_once()
        self.update.assert_not_called()

    def test_shared_edit_templates_isolate_auth_on_get_and_validation_error(self):
        observed = test_user_profile.install_shared_isolation_probe(self)
        for method, expected_status in (('GET', 200), ('POST', 400)):
            observed.clear()
            self.service.reset_mock()
            self.update.reset_mock()
            before = len(self.requests)
            with patch.object(self.dependencies.coordinator, 'authenticated',
                              wraps=self.dependencies.coordinator.authenticated) as authenticated:
                response = self.client.open(self.path, method=method,
                                            data=self.form(first_name='x' * 101))
            self.assertEqual(response.status_code, expected_status)
            authenticated.assert_called_once()
            self.assertEqual(observed, ['base.html', 'partials/navbar.html', 'partials/footer.html'])
            if method == 'GET':
                self.service.assert_called_once()
                self.update.assert_not_called()
                self.assertEqual(len(self.requests), before + 1)
            else:
                self.service.assert_not_called()
                self.update.assert_called_once()
                self.assertEqual(len(self.requests), before)

    def test_edit_feedback_roles_and_blank_values(self):
        self.data[0].update(first_name=None, last_name=None)
        page = Document(self.client.get(self.path).get_data(as_text=True))
        for field in ('first_name', 'last_name'):
            self.assertEqual(page.find('input', name=field)[0].attrs['value'], '')
        response = self.client.post(self.path, data=self.form(first_name='x' * 101))
        self.assertEqual(response.status_code, 400)
        page = Document(response.get_data(as_text=True))
        self.assertEqual([node.text for node in page.find('p', role='alert')],
                         ['Use names of at most 100 characters without control characters. Names may be blank.'])
        self.assertEqual(page.find('input', name='first_name')[0].attrs['value'], 'x' * 101)
        response = self.client.post(self.path, data=self.form())
        self.assertEqual(response.status_code, 303)
        page = Document(self.client.get(self.path).get_data(as_text=True))
        self.assertEqual([node.text for node in page.find('p', role='status')], ['Profile updated.'])
        self.assertEqual(page.find('p', role='alert'), [])

    def test_success_redirect_flash_and_exactly_one_update(self):
        for headers in ({}, {'Origin': 'http://localhost'}):
            self.requests.clear()
            self.update.reset_mock()
            self.service.reset_mock()
            response = self.client.post(self.path, data=self.form(first_name=" Ana-María ", last_name=" O'Neill "), headers=headers)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers['Location'], self.path)
            self.assert_protected(response)
            self.update.assert_called_once()
            self.service.assert_not_called()
            self.assertEqual([r.method for r in self.requests], ['PATCH'])
            self.assertEqual(json.loads(self.requests[0].content), dict(first_name='Ana-María', last_name="O'Neill"))
            page = self.client.get(self.path)
            self.assertIn(b'Profile updated.', page.data)
            self.assertEqual([r.method for r in self.requests], ['PATCH', 'GET'])
            self.assertNotIn(b'Profile updated.', self.client.get(self.path).data)

    def test_blank_names_become_null(self):
        response = self.client.post(self.path, data=self.form(first_name=' \t ', last_name=''))
        self.assertEqual(response.status_code, 303)
        self.assertEqual(json.loads(self.requests[0].content), dict(first_name=None, last_name=None))

    def test_csrf_failures_precede_all_profile_operations(self):
        other_handle = self.seed()
        other_csrf = self.dependencies.store.resolve(other_handle).csrf
        with self.client.session_transaction() as current:
            current['auth_session_id'] = self.handle
        cases = [MultiDict([('first_name', 'Ana'), ('last_name', 'Cruz')])]
        cases += [self.form(csrf_token=token) for token in ('', ' ', 'invalid', other_csrf)]
        duplicate = MultiDict(self.form())
        duplicate.add('csrf_token', self.csrf)
        cases.append(duplicate)
        for data in cases:
            response = self.client.post(self.path, data=data)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(self.csrf.encode(), response.data)
            self.assertNotIn(other_csrf.encode(), response.data)
            self.assert_protected(response)
            self.assert_authority_preserved(self.handle)
        self.assert_no_profile_operation()

    def test_origin_rejections_precede_profile_operations(self):
        for origin in ('https://foreign.invalid', 'null', 'garbage', '',
                       'http://localhost.evil.invalid', 'http://localhost/path',
                       'http://localhost, https://foreign.invalid'):
            response = self.client.post(self.path, data=self.form(), headers={'Origin': origin})
            self.assertEqual(response.status_code, 403)
            self.assert_protected(response)
        self.assert_no_profile_operation()

    def test_strict_form_shape_rejects_missing_duplicates_extras_and_files(self):
        cases = []
        for field in ('first_name', 'last_name'):
            missing = self.form()
            del missing[field]
            cases.append(missing)
            duplicate = MultiDict(self.form())
            duplicate.add(field, 'other')
            cases.append(duplicate)
        for field in ('id', 'user_id', 'email', 'role', 'created_at', 'auth_session_id', 'unexpected'):
            cases.append(self.form(**{field: 'untrusted'}))
        cases.append(self.form(upload=(io.BytesIO(b'fixture'), 'avatar.txt')))
        for data in cases:
            response = self.client.post(self.path, data=data)
            self.assertEqual(response.status_code, 400)
            self.assert_protected(response)
        self.assert_no_profile_operation()

    def test_invalid_names_redisplay_escaped_without_database_operation(self):
        for name in ('x' * 101, 'A\x00B', 'A\tB', 'A\nB'):
            response = self.client.post(self.path, data=self.form(first_name=name, last_name='<script>bad</script>'))
            self.assertEqual(response.status_code, 400)
            self.assertIn(b'&lt;script&gt;', response.data)
            self.assertNotIn(b'<script>', response.data)
            self.assertIn(b'name="csrf_token"', response.data)
            self.assert_protected(response)
        self.assertEqual(self.requests, [])
        self.service.assert_not_called()

    def test_unauthenticated_legacy_and_recovery_only_cannot_edit(self):
        for state in ({}, {'user_id': 'other', 'user_email': 'legacy@example.invalid'},
                      {'pending_recovery_id': 'pending', 'password_recovery_id': 'grant'}):
            with self.client.session_transaction() as current:
                current.clear()
                current.update(state)
            for method in ('GET', 'POST'):
                response = self.client.open(self.path, method=method, data=self.form())
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers['Location'], '/login?login_required=1')
                self.assert_protected(response)
        self.assert_no_profile_operation()

    def test_busy_unavailable_never_call_profile(self):
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                for method in ('GET', 'POST'):
                    response = self.client.open(self.path, method=method, data=self.form())
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.headers['Retry-After'], '1')
                    self.assert_protected(response)
        self.assert_no_profile_operation()
        self.assert_authority_preserved(self.handle)

    def test_legacy_cookie_and_query_identity_cannot_change_target(self):
        with self.client.session_transaction() as current:
            current.update(user_id='other', user_email='legacy@example.invalid')
        response = self.client.post(self.path + '?user_id=other&id=other', data=self.form())
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.update.call_args.args[0].user_id, 'user-123')
        page = self.client.get(self.path + '?id=other')
        self.assertIn(b'verified@example.invalid', page.data)
        self.assertNotIn(b'legacy@example.invalid', page.data)

    def test_missing_profile_get_and_post_preserve_session(self):
        self.data = []
        for method in ('GET', 'POST'):
            response = self.client.open(self.path, method=method, data=self.form())
            self.assertEqual(response.status_code, 404)
            self.assert_authority_preserved(self.handle)
            self.assert_protected(response)
        self.assertEqual([r.method for r in self.requests], ['GET', 'PATCH'])

    def test_provider_network_and_consistency_errors_are_safe(self):
        for method in ('GET', 'POST'):
            for mode in ('provider', 'network', 'consistency'):
                self.provider_status = 503 if mode == 'provider' else 200
                self.provider_error = httpx.ReadTimeout('fixture-access private-detail') if mode == 'network' else None
                self.data = (dict(code='503', message='private-detail', details='fixture-access', hint='SQL-private')
                             if mode == 'provider' else [dict(id='wrong-private-id', first_name='Ana', last_name='Cruz', created_at='bad')])
                before = len(self.requests)
                response = self.client.open(self.path, method=method, data=self.form())
                self.assertEqual(response.status_code, 500 if mode == 'consistency' else 503)
                self.assertEqual(len(self.requests), before + 1)
                for secret in (b'private', b'fixture-access', b'SQL'):
                    self.assertNotIn(secret, response.data)
                if method == 'POST' and mode != 'consistency':
                    self.assertIn(b'save could not be confirmed', response.data)
                self.assert_protected(response)
                self.assert_authority_preserved(self.handle)

    def install_probe(self, error=None):
        original = self.app.jinja_loader
        source, _, _ = original.get_source(self.app.jinja_env, 'user/profile_edit.html')
        self.app.jinja_env.loader = ChoiceLoader([
            DictLoader({'user/profile_edit.html': '{{ probe(g, g.auth is undefined) }}' + source}), original])
        self.app.jinja_env.cache.clear()
        def probe(template_g, undefined):
            self.assertTrue(undefined)
            self.assertNotIn('auth', template_g)
            self.assertFalse(self.owned[-1].is_closed)
            self.events.append('render')
            if error is not None:
                raise error
            return ''
        self.app.jinja_env.globals['probe'] = probe

    def test_effective_jinja_context_get_and_validation_error(self):
        self.install_probe()
        observed = []
        def inspect(sender, template, context, **extra):
            self.assertNotIn('auth', context['g'])
            self.assertEqual(context['csrf'], self.csrf)
            self.assertEqual(context['user_email'], 'verified@example.invalid')
            self.assertIsInstance(context['first_name'], str)
            self.assertIsInstance(context['last_name'], str)
            for values in (context, vars(context['g']), dict(session)):
                for value in values.values():
                    self.assertFalse(isinstance(value, (AuthenticatedContext, NormalAuthSession)))
                    auth = (self.update.call_args or self.service.call_args).args[0]
                    self.assertIsNot(value, auth.client)
                    if isinstance(value, str):
                        self.assertNotIn(value, ('fixture-access', 'fixture-refresh', 'fixture-session'))
            observed.append(True)
        with before_render_template.connected_to(inspect, self.app):
            self.assertEqual(self.client.get(self.path).status_code, 200)
            self.assertEqual(self.events, ['enter', 'service', 'GET', 'render', 'close'])
            self.events.clear()
            self.assertEqual(self.client.post(self.path, data=self.form(first_name='x' * 101)).status_code, 400)
            self.assertEqual(self.events, ['enter', 'update', 'render', 'close'])
        self.assertEqual(observed, [True, True])

    def test_jinja_exception_propagates_and_cleans_up(self):
        for error in (RuntimeError('template sentinel'), ProfileConsistencyError(), ProfileUnavailableError()):
            self.install_probe(error)
            for method in ('GET', 'POST'):
                with self.app.app_context():
                    with self.assertRaises(type(error)) as raised:
                        self.client.open(self.path, method=method, data=self.form(first_name='x' * 101))
                    self.assertIs(raised.exception, error)
                    self.assertNotIn('auth', g)
                self.assertTrue(self.owned[-1].is_closed)

    def test_nested_auth_restored_after_render_success_and_exception(self):
        for error in (None, RuntimeError('template sentinel')):
            self.install_probe(error)
            for method in ('GET', 'POST'):
                with self.app.test_request_context(self.path, method=method, data=self.form(first_name='x' * 101)):
                    session['auth_session_id'] = self.handle
                    with normal_authenticated() as outer:
                        outer_http = self.owned[-1]
                        if error is None:
                            self.app.view_functions['user_profile_edit']()
                        else:
                            with self.assertRaises(RuntimeError) as raised:
                                self.app.view_functions['user_profile_edit']()
                            self.assertIs(raised.exception, error)
                        self.assertIs(g.auth, outer)
                        self.assertFalse(outer_http.is_closed)
                        self.assertTrue(self.owned[-1].is_closed)
                    self.assertNotIn('auth', g)
                    self.assertTrue(outer_http.is_closed)

    def test_service_programming_errors_propagate(self):
        for method, service in (('GET', self.service), ('POST', self.update)):
            error = RuntimeError('application sentinel')
            service.side_effect = error
            with self.app.app_context():
                with self.assertRaises(RuntimeError) as raised:
                    self.client.open(self.path, method=method, data=self.form())
                self.assertIs(raised.exception, error)
                self.assertNotIn('auth', g)


if __name__ == '__main__':
    unittest.main()
