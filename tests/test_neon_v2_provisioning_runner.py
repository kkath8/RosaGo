"""Pre-execution guard tests; no network, database statements or file mutation."""
import hashlib
import json
import unittest
from unittest.mock import patch

from pglast import parse_sql
from pglast.stream import RawStream
from tools import provision_neon_evaluation_sessions as runner


class NeonV2ProvisioningRunner(unittest.TestCase):
    def test_all_three_inputs_match_reviewed_hashes(self):
        texts = runner.reviewed_inputs()
        self.assertEqual(len(texts), 3)
        for (name, digest), text in zip(runner.INPUTS, texts):
            self.assertEqual(hashlib.sha256((runner.ROOT/name).read_bytes()).hexdigest(), digest)

    def test_only_approval_statement_and_final_commit_change_in_memory(self):
        texts = runner.reviewed_inputs()
        for index, db in ((0, 'neondb'), (2, runner.DATABASE)):
            with self.subTest(stage=index):
                text = texts[index];before = hashlib.sha256(text.encode()).hexdigest()
                body = runner.transaction_body(text, runner.GATES[index], db)
                original = [RawStream()(s.stmt) for s in parse_sql(text)]
                approved = [RawStream()(s.stmt) for s in parse_sql(body)]
                self.assertEqual(approved[0], 'BEGIN')
                self.assertEqual(approved[2:], original[2:-1])
                self.assertIn('current_database()', approved[1])
                self.assertIn(db, approved[1])
                self.assertIn('session_user', approved[1])
                self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), before)
        runner.reviewed_inputs()  # Disk gates/hashes remain intact.

    def test_changed_gate_rejected(self):
        with self.assertRaisesRegex(runner.Stop, 'transaction_gate_mismatch'):
            runner.transaction_body('BEGIN; COMMIT;', runner.GATES[0], 'neondb')

    def test_database_step_contains_one_create_database_only(self):
        text = runner.reviewed_inputs()[1]
        sql = '\n'.join(line for line in text.splitlines() if not line.startswith('\\'))
        statements = parse_sql(sql)
        self.assertEqual(len(statements), 1)
        self.assertEqual(type(statements[0].stmt).__name__, 'CreatedbStmt')
        self.assertEqual(statements[0].stmt.dbname, runner.DATABASE)

    def test_neon_project_mismatch_denies_before_any_other_request(self):
        with patch.object(runner, 'cli', return_value=json.dumps({'project':{'id':'unexpected','org_id':runner.ORG}})) as call:
            with self.assertRaisesRegex(runner.Stop, 'project_identity_mismatch'):
                runner.metadata()
        self.assertEqual(call.call_count, 1)

    def test_neon_endpoint_mismatch_denies(self):
        values = [dict(project=dict(id=runner.PROJECT,org_id=runner.ORG)),
                  dict(branches=[dict(id=runner.BRANCH,project_id=runner.PROJECT)]),
                  dict(endpoints=[dict(branch_id=runner.BRANCH,host='wrong.example',type='read_write')])]
        with patch.object(runner, 'cli', side_effect=[json.dumps(v) for v in values]):
            with self.assertRaisesRegex(runner.Stop, 'endpoint_identity_mismatch'):
                runner.metadata()

    def test_connection_target_mismatch_denies_without_printing_password(self):
        with patch.object(runner, 'cli', return_value='postgresql://neondb_owner:private-value@wrong.example/neondb'):
            with self.assertRaises(runner.Stop) as caught:
                runner.connection_values()
        self.assertNotIn('private-value', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
