"""Offline read-service, real SDK response parsing, route and SQL contract checks."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from normal_auth_coordinator import AuthenticatedContext
from normal_auth_flask import normal_authenticated
from admin_places_service import (
    destination_counts, list_destinations, AdminPlacesError, PROJECTION, MAX_OFFSET,
)
import test_admin_authorization as foundation
import test_registration


def row(status='draft', **changes):
    return dict(name='Fixture <destination>', slug='rosago-test-v1-fixture', category='nature',
                status=status, address='Fixture address', updated_at='2026-10-20T04:00:00Z') | changes


class AdminPlacesServiceTests(unittest.TestCase):
    def setUp(self):
        self.query = Mock()
        for method in ('select', 'eq', 'order', 'range', 'retry'):
            getattr(self.query, method).return_value = self.query
        self.client = Mock(spec=['table'])
        self.client.table.return_value = self.query
        self.context = AuthenticatedContext('handle', 'user', 'email', self.client)

    def test_list_projection_statuses_filter_and_bound(self):
        for status in ('draft', 'published', 'archived'):
            self.query.execute.return_value = SimpleNamespace(data=[row(status)])
            result = list_destinations(self.context, status=status, offset=25)
            self.assertEqual(result[0].status, status)
            self.assertTrue(result[0].is_test_record)
        self.query.select.assert_called_with(PROJECTION)
        self.query.range.assert_called_with(25, 49)
        self.query.retry.assert_called_with(False)
        self.client.table.assert_called_with('places')

    def test_counts_require_exact_nonnegative_integer(self):
        self.query.execute.side_effect = [SimpleNamespace(data=[], count=n) for n in (105, 80, 20, 5)]
        self.assertEqual(destination_counts(self.context), dict(total=105, published=80, draft=20, archived=5))
        self.query.select.assert_called_with('id', count='exact', head=True)
        self.query.execute.side_effect = None
        for count in (None, True, -1, 1.2, '3'):
            self.query.execute.return_value = SimpleNamespace(data=[], count=count)
            with self.assertRaises(AdminPlacesError):
                destination_counts(self.context)

    def test_invalid_inputs_rows_and_failure_are_closed(self):
        for kwargs in ({'status': 'unknown'}, {'status': []}, {'offset': True}, {'offset': -1}, {'offset': MAX_OFFSET + 1}):
            with self.assertRaises(AdminPlacesError):
                list_destinations(self.context, **kwargs)
        self.client.table.assert_not_called()
        for data in (None, {}, [row()] * 26, [row(), row()], [row(status='unknown')],
                     [row(category=[])], [row(updated_at='2026-10-20')], [row(name='')],
                     [row(slug='INVALID')], [row(extra='secret')]):
            self.query.execute.return_value = SimpleNamespace(data=data)
            with self.assertRaises(AdminPlacesError):
                list_destinations(self.context)
        self.query.execute.side_effect = httpx.ConnectError('private-provider-detail')
        with self.assertRaises(AdminPlacesError) as caught:
            destination_counts(self.context)
        self.assertIsNone(caught.exception.__context__)
        with self.assertRaises(AdminPlacesError):
            list_destinations(None)


class AdminPlacesRouteTests(unittest.TestCase):
    setUp = foundation.AdminBoundaryTests.setUp
    tearDown = foundation.AdminBoundaryTests.tearDown
    protected = foundation.AdminBoundaryTests.protected

    def install_catalog(self, *, failure=False, count_header=True, content_range=None):
        def respond(request):
            self.requests.append(request)
            self.assertEqual(request.headers['authorization'], 'Bearer fixture-access')
            if request.url.path.endswith('/rosago_is_admin'):
                return httpx.Response(200, json=True)
            self.assertEqual(request.url.path, '/rest/v1/places')
            if failure:
                return httpx.Response(503, json={'message': 'private-provider-detail'})
            if request.method == 'HEAD':
                self.assertEqual(request.headers['Prefer'], 'count=exact')
                self.assertEqual(request.url.params['select'], 'id')
                count = {'eq.published': 30, 'eq.draft': 20, 'eq.archived': 5}.get(request.url.params.get('status'), 55)
                headers = {'Content-Range': f'*/{count}', 'Preference-Applied': 'count=exact'} if count_header else {}
                if content_range is not None:
                    headers['Content-Range'] = content_range
                return httpx.Response(200, headers=headers)
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.params['select'], PROJECTION)
            self.assertEqual(request.url.params['limit'], '25')
            status = request.url.params.get('status')
            rows = [row(value, slug=f'rosago-test-v1-{value}') for value in ('draft', 'published', 'archived')
                    if status is None or status == 'eq.' + value]
            return httpx.Response(200, json=rows)
        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
            self.clients.append(client)
            return client
        self.dependencies.adapters._http_factory = factory
        return test_registration.seed_normal_session(self)

    def test_real_counts_listing_filter_and_disclosure(self):
        self.install_catalog()
        response = self.client.get('/admin')
        self.protected(response, 200)
        for count in (55, 30, 20, 5):
            self.assertIn(f'class="metric-value">{count}<'.encode(), response.data)
        response = self.client.get('/admin/places')
        self.protected(response, 200)
        for status in ('Draft', 'Published', 'Archived'):
            self.assertIn(f'>{status}</span>'.encode(), response.data)
        self.assertIn(b'Development/test record', response.data)
        self.assertIn(b'Fixture &lt;destination&gt;', response.data)
        response = self.client.get('/admin/places?status=draft&offset=25')
        self.protected(response, 200)
        self.assertNotIn(b'>Published</span>', response.data)
        self.assertIn(b'Previous page', response.data)
        for query in ('status=bad', 'status=draft&status=published', 'offset=-1', 'offset=01', 'offset=99999999999', 'role=admin'):
            self.protected(self.client.get('/admin/places?' + query), 400)

    def test_api_and_missing_count_failures_are_unavailable_not_zero(self):
        for failure, count_header in ((True, True), (False, False)):
            self.install_catalog(failure=failure, count_header=count_header)
            response = self.client.get('/admin')
            self.protected(response, 503)
            self.assertIn(b'Destination counts are unavailable', response.data)
            self.assertNotIn(b'class="metric-value">0', response.data)
        self.install_catalog(failure=True)
        self.protected(self.client.get('/admin/places'), 503)

    def test_sdk_malformed_content_range_is_sanitized_in_service_and_dashboard(self):
        for header in ('*/not-a-count', '*/*'):
            with self.subTest(header=header):
                handle = self.install_catalog(content_range=header)
                with self.app.test_request_context('/admin'):
                    from flask import session
                    session['auth_session_id'] = handle
                    with normal_authenticated() as context:
                        with self.assertRaises(AdminPlacesError) as caught:
                            destination_counts(context)
                self.assertEqual(str(caught.exception), 'Destination information is temporarily unavailable.')
                self.assertIsNone(caught.exception.__context__)
                self.assertIsNone(caught.exception.__cause__)
                response = self.client.get('/admin')
                self.protected(response, 503)
                self.assertIn(b'Destination counts are unavailable', response.data)
                self.assertNotIn(b'class="metric-value">0', response.data)
                for detail in (header.encode(), b'ValueError', b'Traceback', b'Content-Range'):
                    self.assertNotIn(detail, response.data)

    def test_sdk_zero_content_range_remains_valid_zero(self):
        handle = self.install_catalog(content_range='*/0')
        with self.app.test_request_context('/admin'):
            from flask import session
            session['auth_session_id'] = handle
            with normal_authenticated() as context:
                self.assertEqual(destination_counts(context), dict(total=0, published=0, draft=0, archived=0))
        response = self.client.get('/admin')
        self.protected(response, 200)
        self.assertEqual(response.data.count(b'class="metric-value">0'), 4)
        self.assertNotIn(b'Destination counts are unavailable', response.data)


class AdminPlacesMigrationTests(unittest.TestCase):
    def test_only_additive_select_policy(self):
        root = Path(__file__).resolve().parents[1]
        sql = (root / 'migrations/0009_admin_places_read.sql').read_text(encoding='utf-8')
        statements = '\n'.join(line for line in sql.splitlines() if not line.lstrip().startswith('--'))
        self.assertEqual(' '.join(statements.split()),
            'BEGIN; CREATE POLICY places_select_admin ON public.places AS PERMISSIVE FOR SELECT TO authenticated USING ((SELECT public.rosago_is_admin())); COMMIT;')
        existing = (root / 'migrations/0002_places.sql').read_text()
        self.assertIn("USING (status = 'published')", existing)
        self.assertIn('GRANT SELECT ON TABLE public.places TO anon, authenticated;', existing)
