"""Offline approval-gate and secret-custody checks; never decrypt or connect."""
import json
from pathlib import Path
import subprocess
import unittest

from pglast import parse_sql

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/production-shared-sessions'


class NeonCredentialPreparation(unittest.TestCase):
    def test_proposal_has_two_unconditional_stops_before_only_runtime_login(self):
        nodes = [r.stmt for r in parse_sql((DOCS/'credential-activation.review.sql').read_text())]
        self.assertEqual([type(n).__name__ for n in nodes],
            ['TransactionStmt','DoStmt','DoStmt','DoStmt','AlterRoleStmt','DoStmt','TransactionStmt'])
        self.assertIn('UNAPPROVED_NEON_PRIVATE_CREDENTIAL_ACTIVATION', str(nodes[1]))
        self.assertIn('PRIVATE_CLIENT_SCRAM_ASSIGNMENT_REQUIRED', str(nodes[3]))
        self.assertEqual(nodes[4].role.rolename, 'rosago_session_app')
        self.assertEqual(len(nodes[4].options), 1)
        self.assertEqual(nodes[4].options[0].defname, 'canlogin')

    def test_preflight_was_readonly_and_matches_completed_installation(self):
        v = json.loads((DOCS/'neon-credential-preparation-preflight.json').read_text())
        self.assertTrue(v['read_only_preflight_passed'])
        self.assertTrue(v['database_postflight_matches'])
        self.assertTrue(v['roles_nologin'])
        self.assertTrue(v['neondb_unchanged'])
        self.assertFalse(v['hosted_changes'])
        self.assertFalse(v['activation_performed'])
        self.assertFalse(v['supabase_contacted'])

    def test_nonsecret_receipt_has_no_credential_payload(self):
        v = json.loads((DOCS/'neon-credential-preparation.json').read_text())
        allowed = {'target_project','target_branch','target_database','target_role',
            'password_generated_privately','random_bits','password_characters','encoding',
            'local_encrypted_file','protection','acl_current_user_and_system_only',
            'dpapi_roundtrip_verified','git_ignored_and_untracked','plaintext_written_or_printed',
            'database_password_set','runtime_login_activated','owner_login_activated',
            'render_secret_updated','activation_authorized','deployment_authorized','read_only_preflight_sha256'}
        self.assertEqual(set(v), allowed)
        self.assertEqual((v['target_project'],v['target_database'],v['target_role']),
            ('broad-cake-08068289','rosago_sessions_evaluation','rosago_session_app'))
        self.assertEqual(v['random_bits'],384); self.assertEqual(v['password_characters'],64)
        self.assertTrue(v['password_generated_privately']); self.assertTrue(v['dpapi_roundtrip_verified'])
        self.assertTrue(v['acl_current_user_and_system_only'])
        for key in ('plaintext_written_or_printed','database_password_set','runtime_login_activated',
                    'owner_login_activated','render_secret_updated','activation_authorized','deployment_authorized'):
            self.assertIs(v[key],False)

    def test_encrypted_destination_is_present_ignored_and_untracked(self):
        relative='backups/neon-evaluation-credentials/rosago_session_app.seed.dpapi'
        self.assertTrue((ROOT/relative).is_file())
        self.assertGreater((ROOT/relative).stat().st_size,48)
        ignored=subprocess.run(['git','check-ignore','--no-index',relative],cwd=ROOT,capture_output=True)
        tracked=subprocess.run(['git','ls-files','--',relative],cwd=ROOT,capture_output=True)
        self.assertEqual(ignored.returncode,0)
        self.assertEqual(tracked.stdout,b'')


if __name__ == '__main__':
    unittest.main()
