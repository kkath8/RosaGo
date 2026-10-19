"""Offline authorization tests; no live SQL or provisioning."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

import httpx
from flask import before_render_template, g
from postgrest.exceptions import APIError

from admin_authorization_service import AdminAuthorizationError, is_current_admin
from normal_auth_coordinator import AuthenticatedContext, SessionBusy, ClientUnavailable
import test_registration


class AdminServiceTests(unittest.TestCase):
    def test_strict_boolean_and_request_client(self):
        client = Mock(spec=['rpc'])
        query = client.rpc.return_value
        query.retry.return_value = query
        context = AuthenticatedContext('handle', 'user', 'irrelevant@example.invalid', client)
        for value in (True, False):
            client.reset_mock()
            query.execute.return_value = SimpleNamespace(data=value)
            self.assertIs(is_current_admin(context), value)
            self.assertEqual(client.mock_calls, [call.rpc('rosago_is_admin', {}),
                call.rpc().retry(False), call.rpc().execute()])
        for value in (None, 0, 1, 'true', [], [True], {'is_admin': True}):
            query.execute.return_value = SimpleNamespace(data=value)
            with self.assertRaises(AdminAuthorizationError):
                is_current_admin(context)
        for error in (httpx.ConnectError('private-provider-detail'),
                      APIError(dict(message='private-provider-detail', code='42501', details='', hint=''))):
            query.execute.side_effect = error
            with self.assertRaises(AdminAuthorizationError) as raised:
                is_current_admin(context)
            self.assertIsNone(raised.exception.__context__)
            self.assertNotIn('private-provider-detail', str(raised.exception))
        with self.assertRaises(AdminAuthorizationError):
            is_current_admin({'is_admin': True})


class AdminBoundaryTests(unittest.TestCase):
    def setUp(self):
        test_registration.RegistrationTests.setUp(self)
        self.dependencies = self.app.extensions['rosago_normal_auth']
        self.value = False
        self.status = 200
        self.requests = []
        self.clients = []

        def respond(request):
            self.requests.append(request)
            self.assertIsNotNone(g.auth)
            self.assertEqual(request.url.path, '/rest/v1/rpc/rosago_is_admin')
            self.assertEqual(request.method, 'POST')
            self.assertEqual(request.content, b'{}')
            self.assertEqual(request.headers['authorization'], 'Bearer fixture-access')
            return httpx.Response(self.status, json=self.value)

        def http_factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
            self.clients.append(client)
            return client
        self.dependencies.adapters._http_factory = http_factory
        self.dependencies.coordinator._clients = self.dependencies.adapters.database_client

    def tearDown(self):
        self.assertTrue(all(client.is_closed for client in self.clients))
        self.assertEqual(self.supabase.mock_calls, [])

    def protected(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        for secret in (b'fixture-access', b'fixture-refresh', b'private-provider-detail', b'user-123'):
            self.assertNotIn(secret, response.data)

    def test_unauthenticated_and_forged_flags(self):
        for state in ({}, {'is_admin': True, 'role': 'admin', 'user_id': 'user-123'}):
            with self.client.session_transaction() as session:
                session.clear(); session.update(state)
            response = self.client.get('/admin')
            self.protected(response, 302)
            self.assertEqual(response.location, '/login?login_required=1')
        self.assertEqual(self.requests, [])

    def test_membership_revocation_and_render_isolation(self):
        test_registration.seed_normal_session(self)
        self.protected(self.client.get('/admin'), 403)
        seen = []
        def inspect(sender, template, context, **kwargs):
            self.assertNotIn('auth', g)
            self.assertNotIn('admin', g)
            self.assertFalse(any(isinstance(value, AuthenticatedContext) for value in context.values()))
            seen.append(template.name)
        self.value = True
        with before_render_template.connected_to(inspect, self.app):
            response = self.client.get('/admin')
        self.protected(response, 200)
        self.assertIn(b'RosaGo Admin', response.data)
        self.assertEqual(seen, ['admin/index.html'])
        self.value = False
        self.protected(self.client.get('/admin'), 403)
        self.assertEqual(len(self.requests), 3)
        with self.client.session_transaction() as session:
            self.assertNotIn('is_admin', session)
            self.assertNotIn('role', session)

    def test_failures_and_error_paths_are_private(self):
        handle = test_registration.seed_normal_session(self)
        for value in (None, 'true', 1, [True], {'role': 'admin'}):
            self.value = value
            self.protected(self.client.get('/admin'), 503)
        self.status = 503
        self.value = {'message': 'private-provider-detail'}
        self.protected(self.client.get('/admin'), 503)
        for error in (SessionBusy(), ClientUnavailable()):
            with patch.object(self.dependencies.coordinator, 'authenticated', side_effect=error):
                self.protected(self.client.get('/admin'), 503)
        self.protected(self.client.get('/admin/missing'), 404)
        self.protected(self.client.post('/admin'), 405)
        self.dependencies.store.revoke(handle)
        self.protected(self.client.get('/admin'), 302)


class AdminMigrationTests(unittest.TestCase):
    def test_static_grants_and_current_caller_predicate(self):
        sql = (Path(__file__).resolve().parents[1] / 'migrations/0008_admin_authorization.sql').read_text()
        self.assertIn('CREATE TABLE public.admin_memberships', sql)
        self.assertIn('user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE', sql)
        self.assertIn('ENABLE ROW LEVEL SECURITY', sql)
        self.assertIn('GRANT SELECT ON TABLE public.admin_memberships TO authenticated;', sql)
        self.assertIn('FOR SELECT TO authenticated\n    USING (user_id = (SELECT auth.uid()))', sql)
        self.assertEqual(sql.count('CREATE POLICY'), 1)
        self.assertEqual(sql.count('GRANT '), 2)
        self.assertEqual(sql.count('FROM PUBLIC, anon, authenticated, service_role;'), 2)
        self.assertIn('CREATE FUNCTION public.rosago_is_admin()', sql)
        self.assertIn('SECURITY INVOKER\nSET search_path = \'\'', sql)
        self.assertIn('WHERE membership.user_id = (SELECT auth.uid())', sql)
        self.assertIn('GRANT EXECUTE ON FUNCTION public.rosago_is_admin() TO authenticated;', sql)
        self.assertNotIn('INSERT INTO', sql)
