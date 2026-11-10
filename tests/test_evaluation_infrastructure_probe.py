"""No network: test target fences, privacy and component-only qualification."""
from contextlib import nullcontext
import json
import unittest
from unittest.mock import Mock, patch

from tools import qualify_evaluation_infrastructure as probe


class EvaluationInfrastructureProbe(unittest.TestCase):
    def setUp(self):
        self.host = 'database.example.invalid'
        self.origin = 'https://authority.example.invalid'
        self.env = dict(SUPABASE_URL='https://' + probe.PROJECT + '.supabase.co',
            ROSAGO_SESSION_DATABASE_URL='host=' + self.host + ' dbname=rosago_sessions_evaluation '
                'user=rosago_session_app password=' + 'private-test-password-' * 3 +
                ' sslmode=verify-full sslrootcert=system',
            ROSAGO_SESSION_NAMESPACE='evaluation_probe',
            ROSAGO_USER_SESSION_EPOCH='user_epoch_probe_01',
            ROSAGO_ADMIN_SESSION_EPOCH='admin_epoch_probe_01',
            ROSAGO_AUTHORITY_ORIGIN=self.origin, ROSAGO_AUTHORITY_ID='authority_probe_01',
            ROSAGO_AUTHORITY_INCARNATION='incarnation_probe_01',
            ROSAGO_AUTHORITY_MIN_SEQUENCE='0', ROSAGO_AUTHORITY_CLIENT_TOKEN='private-token-' * 4)
        self.connect = patch.object(probe.psycopg, 'connect').start()
        self.addCleanup(patch.stopall)
        self.transport = patch.object(probe, 'AuthorityHTTPTransport').start()

    def run_probe(self, **kwargs):
        return probe.probe(self.env, database_host=self.host, authority_origin=self.origin, **kwargs)

    def test_default_is_offline_even_with_complete_configuration(self):
        result = self.run_probe()
        self.assertTrue(result['configuration_valid'])
        self.assertFalse(result['infrastructure_contact_attempted'])
        self.connect.assert_not_called(); self.transport.assert_not_called()

    def test_missing_environment_reports_names_only(self):
        result = probe.probe({}, live=True)
        self.assertFalse(result['configuration_valid'])
        self.assertEqual(result['missing_variables'], list(probe.REQUIRED))
        self.connect.assert_not_called()

    def test_production_project_rejected_before_connect(self):
        self.env['SUPABASE_URL'] = 'https://brnkigrrqdrywahvcbvc.supabase.co'
        self.assertFalse(self.run_probe(live=True)['configuration_valid'])
        self.connect.assert_not_called()

    def test_target_tls_and_privilege_fences(self):
        original = dict(self.env)
        cases = [dict(ROSAGO_SESSION_NAMESPACE='production_probe'), dict(PGHOST=self.host),
                 dict(ROSAGO_AUTHORITY_OPERATOR_TOKEN='operator-private'),
                 dict(ROSAGO_AUTHORITY_ORIGIN='http://authority.example.invalid')]
        for suffix in (' options=unsafe', ' service=unsafe'):
            cases.append(dict(ROSAGO_SESSION_DATABASE_URL=original['ROSAGO_SESSION_DATABASE_URL'] + suffix))
        for old, new in (('verify-full', 'require'), ('rosago_session_app', 'postgres'),
                         (self.host, 'db.jfaufpfzfhysqkhcdsrs.supabase.co')):
            cases.append(dict(ROSAGO_SESSION_DATABASE_URL=original['ROSAGO_SESSION_DATABASE_URL'].replace(old, new)))
        for changes in cases:
            with self.subTest(fields=list(changes)):
                self.env = {**original, **changes}
                self.assertFalse(self.run_probe(live=True)['configuration_valid'])
        self.connect.assert_not_called()

    def test_separately_selected_hosts_must_match(self):
        result = probe.probe(self.env, live=True, database_host='other.example.invalid', authority_origin=self.origin)
        self.assertFalse(result['configuration_valid']); self.connect.assert_not_called()

    def test_connection_failure_does_not_disclose_secrets_or_attempt_authority(self):
        self.connect.side_effect = RuntimeError(self.env['ROSAGO_SESSION_DATABASE_URL'])
        result = self.run_probe(live=True)
        self.assertEqual(result['stop_reason'], 'database_connection_tls_or_acl_failed')
        self.assertNotIn('private-test-password', json.dumps(result)); self.transport.assert_not_called()

    def connection(self, ssl=True):
        conn = Mock()
        conn.pgconn.ssl_in_use = ssl
        conn.transaction.side_effect = lambda: nullcontext()
        conn.execute.return_value.fetchone.return_value = dict(readonly='on', ssl=ssl)
        self.connect.return_value = nullcontext(conn)
        return conn

    def test_database_must_confirm_readonly_tls_and_runtime_acl(self):
        self.connection(ssl=False)
        result = self.run_probe(live=True)
        self.assertFalse(result['database_tls_and_acl_passed']); self.transport.assert_not_called()

    def test_backend_tls_does_not_substitute_for_client_tls(self):
        conn = self.connection(ssl=False)
        conn.execute.return_value.fetchone.return_value = dict(readonly='on', ssl=True)
        result = self.run_probe(live=True)
        self.assertFalse(result['database_tls_and_acl_passed'])
        self.transport.assert_not_called()

    def test_verified_client_tls_can_end_at_managed_proxy(self):
        conn = self.connection(ssl=True)
        conn.execute.return_value.fetchone.return_value = dict(readonly='on', ssl=False)
        authority = Mock()
        authority.descriptor.return_value = dict(state='OPEN', epochs=dict(user=self.env['ROSAGO_USER_SESSION_EPOCH'],
            admin=self.env['ROSAGO_ADMIN_SESSION_EPOCH']))
        with patch.object(probe, '_verify_pool'), patch.object(probe, 'ProtectedRevisionAuthority', return_value=authority):
            result = self.run_probe(live=True)
        self.assertTrue(result['database_tls_and_acl_passed'])
        self.assertTrue(result['authority_descriptor_passed'])

    def test_real_permission_checker_is_required(self):
        self.connection()
        with patch.object(probe, '_verify_pool', side_effect=ValueError('private ACL data')):
            result = self.run_probe(live=True)
        self.assertFalse(result['database_tls_and_acl_passed']); self.transport.assert_not_called()
        self.assertNotIn('private ACL data', json.dumps(result))

    def test_component_success_never_qualifies_provider_or_application(self):
        conn = self.connection()
        authority = Mock()
        authority.descriptor.return_value = dict(state='OPEN', epochs=dict(user=self.env['ROSAGO_USER_SESSION_EPOCH'],
            admin=self.env['ROSAGO_ADMIN_SESSION_EPOCH']))
        with patch.object(probe, '_verify_pool') as acl, patch.object(probe, 'ProtectedRevisionAuthority', return_value=authority):
            result = self.run_probe(live=True)
        acl.assert_called_once()
        self.assertIs(acl.call_args.args[0].conn, conn)
        self.assertIn('default_transaction_read_only=on', self.connect.call_args.kwargs['options'])
        self.assertTrue(result['authority_descriptor_passed'])
        for name in ('supabase_contacted', 'live_signins_performed', 'session_mutations_performed',
                     'provider_security_qualified', 'application_startup_qualified', 'deployment_authorized'):
            self.assertIs(result[name], False)
        authority.maintain.assert_called_once(); authority.descriptor.assert_called_once()
        self.transport.return_value.close.assert_called_once()

    def test_authority_failure_is_closed_and_sanitized(self):
        self.connection()
        with patch.object(probe, '_verify_pool'), patch.object(probe, 'ProtectedRevisionAuthority',
                side_effect=RuntimeError(self.env['ROSAGO_AUTHORITY_CLIENT_TOKEN'])):
            result = self.run_probe(live=True)
        self.assertFalse(result['authority_descriptor_passed'])
        self.assertNotIn('private-token', json.dumps(result))
        self.transport.return_value.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
