"""Offline audit UI tests through the real authentication/PostgREST boundary."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import httpx

from admin_audit_service import PROJECTION, PAGE_SIZE
import test_admin_authorization as foundation
import test_registration
from test_public_layout import Document


ACTOR_ONE = '22222222-2222-4222-8222-222222222222'
ACTOR_TWO = '44444444-4444-4444-8444-444444444444'


def directory_user(identifier, name=None, email=None):
    return dict(identifier=identifier, name=name, email=email, created_at='2026-11-01T00:00:00+00:00')


def audit_row(index=1, **changes):
    return dict(id=f'11111111-1111-4111-8111-{index:012}',
        actor_id=ACTOR_ONE, action='edit',
        destination_id='33333333-3333-4333-8333-333333333333',
        occurred_at='2026-11-03T04:05:06+00:00',
        summary=dict(submitted_fields=['name', 'address'], resulting_status='draft'),
        destination=dict(name='Santa Rosa destination', slug='santa-rosa-destination')) | changes


class AuditRouteTests(unittest.TestCase):
    setUp = foundation.AdminBoundaryTests.setUp
    tearDown = foundation.AdminBoundaryTests.tearDown
    protected = foundation.AdminBoundaryTests.protected

    def install(self):
        test_registration.seed_normal_session(self)
        self.value = True
        self.rows = [audit_row()]
        self.audit_status = 200
        self.directory_status = 200
        self.users = []

        def respond(request):
            self.requests.append(request)
            self.assertEqual(request.headers['authorization'], 'Bearer fixture-access')
            if request.url.path.endswith('/rosago_is_admin'):
                return httpx.Response(self.status, json=self.value)
            if request.url.path.endswith('/rosago_admin_operational_overview'):
                self.assertEqual(request.method, 'POST')
                args = json.loads(request.content)
                self.assertEqual(args['p_query'], '')
                if self.directory_status != 200:
                    return httpx.Response(self.directory_status,
                        json=dict(message='private-provider-detail', code='42501'))
                offset = args['p_offset']
                return httpx.Response(200, json=dict(users_total=len(self.users), users_matching=len(self.users),
                    users=self.users[offset:offset + 25], trips_total=0, upcoming_trips=0,
                    destinations_in_trips=0, popular=[], categories=[]))
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.path, '/rest/v1/admin_destination_audit')
            self.assertEqual(request.url.params['select'], PROJECTION)
            self.assertEqual(request.url.params['order'], 'occurred_at.desc,id.desc')
            self.assertEqual(request.url.params['limit'], str(PAGE_SIZE + 1))
            if self.audit_status != 200:
                return httpx.Response(self.audit_status, json=dict(message='private-provider-detail', code='42501'))
            return httpx.Response(200, json=self.rows)

        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
            self.clients.append(client)
            return client
        self.dependencies.adapters._http_factory = factory

    def test_unauthenticated_forged_nonadmin_revoked_and_unavailable_membership(self):
        for state in ({}, {'is_admin': True, 'role': 'admin'}):
            with self.client.session_transaction() as session:
                session.clear(); session.update(state)
            self.protected(self.client.get('/admin/audit-logs'), 302)
        self.assertEqual(self.requests, [])
        self.install()
        self.value = False
        self.protected(self.client.get('/admin/audit-logs'), 403)
        self.assertFalse(any(r.url.path.endswith('/admin_destination_audit') for r in self.requests))
        self.value = True
        self.protected(self.client.get('/admin/audit-logs'), 200)
        self.requests.clear()
        self.value = False
        self.protected(self.client.get('/admin/audit-logs'), 403)
        self.status = 503
        self.protected(self.client.get('/admin/audit-logs'), 503)
        self.assertFalse(any(r.url.path.endswith('/admin_destination_audit') for r in self.requests))

    def test_real_projection_rendering_escape_timezone_and_readonly_navigation(self):
        self.install()
        self.rows = [audit_row(destination=dict(name='<script>unsafe</script>', slug='safe-destination'))]
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        html = response.get_data(as_text=True)
        document = Document(html)
        self.assertEqual(document.stack, [])
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', html)
        for text in ('Updated', '12:05:06 PM', 'Asia/Manila', 'Submitted fields: address, name',
                     self.rows[0]['actor_id'], 'Read-only history'):
            self.assertIn(text, html)
        self.assertTrue(document.find('a', href='/admin/audit-logs', **{'aria-current': 'page'}))
        self.assertTrue(document.find('a', href='/admin/places/safe-destination'))
        self.assertTrue(document.find('form', action='/admin/logout'))
        self.assertTrue(document.find('input', name='csrf_token'))
        self.assertNotIn('Delete Audit', html)
        self.assertNotIn('Edit Audit', html)
        self.assertNotIn('Deleted', html)

    def test_filter_pagination_and_bounded_read(self):
        self.install()
        self.rows = [audit_row(n, action='publish') for n in range(1, PAGE_SIZE + 2)]
        response = self.client.get('/admin/audit-logs?action=publish&page=2')
        self.protected(response, 200)
        document = Document(response.get_data(as_text=True))
        self.assertTrue(document.find('a', href='/admin/audit-logs?action=publish&page=3'))
        self.assertTrue(document.find('a', href='/admin/audit-logs?action=publish&page=1'))
        self.assertEqual(len(document.find('time')), PAGE_SIZE)
        audit_request = next(r for r in self.requests if r.url.path.endswith('/admin_destination_audit'))
        self.assertEqual(audit_request.url.params['action'], 'eq.publish')
        self.assertEqual(audit_request.url.params['offset'], '25')

    def test_empty_and_failure_are_distinct_and_nullable_destination_keeps_identity(self):
        self.install()
        self.rows = []
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        self.assertIn(b'No audit records', response.data)
        self.assertNotIn(b'Next page', response.data)
        self.audit_status = 503
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 503)
        self.assertIn(b'Audit history is temporarily unavailable', response.data)
        self.assertNotIn(b'No audit records', response.data)
        self.audit_status = 200
        self.rows = [audit_row(destination=None)]
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        self.assertIn(self.rows[0]['destination_id'].encode(), response.data)

    def test_invalid_parameters_and_write_methods_never_read_history(self):
        self.install()
        for query in ('page=0', 'page=-1', 'page=01', 'page=100001', 'page=1&page=2',
                      'action=delete', 'action=edit&action=publish', 'q=anything', 'page=%D9%A1'):
            self.protected(self.client.get('/admin/audit-logs?' + query), 400)
        for method in ('post', 'put', 'patch', 'delete'):
            self.protected(getattr(self.client, method)('/admin/audit-logs'), 405)
        self.assertFalse(any(r.url.path.endswith('/admin_destination_audit') for r in self.requests))

    def test_malformed_or_private_payloads_fail_closed(self):
        self.install()
        changes = [dict(action='delete'), dict(actor_id='not-a-uuid'), dict(occurred_at='invalid'),
            dict(occurred_at='2026-11-03T04:05:06'), dict(summary={'values': {'private': 'secret'}}),
            dict(summary=dict(submitted_fields=['password'], resulting_status='draft')),
            dict(summary=dict(submitted_fields=['name'], resulting_status='invalid')),
            dict(destination=dict(name='Destination', slug='../private'))]
        for changed in changes:
            with self.subTest(changed=changed):
                self.rows = [audit_row(**deepcopy(changed))]
                response = self.client.get('/admin/audit-logs')
                self.protected(response, 503)
                self.assertIn(b'Audit history is temporarily unavailable', response.data)

    def test_multiple_admins_match_events_and_share_one_batched_directory_lookup(self):
        self.install()
        self.users = [directory_user(ACTOR_TWO, 'Second Administrator', 'second@example.invalid'),
                      directory_user(ACTOR_ONE, 'First Administrator', 'first@example.invalid')]
        self.rows = [audit_row(1, action='create'),
                     audit_row(2, actor_id=ACTOR_TWO, action='publish',
                               summary=dict(submitted_fields=[], resulting_status='published')),
                     audit_row(3, action='archive',
                               summary=dict(submitted_fields=[], resulting_status='archived'))]
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        document = Document(response.get_data(as_text=True))
        self.assertIn(b'Performed by', response.data)
        self.assertIn(b'Actor ID:', response.data)
        # Directory order differs from event order; identity must match by UUID.
        tbody = document.find('tbody')[0]
        event_rows = [row for row in document.find('tr')
                      if any(ancestor is tbody for ancestor in row.ancestors)]
        self.assertEqual(len(event_rows), 3)
        for row, name, email, actor in zip(event_rows,
                ['First Administrator', 'Second Administrator', 'First Administrator'],
                ['first@example.invalid', 'second@example.invalid', 'first@example.invalid'],
                [ACTOR_ONE, ACTOR_TWO, ACTOR_ONE]):
            self.assertIn(name, row.text)
            self.assertIn(email, row.text)
            self.assertIn(actor, row.text)
        self.assertEqual(sum(r.url.path.endswith('/rosago_admin_operational_overview') for r in self.requests), 1)

    def test_email_only_deleted_and_missing_profile_fallback(self):
        self.install()
        self.users = [directory_user(ACTOR_ONE, email='email-only@example.invalid')]
        self.rows = [audit_row(), audit_row(2, actor_id=ACTOR_TWO)]
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        self.assertIn(b'email-only@example.invalid', response.data)
        self.assertEqual(response.data.count(b'Unknown / Former Admin'), 1)
        self.assertIn(ACTOR_TWO.encode(), response.data)
        self.assertNotIn(b'Some account details could not be resolved', response.data)
        self.users = [directory_user(ACTOR_ONE)]
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        self.assertIn(b'Unknown / Former Admin', response.data)

    def test_later_directory_batches_are_read_once_and_only_for_visible_actors(self):
        self.install()
        self.users = [directory_user(f'55555555-5555-4555-8555-{n:012}', 'Unrelated account')
                      for n in range(25)] + [directory_user(ACTOR_ONE, 'Older Administrator', 'older@example.invalid')]
        self.rows = [audit_row(n) for n in range(1, PAGE_SIZE + 1)] + [audit_row(26, actor_id=ACTOR_TWO)]
        response = self.client.get('/admin/audit-logs?action=edit&page=2')
        self.protected(response, 200)
        self.assertIn(b'Older Administrator', response.data)
        self.assertNotIn(b'Unrelated account', response.data)
        calls = [json.loads(r.content) for r in self.requests
                 if r.url.path.endswith('/rosago_admin_operational_overview')]
        self.assertEqual([call['p_offset'] for call in calls], [0, 25])
        self.assertIn(b'/admin/audit-logs?action=edit&amp;page=3', response.data)
        self.assertNotIn(ACTOR_TWO.encode(), response.data)

    def test_identity_failure_keeps_history_and_empty_history_skips_directory(self):
        self.install()
        self.directory_status = 503
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        self.assertIn(b'Unknown / Former Admin', response.data)
        self.assertIn(b'Some account details could not be resolved', response.data)
        self.assertIn(ACTOR_ONE.encode(), response.data)
        self.requests.clear()
        self.rows = []
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        self.assertFalse(any(r.url.path.endswith('/rosago_admin_operational_overview') for r in self.requests))

    def test_actor_names_and_emails_are_escaped_and_not_read_without_authorization(self):
        self.install()
        self.users = [directory_user(ACTOR_ONE, '<script>name</script>', '<b>email</b>')]
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        self.assertIn(b'&lt;script&gt;name&lt;/script&gt;', response.data)
        self.assertIn(b'&lt;b&gt;email&lt;/b&gt;', response.data)
        self.requests.clear()
        self.value = False
        self.protected(self.client.get('/admin/audit-logs'), 403)
        self.assertFalse(any(r.url.path.endswith('/rosago_admin_operational_overview') for r in self.requests))

    def test_all_supported_actions_retain_the_authenticated_actor_write_contract(self):
        sql = (Path(__file__).resolve().parents[1] / 'migrations/0013_admin_destination_audit.sql').read_text()
        self.assertIn("action IN ('create','edit','publish','draft','archive','restore')", sql)
        self.assertIn('VALUES ((SELECT auth.uid()),p_action,target_id,', sql)
        self.assertIn('rosago_admin_mutate_destination_unlogged(p_action,p_slug,p_expected_updated_at,p_values)', sql)

    def test_photo_field_changes_render_without_contents_or_urls(self):
        self.install()
        self.rows = [audit_row(summary=dict(submitted_fields=['image_url'], resulting_status='published'))]
        response = self.client.get('/admin/audit-logs')
        self.protected(response, 200)
        self.assertIn(b'Submitted fields: image url', response.data)
        self.assertIn(ACTOR_ONE.encode(), response.data)
        self.assertNotIn(b'/storage/v1/', response.data)


if __name__ == '__main__':
    unittest.main()
