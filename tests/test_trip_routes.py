"""Protected Trip CRUD through real auth scopes and offline service doubles."""
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from datetime import date, datetime, timezone
import io
import time
import unittest
from unittest.mock import Mock, patch

from flask import before_render_template, g
from jinja2 import ChoiceLoader, DictLoader
from werkzeug.datastructures import MultiDict

from normal_auth_coordinator import AuthenticatedContext, SessionBusy, ClientUnavailable
from normal_auth_flask import normal_authenticated
from normal_auth_store import NormalAuthSession
from trip_service import (Trip, TripDetail, TripPlace, TripValidationError, TripNotFoundError,
                          TripOperationRejectedError, TripUnavailableError, TripConsistencyError)
from test_public_layout import Document
import test_registration


OWNER = '00000000-0000-0000-0000-000000000001'
TRIP = 'aaaaaaaa-0000-0000-0000-000000000002'
ROOT = '/user/trips'
DETAIL = ROOT + '/' + TRIP
ROUTES = [('GET', ROOT), ('GET', ROOT + '/new'), ('POST', ROOT), ('GET', DETAIL),
          ('GET', DETAIL + '/edit'), ('POST', DETAIL + '/edit'), ('POST', DETAIL + '/delete')]


class TripRouteTests(unittest.TestCase):
    def setUp(self):
        # Includes socket guards, isolated application loading and fake config.
        test_registration.RegistrationTests.setUp(self)
        self.dependencies = self.app.extensions['rosago_normal_auth']
        self.owned = []
        @contextmanager
        def clients(token):
            client = Mock(spec=['table', 'rpc', 'close'])
            self.owned.append(client)
            try:
                yield client
            finally:
                client.close()
        self.dependencies.coordinator._clients = clients
        self.handle = self.seed()
        self.csrf = self.dependencies.store.resolve(self.handle).csrf
        stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.trip = Trip(TRIP, 'My <trip>', date(2020, 1, 2), stamp, stamp)
        self.detail = TripDetail(self.trip, (TripPlace(TRIP, OWNER, 3, stamp, None),), 3)
        self.services = {}
        results = {'list_user_trips': (self.trip,), 'get_user_trip': self.detail,
                   'create_trip': self.trip, 'update_trip': self.trip, 'delete_trip': None, 'add_place': None}
        for name, result in results.items():
            def operation(context, *args, result=result, **kwargs):
                self.assertIs(context, g.auth)
                self.assertEqual(context.user_id, OWNER)
                self.assertIs(context.client, self.owned[-1])
                context.client.close.assert_not_called()
                return result
            self.services[name] = Mock(side_effect=operation)
        namespace = self.app.view_functions['trips_list'].__wrapped__.__globals__
        guard = patch.dict(namespace, self.services)
        guard.start(); self.addCleanup(guard.stop)

    def seed(self):
        handle = self.dependencies.store.create(user_id=OWNER, user_email='fixture@example.invalid',
            access_token='private-access', refresh_token='private-refresh',
            access_expires_at=time.time() + 3600, session_id='private-provider-session')
        with self.client.session_transaction() as session:
            session['auth_session_id'] = handle
        return handle

    def tearDown(self):
        self.assertEqual(self.supabase.mock_calls, [])
        for client in self.owned:
            client.close.assert_called_once()
            client.table.assert_not_called()
            client.rpc.assert_not_called()

    def form(self, path, **changes):
        fields = {'csrf_token': self.csrf}
        if not path.endswith('/delete'):
            fields.update(name='Visit', visit_date='')
        return fields | changes

    def protected(self, response):
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')

    def untouched(self):
        for service in self.services.values():
            service.assert_not_called()

    def test_every_route_requires_normal_auth(self):
        for state in ({}, {'user_id': OWNER, 'user_email': 'fake'}, {'password_recovery_id': 'grant'}):
            with self.client.session_transaction() as session:
                session.clear(); session.update(state)
            for method, path in ROUTES:
                response = self.client.open(path, method=method, data=self.form(path))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers['Location'], '/login?login_required=1')
                self.protected(response)
        self.untouched()

    def test_busy_and_unavailable_prevent_service_calls(self):
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                for method, path in ROUTES:
                    response = self.client.open(path, method=method, data=self.form(path))
                    self.assertEqual(response.status_code, 503)
                    self.protected(response)
        self.untouched()
        self.assertIsNotNone(self.dependencies.store.resolve(self.handle))

    def test_reads_forms_account_link_and_unavailable_place(self):
        for path in (ROOT, ROOT + '/new', DETAIL, DETAIL + '/edit'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.protected(response)
            self.assertIn(b'/static/css/site.css', response.data)
            label = 'Planner' if path == ROOT + '/new' else 'My Trips'
            state = 'page' if path in (ROOT, ROOT + '/new') else 'true'
            self.assertIn(f'aria-current="{state}">{label}'.encode(), response.data)
        self.assertEqual(self.services['list_user_trips'].call_args.kwargs, {'limit': 50, 'offset': 0})
        detail = self.client.get(DETAIL)
        self.assertIn(b'Place unavailable', detail.data)
        self.assertNotIn(OWNER.encode(), detail.data)
        self.assertIn(b'My &lt;trip&gt;', detail.data)
        self.assertNotIn(b'draft', detail.data)
        self.assertNotIn(b'archived', detail.data)
        edit = self.client.get(DETAIL + '/edit')
        self.assertIn(b'value="2020-01-02"', edit.data)
        self.assertIn(self.csrf.encode(), edit.data)
        source = self.app.jinja_loader.get_source(self.app.jinja_env, 'user/index.html')[0]
        self.assertIn('My Trips', source)

    def test_successful_mutations_once_dates_origins_and_redirects(self):
        for path, service_name, target in ((ROOT, 'create_trip', DETAIL),
                (DETAIL + '/edit', 'update_trip', DETAIL), (DETAIL + '/delete', 'delete_trip', ROOT)):
            service = self.services[service_name]
            for headers in ({}, {'Origin': 'http://localhost'}):
                for value, expected in (('', None), ('0001-01-01', date.min)):
                    service.reset_mock()
                    data = self.form(path)
                    if 'visit_date' in data:
                        data['visit_date'] = value
                    response = self.client.post(path.replace('aaaaaaaa', 'AAAAAAAA'), data=data, headers=headers)
                    self.assertEqual(response.status_code, 303)
                    self.assertEqual(response.headers['Location'], target)
                    self.protected(response)
                    service.assert_called_once()
                    self.assertEqual(service.call_args.args[1:], () if path == ROOT else (TRIP,))
                    self.assertEqual(service.call_args.kwargs, {} if path.endswith('/delete')
                                     else {'name': 'Visit', 'visit_date': expected})

    def test_csrf_failures_and_wrong_session(self):
        other = self.seed()
        wrong = self.dependencies.store.resolve(other).csrf
        with self.client.session_transaction() as session:
            session['auth_session_id'] = self.handle
        for path in (ROOT, DETAIL + '/edit', DETAIL + '/delete'):
            cases = [self.form(path, csrf_token=value) for value in ('', ' ', 'invalid', wrong)]
            missing = self.form(path); del missing['csrf_token']; cases.append(missing)
            duplicate = MultiDict(self.form(path)); duplicate.add('csrf_token', self.csrf); cases.append(duplicate)
            for data in cases:
                response = self.client.post(path, data=data)
                self.assertEqual(response.status_code, 403)
                self.protected(response)
        self.untouched()

    def test_origin_rejected_before_services(self):
        for path in (ROOT, DETAIL + '/edit', DETAIL + '/delete'):
            for origin in ('null', 'https://foreign.invalid', '', 'http://localhost.evil', 'http://localhost/path'):
                response = self.client.post(path, data=self.form(path), headers={'Origin': origin})
                self.assertEqual(response.status_code, 403)
                self.protected(response)
        self.untouched()

    def test_exact_forms_missing_duplicate_extra_and_upload(self):
        for path in (ROOT, DETAIL + '/edit', DETAIL + '/delete'):
            cases = []
            for field in set(self.form(path)) - {'csrf_token'}:
                missing = self.form(path); del missing[field]; cases.append(missing)
                duplicate = MultiDict(self.form(path)); duplicate.add(field, 'extra'); cases.append(duplicate)
            for field in ('user_id', 'owner', 'email', 'access_token', 'auth_session_id', 'client', 'extra'):
                cases.append(self.form(path, **{field: 'untrusted'}))
            cases.append(self.form(path, upload=(io.BytesIO(b'file'), 'file.txt')))
            for data in cases:
                response = self.client.post(path, data=data)
                self.assertEqual(response.status_code, 400)
                self.protected(response)
        self.untouched()

    def test_invalid_dates_never_call_service_and_redisplay_escaped(self):
        for path in (ROOT, DETAIL + '/edit'):
            for value in (' ', '20260101', '2026-1-01', '2026-02-30', '2026-01-01T00:00:00', '2026-01-01 '):
                response = self.client.post(path, data=self.form(path, name='<script>x</script>', visit_date=value))
                self.assertEqual(response.status_code, 400)
                self.assertIn(b'&lt;script&gt;', response.data)
                self.assertNotIn(b'<script>', response.data)
                self.protected(response)
        self.untouched()

    def test_service_errors_are_fixed_and_mutations_not_replayed(self):
        for method, path, name in [('GET', ROOT, 'list_user_trips'), ('GET', DETAIL, 'get_user_trip'),
                ('GET', DETAIL + '/edit', 'get_user_trip'), ('POST', ROOT, 'create_trip'),
                ('POST', DETAIL + '/edit', 'update_trip'), ('POST', DETAIL + '/delete', 'delete_trip')]:
            service = self.services[name]
            original = service.side_effect
            for error_type, status in ((TripValidationError, 400), (TripNotFoundError, 404),
                    (TripOperationRejectedError, 400), (TripUnavailableError, 503), (TripConsistencyError, 500)):
                error = error_type(); error.args = ('private-provider-message private-access',)
                service.side_effect = error; service.reset_mock()
                response = self.client.open(path, method=method, data=self.form(path))
                self.assertEqual(response.status_code, status)
                self.assertNotIn(b'private-', response.data)
                if method == 'POST' and status == 503:
                    self.assertIn(b'could not be confirmed', response.data)
                self.protected(response); service.assert_called_once()
            service.side_effect = original

    def test_missing_and_foreign_same_not_found(self):
        service = self.services['get_user_trip']
        for path in (DETAIL, DETAIL + '/edit'):
            service.side_effect = None; service.return_value = None
            missing = self.client.get(path)
            service.side_effect = TripNotFoundError()
            foreign = self.client.get(path)
            self.assertEqual((missing.status_code, missing.data), (404, b'Trip not found.'))
            self.assertEqual((foreign.status_code, foreign.data), (missing.status_code, missing.data))

    def test_uuid_method_errors_and_pagination(self):
        for method, path, status in [('GET', ROOT + '/bad', 404), ('POST', ROOT + '/bad/edit', 404),
                                   ('GET', DETAIL + '/delete', 405), ('POST', ROOT + '/new', 405)]:
            response = self.client.open(path, method=method)
            self.assertEqual(response.status_code, status); self.protected(response)
        self.untouched()
        for path in (ROOT + '?offset=-1', ROOT + '?offset=1&offset=2', ROOT + '?offset=2147483647',
                     DETAIL + '?after_position=2147483648', DETAIL + '?after_position=x'):
            self.assertEqual(self.client.get(path).status_code, 400)
        self.untouched()
        self.client.get(ROOT + '?offset=50&user_id=foreign')
        self.assertEqual(self.services['list_user_trips'].call_args.kwargs, {'limit': 50, 'offset': 50})
        self.client.get(DETAIL + '?after_position=3&owner=foreign')
        self.assertEqual(self.services['get_user_trip'].call_args.kwargs, {'membership_limit': 50, 'after_position': 3})

    def test_templates_isolate_authority_on_success_and_validation(self):
        observed = []
        def inspect(sender, template, context, **extra):
            self.assertNotIn('auth', g)
            for value in context.values():
                self.assertNotIsInstance(value, (AuthenticatedContext, NormalAuthSession))
                self.assertTrue(all(value is not client for client in self.owned))
            observed.append(template.name)
        original = self.app.jinja_loader
        sources = {}
        for name in ('base.html', 'partials/navbar.html', 'partials/footer.html'):
            sources[name] = '{{ probe() }}' + original.get_source(self.app.jinja_env, name)[0]
        def probe():
            self.assertNotIn('auth', g)
            return ''
        self.app.jinja_env.loader = ChoiceLoader([DictLoader(sources), original])
        self.app.jinja_env.globals['probe'] = probe
        self.app.jinja_env.cache.clear()
        with before_render_template.connected_to(inspect, self.app):
            for path in (ROOT, ROOT + '/new', DETAIL, DETAIL + '/edit'):
                response = self.client.get(path)
                for secret in ('private-access', 'private-refresh', 'private-provider-session', self.handle, OWNER):
                    self.assertNotIn(secret.encode(), response.data)
            for path in (ROOT, DETAIL + '/edit'):
                self.assertEqual(self.client.post(path, data=self.form(path, visit_date='bad')).status_code, 400)
        self.assertEqual(len(observed), 6)

    def test_render_failure_restores_outer_context(self):
        namespace = self.app.view_functions['trips_new'].__wrapped__.__globals__
        with self.app.test_request_context(ROOT + '/new'):
            from flask import session
            session['auth_session_id'] = self.handle
            with normal_authenticated() as outer:
                with patch.dict(namespace, render_template=Mock(side_effect=RuntimeError('template bug'))):
                    with self.assertRaises(RuntimeError):
                        self.app.view_functions['trips_new']()
                self.assertIs(g.auth, outer)
                outer.client.close.assert_not_called()
            self.assertNotIn('auth', g)

    def test_trip_presentation_forms_keep_exact_fields_and_actions(self):
        for path, action, heading, submit in (
            (ROOT + '/new', ROOT, 'Plan a Trip', 'Create Trip'),
            (DETAIL + '/edit', DETAIL + '/edit', 'Edit Trip', 'Save Changes'),
        ):
            page = Document(self.client.get(path).get_data(as_text=True))
            self.assertEqual([node.text for node in page.find('h1')], [heading])
            form = page.find('form', action=action)[0]
            self.assertEqual(form.attrs['method'], 'post')
            inputs = [node for node in page.find('input') if form in node.ancestors]
            self.assertEqual([node.attrs['name'] for node in inputs], ['csrf_token', 'name', 'visit_date'])
            self.assertEqual(inputs[0].attrs['value'], self.csrf)
            self.assertIn('required', inputs[1].attrs)
            self.assertNotIn('required', inputs[2].attrs)
            self.assertEqual([node.text for node in page.find('button') if form in node.ancestors], [submit])
            self.assertEqual(page.find('script'), [])
            self.assertEqual(page.find('select'), [])
            self.assertEqual(page.stack, [])
        response = self.client.post(ROOT, data=self.form(ROOT, visit_date='invalid'))
        page = Document(response.get_data(as_text=True))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(page.find('p', id='trip-form-error', role='alert')), 1)

    def test_trip_cards_empty_states_dates_and_pagination(self):
        service = self.services['list_user_trips']
        service.side_effect = None
        service.return_value = (replace(self.trip, visit_date=None),)
        page = Document(self.client.get(ROOT).get_data(as_text=True))
        self.assertIn('Date not set', page.find('main')[0].text)
        self.assertEqual(page.find('a', href=DETAIL)[0].text, 'View Trip')
        self.assertEqual(page.find('a', href=DETAIL + '/edit')[0].text, 'Edit')
        self.assertEqual(page.find('h2')[0].text, self.trip.name)
        service.return_value = ()
        self.assertIn(b'Plan Your First Trip', self.client.get(ROOT).data)
        later = self.client.get(ROOT + '?offset=50').get_data(as_text=True)
        self.assertIn('No trips on this page.', later)
        self.assertNotIn('Plan Your First Trip', later)
        self.assertIn('offset=0', later)
        service.return_value = (self.trip,) * 50
        self.assertIn(b'offset=50', self.client.get(ROOT).data)

    def test_memberships_empty_pagination_and_post_delete_presentation(self):
        page = Document(self.client.get(DETAIL).get_data(as_text=True))
        membership_list = page.find('ol', **{'class': 'trip-memberships'})[0]
        members = [node for node in page.find('li') if membership_list in node.ancestors]
        self.assertEqual([(node.attrs['value'], node.text) for node in members], [('3', 'Place unavailable')])
        self.assertEqual(len(page.find('a', href=DETAIL + '?after_position=3')), 1)
        delete = page.find('form', action=DETAIL + '/delete')[0]
        self.assertEqual(delete.attrs['method'], 'post')
        self.assertEqual(page.find('a', href=DETAIL + '/delete'), [])
        fields = [node for node in page.find('input') if delete in node.ancestors]
        self.assertEqual([(node.attrs['name'], node.attrs['value']) for node in fields], [('csrf_token', self.csrf)])
        section = page.find('section', **{'aria-labelledby': 'trip-destinations-title'})[0]
        for tag in ('button', 'form', 'input', 'select'):
            self.assertFalse(any(section in node.ancestors for node in page.find(tag)))
        service = self.services['get_user_trip']
        service.side_effect = None
        service.return_value = replace(self.detail, memberships=(), next_after_position=None)
        self.assertIn(b'No destinations added yet.', self.client.get(DETAIL).data)
        later = self.client.get(DETAIL + '?after_position=3').get_data(as_text=True)
        self.assertIn('No more places on this page.', later)
        self.assertNotIn('No destinations added yet.', later)
        member = replace(self.detail.memberships[0], place=SimpleNamespace(name='<script>Place</script>'))
        service.return_value = replace(self.detail, memberships=(member,))
        html = self.client.get(DETAIL).get_data(as_text=True)
        self.assertIn('&lt;script&gt;Place&lt;/script&gt;', html)
        self.assertNotIn('<script>', html)

    def setup_add_place(self):
        self.place = SimpleNamespace(id='bbbbbbbb-0000-0000-0000-000000000003',
            slug='synthetic-place', name='<script>Place</script>', category='nature', address='Safe address')
        self.catalog = Mock(spec=['get_published_by_slug'])
        self.catalog.get_published_by_slug.return_value = self.place
        self.app.extensions['rosago_places'] = self.catalog
        self.add_path = ROOT + '/add-place/synthetic-place'
        return {'csrf_token': self.csrf, 'trip_id': TRIP}

    def test_add_chooser_owned_choices_isolation_and_no_get_mutation(self):
        self.setup_add_place()
        seen = []
        def inspect(sender, template, context, **extra):
            self.assertNotIn('auth', g)
            self.assertEqual(context['trips'], (self.trip,))
            for value in context.values():
                self.assertNotIsInstance(value, (AuthenticatedContext, NormalAuthSession))
                self.assertTrue(all(value is not client for client in self.owned))
            seen.append(template.name)
        with before_render_template.connected_to(inspect, self.app):
            response = self.client.get(self.add_path)
        self.assertEqual(response.status_code, 200)
        self.protected(response)
        self.assertEqual(seen, ['trips/add_place.html'])
        self.catalog.get_published_by_slug.assert_called_once_with('synthetic-place')
        self.assertEqual(self.services['list_user_trips'].call_args.kwargs, {'limit': 50, 'offset': 0})
        self.services['add_place'].assert_not_called()
        html = response.get_data(as_text=True)
        page = Document(html)
        self.assertEqual(page.find('h1')[0].text, 'Add to Trip')
        self.assertEqual(page.find('script'), [])
        self.assertIn('&lt;script&gt;Place&lt;/script&gt;', html)
        self.assertIn('My &lt;trip&gt;', html)
        self.assertIn('aria-current="true">My Trips', html)
        form = page.find('form', action=self.add_path)[0]
        self.assertEqual(form.attrs['method'], 'post')
        inputs = [node for node in page.find('input') if form in node.ancestors]
        self.assertEqual([node.attrs['name'] for node in inputs], ['csrf_token', 'trip_id'])
        self.assertEqual(inputs[1].attrs['value'], TRIP)
        self.assertIn('required', inputs[1].attrs)
        self.assertEqual(inputs[1].ancestors[-1].tag, 'label')
        for secret in (OWNER, self.handle, 'private-access', 'private-refresh', 'private-provider-session'):
            self.assertNotIn(secret, html)
        self.assertEqual(page.stack, [])

    def test_add_requires_login_and_retains_auth_failure_behavior(self):
        data = self.setup_add_place()
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                for method in ('GET', 'POST'):
                    response = self.client.open(self.add_path, method=method, data=data)
                    self.assertEqual(response.status_code, 503)
                    self.protected(response)
        with self.client.session_transaction() as session:
            session.clear()
        for method in ('GET', 'POST'):
            response = self.client.open(self.add_path, method=method, data=data)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['Location'], '/login?login_required=1')
            self.protected(response)
        self.catalog.get_published_by_slug.assert_not_called()
        self.untouched()

    def test_add_empty_and_paginated_trip_choices(self):
        self.setup_add_place()
        service = self.services['list_user_trips']
        service.side_effect = None
        service.return_value = ()
        response = self.client.get(self.add_path)
        self.assertIn(b'Create a trip first', response.data)
        self.assertIn(b'href="/user/trips/new"', response.data)
        self.assertEqual(Document(response.get_data(as_text=True)).find('form', action=self.add_path), [])
        response = self.client.get(self.add_path + '?offset=50')
        self.assertIn(b'No trips on this page', response.data)
        self.assertIn(b'offset=0', response.data)
        self.assertNotIn(b'Create a trip first', response.data)
        self.assertEqual(service.call_args.kwargs, {'limit': 50, 'offset': 50})
        service.return_value = (replace(self.trip, visit_date=None),) * 50
        response = self.client.get(self.add_path)
        self.assertIn(b'Date not set', response.data)
        self.assertIn(b'offset=50', response.data)
        for query in ('offset=-1', 'offset=1&offset=2', 'offset=2147483647'):
            self.assertEqual(self.client.get(self.add_path + '?' + query).status_code, 400)
        self.services['add_place'].assert_not_called()

    def test_add_success_single_server_resolved_mutation_and_detail_redirect(self):
        data = self.setup_add_place()
        data['trip_id'] = TRIP.upper()
        response = self.client.post(self.add_path, data=data, headers={'Origin': 'http://localhost'})
        self.assertEqual(response.status_code, 303)
        self.protected(response)
        self.assertEqual(response.headers['Location'], DETAIL)
        mutation = self.services['add_place']
        mutation.assert_called_once()
        self.assertEqual(mutation.call_args.args[1:], (TRIP, self.place.id))
        self.services['list_user_trips'].assert_not_called()
        self.catalog.get_published_by_slug.assert_called_once_with('synthetic-place')
        self.services['get_user_trip'].side_effect = None
        member = replace(self.detail.memberships[0], place_id=self.place.id, place=self.place)
        self.services['get_user_trip'].return_value = replace(self.detail, memberships=(member,))
        self.assertIn(b'&lt;script&gt;Place&lt;/script&gt;', self.client.get(DETAIL).data)

    def test_add_form_uuid_csrf_and_origin_rejections_before_catalog_or_mutation(self):
        data = self.setup_add_place()
        cases = []
        for field in ('csrf_token', 'trip_id'):
            missing = dict(data); del missing[field]
            cases.append((missing, {}, 403 if field == 'csrf_token' else 400))
            duplicate = MultiDict(data); duplicate.add(field, data[field])
            cases.append((duplicate, {}, 403 if field == 'csrf_token' else 400))
        for value in ('', 'invalid', ' '):
            cases.append((data | {'csrf_token': value}, {}, 403))
        other = self.seed()
        wrong_csrf = self.dependencies.store.resolve(other).csrf
        with self.client.session_transaction() as session:
            session['auth_session_id'] = self.handle
        cases.append((data | {'csrf_token': wrong_csrf}, {}, 403))
        for value in ('', 'bad', ' ' + TRIP, TRIP + ' ', TRIP.replace('-', ''), '{' + TRIP + '}'):
            cases.append((data | {'trip_id': value}, {}, 400))
        for field in ('place_id', 'user_id', 'owner', 'extra'):
            cases.append((data | {field: 'untrusted'}, {}, 400))
        cases.append((data | {'upload': (io.BytesIO(b'file'), 'file.txt')}, {}, 400))
        for origin in ('null', '', 'https://foreign.invalid', 'http://localhost.evil'):
            cases.append((data, {'Origin': origin}, 403))
        for payload, headers, status in cases:
            response = self.client.post(self.add_path, data=payload, headers=headers)
            self.assertEqual(response.status_code, status)
            self.protected(response)
        self.catalog.get_published_by_slug.assert_not_called()
        self.untouched()

    def test_add_unpublished_and_catalog_errors_prevent_trip_access(self):
        from places_service import PlacesValidationError, PlacesUnavailableError, PlacesConsistencyError
        data = self.setup_add_place()
        self.catalog.get_published_by_slug.return_value = None
        for method in ('GET', 'POST'):
            self.assertEqual(self.client.open(self.add_path, method=method, data=data).status_code, 404)
        for error, status in ((PlacesValidationError(), 404), (PlacesUnavailableError(), 503),
                              (PlacesConsistencyError(), 500)):
            error.args = ('private-provider-message',)
            self.catalog.get_published_by_slug.side_effect = error
            for method in ('GET', 'POST'):
                response = self.client.open(self.add_path, method=method, data=data)
                self.assertEqual(response.status_code, status)
                self.assertNotIn(b'private-provider-message', response.data)
                self.protected(response)
        self.untouched()

    def test_add_rpc_rejections_sanitized_and_never_replayed(self):
        data = self.setup_add_place()
        service = self.services['add_place']
        for error_type, status in ((TripValidationError, 400), (TripNotFoundError, 404),
                                  (TripOperationRejectedError, 400), (TripUnavailableError, 503),
                                  (TripConsistencyError, 500)):
            error = error_type(); error.args = ('private-provider-message',)
            service.side_effect = error
            service.reset_mock()
            response = self.client.post(self.add_path, data=data)
            self.assertEqual(response.status_code, status)
            self.assertNotIn(b'private-provider-message', response.data)
            self.protected(response)
            service.assert_called_once()
            if status == 503:
                self.assertIn(b'could not be confirmed', response.data)
        for rejected_id in (TRIP, OWNER):
            service.side_effect = TripNotFoundError()
            response = self.client.post(self.add_path, data=data | {'trip_id': rejected_id})
            self.assertEqual((response.status_code, response.data), (404, b'Trip not found.'))

    def test_trip_templates_compile(self):
        for name in ('trips/list.html', 'trips/new.html', 'trips/detail.html', 'trips/edit.html',
                     'user/index.html', 'partials/navbar.html'):
            self.app.jinja_env.get_template(name)


if __name__ == '__main__':
    unittest.main()
