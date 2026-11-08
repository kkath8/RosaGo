"""Focused offline checks for the read-only Admin presentation workflow."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import httpx
from flask import before_render_template, g

import test_admin_authorization as foundation
import test_registration
from test_admin_places import row
from admin_places_service import get_destination, DETAIL_PROJECTION, TOURISM_FIELDS, AdminPlacesError
from normal_auth_coordinator import AuthenticatedContext


def detail(**changes):
    return row() | dict(description='Real <description>', latitude=None,
        longitude=None, image_url=None, created_at='2026-10-19T04:00:00Z') | changes


class PreviewRouteTests(unittest.TestCase):
    setUp = foundation.AdminBoundaryTests.setUp
    tearDown = foundation.AdminBoundaryTests.tearDown
    protected = foundation.AdminBoundaryTests.protected
    paths = ('/admin/places/new', '/admin/places/rosago-test-v1-fixture',
             '/admin/places/rosago-test-v1-fixture/edit')

    def install_detail(self, *, missing=False, failure=False, status='draft'):
        def respond(request):
            self.requests.append(request)
            self.assertEqual(request.headers['authorization'], 'Bearer fixture-access')
            if request.url.path.endswith('/rosago_is_admin'):
                return httpx.Response(200, json=True)
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.path, '/rest/v1/places')
            self.assertIn(request.url.params['select'], (DETAIL_PROJECTION, DETAIL_PROJECTION + ',' + ','.join(TOURISM_FIELDS)))
            self.assertEqual(request.url.params['slug'], 'eq.rosago-test-v1-fixture')
            self.assertEqual(request.url.params['limit'], '1')
            if failure:
                return httpx.Response(503, json={'message': 'private-provider-detail'})
            result = detail(status=status)
            if request.url.params['select'] != DETAIL_PROJECTION:
                result.update({key: None for key in TOURISM_FIELDS})
            return httpx.Response(200, json=[] if missing else [result])
        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
            self.clients.append(client)
            return client
        self.dependencies.adapters._http_factory = factory
        test_registration.seed_admin_session(self)

    def test_all_new_pages_require_fresh_admin_membership(self):
        for path in self.paths:
            self.protected(self.client.get(path), 302)
        self.assertEqual(self.requests, [])
        test_registration.seed_admin_session(self)
        for path in self.paths:
            self.protected(self.client.get(path), 403)
        self.assertFalse(any(r.url.path.endswith('/places') for r in self.requests))

    def test_real_detail_prefill_and_template_authority_isolation(self):
        self.install_detail()
        seen = []
        def inspect(sender, template, context, **kwargs):
            self.assertNotIn('auth', g)
            self.assertFalse(any(isinstance(v, AuthenticatedContext) for v in context.values()))
            seen.append(template.name)
        with before_render_template.connected_to(inspect, self.app):
            for path in self.paths:
                response = self.client.get(path)
                self.protected(response, 200)
                if path == self.paths[0]:
                    self.assertIn(b'Create Draft Destination', response.data)
                elif path.endswith('/edit'):
                    self.assertIn(b'Save Changes', response.data)
                self.assertIn(b'Publication lifecycle', response.data)
                if path != self.paths[0]:
                    self.assertIn(b'Fixture &lt;destination&gt;', response.data)
                    self.assertIn(b'Real &lt;description&gt;', response.data)
                    self.assertIn(b'Development/test record', response.data)
                else:
                    self.assertNotIn(b'<option value="archived"', response.data)
        self.assertEqual(len(seen), 3)
        # The only form in previews is the existing secure logout form.
        response = self.client.get(self.paths[2])
        self.assertEqual(response.data.count(b'<form '), 2)
        self.assertIn(b'name="expected_updated_at"', response.data)
        self.assertIn(b'Save Changes', response.data)

    def test_missing_unavailable_archived_and_no_mutations(self):
        for options, expected in (({'missing': True}, 404), ({'failure': True}, 503),
                                  ({'status': 'archived'}, 200)):
            self.install_detail(**options)
            for path in self.paths[1:]:
                self.protected(self.client.get(path), expected)
        self.assertIn(b'status-archived', self.client.get(self.paths[2]).data)
        for path in self.paths:
            self.protected(self.client.post(path, data={'name': 'Changed'}), 405 if path == self.paths[1] else 403)
        for rule in self.app.url_map.iter_rules():
            if rule.rule.startswith('/admin/places'):
                self.assertLessEqual(rule.methods, {'GET', 'HEAD', 'OPTIONS', 'POST'})


class DetailReadTests(unittest.TestCase):
    def test_bounded_validated_read_and_nullable_draft_coordinates(self):
        query = Mock()
        for method in ('select', 'eq', 'limit', 'retry'):
            getattr(query, method).return_value = query
        client = Mock(spec=['table'])
        client.table.return_value = query
        context = AuthenticatedContext('handle', 'user', 'email', client, realm='admin')
        query.execute.return_value = SimpleNamespace(data=[detail()])
        result = get_destination(context, 'rosago-test-v1-fixture')
        self.assertIsNone(result.latitude)
        self.assertEqual(result.description, 'Real <description>')
        query.limit.assert_called_once_with(1)
        query.retry.assert_called_once_with(False)
        for changes in ({'status': 'unknown'}, {'latitude': True}, {'longitude': 20},
                        {'image_url': 'javascript:alert(1)'},
                        {'created_at': 'bad'}, {'slug': 'other'}, {'description': ''}):
            query.execute.return_value = SimpleNamespace(data=[detail(**changes)])
            with self.subTest(changes=changes), self.assertRaises(AdminPlacesError):
                get_destination(context, 'rosago-test-v1-fixture')
        query.execute.return_value = SimpleNamespace(data=[detail(status='published', latitude=0, longitude=0)])
        self.assertEqual(get_destination(context, 'rosago-test-v1-fixture').latitude, 0)
        client.reset_mock()
        self.assertIsNone(get_destination(context, 'INVALID'))
        client.table.assert_not_called()
