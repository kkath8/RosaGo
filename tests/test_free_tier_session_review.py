"""Static proposal checks only. No SQL execution, service imports or networking."""
import hashlib
import json
from pathlib import Path
import tomllib
import unittest

from pglast import parse_sql
from pglast.stream import RawStream

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'docs/production-shared-sessions/neon-evaluation-review'
NEW = ROOT / 'docs/production-shared-sessions/free-tier-review'


class FreeTierSessionReview(unittest.TestCase):
    def sql(self, name):
        return (NEW / name).read_text(encoding='utf-8')

    def statements(self, name):
        return [RawStream()(item.stmt) for item in parse_sql(self.sql(name))]

    def test_original_review_and_evidence_hashes_preserved(self):
        index = json.loads((OLD / 'review-index.json').read_text())
        for name, expected in index['files'].items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((OLD / name).read_bytes()).hexdigest(), expected)

    def test_each_transaction_has_an_unconditional_approval_failure_before_ddl(self):
        for name in ('01-roles.v2.review.sql', '03-payload-schema.v2.review.sql'):
            with self.subTest(file=name):
                statements = self.statements(name)
                self.assertEqual(statements[0], 'BEGIN')
                self.assertIn('RAISE EXCEPTION', statements[1])
                self.assertIn('UNAPPROVED_NEON_SESSION_', statements[1])
                self.assertEqual(statements[-1], 'COMMIT')

    def test_new_roles_stay_nologin_and_without_parent_membership(self):
        statements = self.statements('01-roles.v2.review.sql')
        roles = [s for s in statements if s.startswith('CREATE ROLE')]
        self.assertEqual(len(roles), 2)
        for sql in roles:
            for option in ('NOLOGIN', 'NOSUPERUSER', 'NOCREATEDB', 'NOCREATEROLE',
                           'NOINHERIT', 'NOREPLICATION', 'NOBYPASSRLS'):
                self.assertIn(option, sql)
            self.assertNotIn('PASSWORD', sql)
            self.assertNotIn(' IN ROLE ', sql)

    def test_temporary_membership_has_explicit_operator_grantor(self):
        grant = [s for s in self.statements('01-roles.v2.review.sql') if s.startswith('GRANT ')]
        self.assertEqual(len(grant), 1)
        self.assertIn('rosago_session_owner TO neondb_owner', grant[0])
        self.assertIn('GRANTED BY neondb_owner', grant[0])
        self.assertIn('INHERIT FALSE', grant[0]); self.assertIn('SET OPTION', grant[0])

    def test_database_owner_is_active_before_owner_only_acl_changes(self):
        statements = self.statements('03-payload-schema.v2.review.sql')
        owner = next(i for i, s in enumerate(statements) if s == "SET LOCAL role TO 'rosago_session_owner'")
        for i, sql in enumerate(statements):
            if ((sql.startswith(('REVOKE ', 'GRANT '))
                 and any(scope in sql for scope in (' ON DATABASE ', ' ON SCHEMA ')))
                    or sql.startswith('CREATE SCHEMA')):
                self.assertGreater(i, owner)

    def test_only_operator_issued_role_grant_is_revoked(self):
        statements = self.statements('03-payload-schema.v2.review.sql')
        revokes = [s for s in statements if s.startswith('REVOKE rosago_session_')]
        self.assertEqual(revokes, ['REVOKE rosago_session_owner FROM neondb_owner GRANTED BY neondb_owner'])
        self.assertLess(statements.index('RESET role'), statements.index(revokes[0]))

    def test_payload_constraints_policy_and_index_match_previous_proposal(self):
        def selected(text):
            return [RawStream()(item.stmt) for item in parse_sql(text)
                    if type(item.stmt).__name__ in ('CreateStmt', 'IndexStmt', 'CreatePolicyStmt', 'AlterTableStmt')]
        self.assertEqual(selected(self.sql('03-payload-schema.v2.review.sql')),
                         selected((OLD / '03-payload-schema.review.sql').read_text()))

    def test_database_creation_stays_separate_and_non_executable(self):
        text = (OLD / '02-database.review.psql').read_text()
        self.assertLess(text.index('\\quit 3'), text.index('CREATE DATABASE rosago_sessions_evaluation'))
        statements = parse_sql('\n'.join(line for line in text.splitlines() if not line.startswith('\\')))
        self.assertEqual(len(statements), 1)
        self.assertEqual(type(statements[0].stmt).__name__, 'CreatedbStmt')

    def test_existing_cloudflare_config_is_sqlite_and_still_not_public(self):
        config = tomllib.loads((ROOT / 'evaluation/infrastructure/authority/wrangler.review.toml').read_text())
        self.assertIs(config['workers_dev'], False)
        self.assertIs(config['preview_urls'], False)
        self.assertEqual(config['migrations'][0]['new_sqlite_classes'], ['SessionAuthority'])
        self.assertEqual(config['durable_objects']['bindings'][0]['name'], 'AUTHORITY')
        self.assertNotIn('account_id', config)


if __name__ == '__main__':
    unittest.main()
