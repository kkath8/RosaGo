"""Offline contract checks; never connect to a database or execute SQL."""
import hashlib
import json
from pathlib import Path
import unittest

try:
    from pglast.parser import parse_sql_json, parse_plpgsql_json
except ImportError:
    parse_sql_json = parse_plpgsql_json = None

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / 'tools/admin_destination_photo_contract.sql'
VERIFY = ROOT / 'tools/verify_admin_photo_contract.sql'
BACKUP = ROOT / 'tools/backup_admin_photo_contract.sql'
ROLLBACK = ROOT / 'tools/rollback_admin_destination_photo_contract.sql'


def function_body(text):
    start = text.index('AS $$') + len('AS $$')
    return text[start:text.index('$$;', start)].replace('\r', '')


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


class PhotoSQLContractTests(unittest.TestCase):
    def test_preflight_binds_both_checks_to_exact_function_oids(self):
        preflight = DEPLOY.read_text(encoding='utf-8').split('CREATE OR REPLACE FUNCTION', 1)[0]
        self.assertIn("'public.rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)'", preflight)
        self.assertIn("'public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)'", preflight)
        self.assertEqual(preflight.count('pg_catalog.to_regprocedure('), 2)
        self.assertIn('WHERE p.oid=wrapper_oid', preflight)
        self.assertIn('WHERE p.oid=inner_oid', preflight)
        self.assertNotIn('p.proname', preflight)
        self.assertIn('inner_oid IS NULL OR wrapper_oid IS NULL', preflight)

    def test_photo_mutation_body_only_adds_optional_image_handling(self):
        original = function_body((ROOT / 'migrations/0012_admin_management.sql').read_text(encoding='utf-8'))
        prepared = function_body(DEPLOY.read_text(encoding='utf-8'))
        restored = prepared.replace("'longitude','image_url',", "'longitude',", 1)
        start = restored.index('        -- Only the optional image field')
        end = restored.index('        tourism_fields :=', start)
        restored = restored[:start] + restored[end:]
        start = restored.index("        IF p_values ? 'image_url' THEN")
        end = restored.index('        IF tourism_fields THEN', start)
        restored = restored[:start] + restored[end:]
        self.assertEqual(original, restored)

    def test_verification_hashes_cover_baseline_photo_and_audit_wrapper(self):
        verification = VERIFY.read_text(encoding='utf-8')
        for path in [ROOT / 'migrations/0012_admin_management.sql', DEPLOY,
                     ROOT / 'migrations/0013_admin_destination_audit.sql']:
            digest = hashlib.md5(function_body(path.read_text(encoding='utf-8')).encode()).hexdigest()
            self.assertIn(digest, verification)
        self.assertNotRegex(verification, r'INNER_(?:BASELINE|PHOTO)_HASH|WRAPPER_BASELINE_HASH')

    def test_verifier_has_required_effective_privilege_and_failure_checks(self):
        verification = VERIFY.read_text(encoding='utf-8')
        for contract in ['pg_catalog.has_function_privilege', 'pg_catalog.has_schema_privilege',
                         'pg_catalog.aclexplode', 'pg_catalog.acldefault', 'pg_catalog.pg_has_role',
                         "'USAGE'", "'SET'", "'MEMBER'", 'a.grantee=0',
                         'FAIL_AUTHENTICATED_HAS_DIRECT_OR_INHERITED_INNER_EXECUTE',
                         'FAIL_AUTHENTICATED_CAN_ASSUME_INNER_EXECUTOR', 'FAIL_FUNCTION_MISSING',
                         'FAIL_REQUIRED_ROLE_MISSING', 'PASS_PHOTO_CONTRACT_ALREADY_APPLIED',
                         'prosecdef', 'proconfig', 'proowner', 'pg_catalog.pg_get_functiondef',
                         'FAIL_PUBLIC_EXECUTE', 'source_md5', 'REPEATABLE READ READ ONLY']:
            self.assertIn(contract, verification)

    def test_backup_exports_definitions_ownership_and_complete_acl_metadata(self):
        backup = BACKUP.read_text(encoding='utf-8')
        for required in ['REPEATABLE READ READ ONLY', 'pg_catalog.to_regprocedure',
                         'pg_catalog.pg_get_functiondef', 'owner_oid', 'owner_name',
                         'raw_acl', 'acl_uses_default', 'pg_catalog.acldefault',
                         'pg_catalog.aclexplode', 'grantor', 'grantee', 'grant_option',
                         'source_md5', 'expected_baseline_md5']:
            self.assertIn(required, backup)
        self.assertEqual(backup.count('pg_catalog.to_regprocedure'), 1)

    def test_rollback_restores_exact_old_body_without_permission_or_wrapper_changes(self):
        original = function_body((ROOT / 'migrations/0012_admin_management.sql').read_text(encoding='utf-8'))
        rollback = ROLLBACK.read_text(encoding='utf-8')
        self.assertEqual(function_body(rollback), original)
        self.assertEqual(rollback.count('CREATE OR REPLACE FUNCTION'), 1)
        self.assertIn('CREATE OR REPLACE FUNCTION public.rosago_admin_mutate_destination_unlogged(', rollback)
        self.assertNotIn('REVOKE ', rollback)
        self.assertNotIn('GRANT ', rollback)
        self.assertNotIn('ALTER ', rollback)
        self.assertNotIn('DROP ', rollback)
        self.assertIn('WHERE p.oid=inner_oid', rollback)
        self.assertIn('WHERE p.oid=wrapper_oid', rollback)
        self.assertIn(hashlib.md5(function_body(DEPLOY.read_text(encoding='utf-8')).encode()).hexdigest(), rollback)
        self.assertIn(hashlib.md5(function_body((ROOT / 'migrations/0013_admin_destination_audit.sql').read_text(encoding='utf-8')).encode()).hexdigest(), rollback)

    @unittest.skipUnless(parse_sql_json, 'Optional pglast parser is not installed')
    def test_sql_and_plpgsql_parse_offline(self):
        self.assertEqual(len(json.loads(parse_sql_json(DEPLOY.read_text(encoding='utf-8')))['stmts']), 5)
        self.assertTrue(parse_plpgsql_json(DEPLOY.read_text(encoding='utf-8')))
        self.assertEqual(len(json.loads(parse_sql_json(VERIFY.read_text(encoding='utf-8')))['stmts']), 3)
        self.assertEqual(len(json.loads(parse_sql_json(BACKUP.read_text(encoding='utf-8')))['stmts']), 3)
        self.assertEqual(len(json.loads(parse_sql_json(ROLLBACK.read_text(encoding='utf-8')))['stmts']), 4)
        self.assertTrue(parse_plpgsql_json(ROLLBACK.read_text(encoding='utf-8')))

    @unittest.skipUnless(parse_sql_json, 'Optional pglast parser is not installed')
    def test_backup_is_readonly_and_rollback_defines_only_the_inner_function(self):
        backup = json.loads(parse_sql_json(BACKUP.read_text(encoding='utf-8')))
        statements = [s['stmt'] for s in backup['stmts']]
        self.assertEqual([next(iter(s)) for s in statements], ['TransactionStmt','SelectStmt','TransactionStmt'])
        self.assertTrue(any(option['DefElem']['defname']=='transaction_read_only'
                            and option['DefElem']['arg']['A_Const']['ival']['ival']==1
                            for option in statements[0]['TransactionStmt']['options']))
        for node in nodes(backup):
            if 'RangeVar' in node:
                relation = node['RangeVar']
                self.assertTrue(relation.get('schemaname')=='pg_catalog'
                                or relation.get('relname') in ('expected','targets'))
        rollback = json.loads(parse_sql_json(ROLLBACK.read_text(encoding='utf-8')))
        self.assertEqual([next(iter(s['stmt'])) for s in rollback['stmts']],
                         ['TransactionStmt','DoStmt','CreateFunctionStmt','TransactionStmt'])
        created = rollback['stmts'][2]['stmt']['CreateFunctionStmt']
        self.assertEqual([part['String']['sval'] for part in created['funcname']],
                         ['public','rosago_admin_mutate_destination_unlogged'])

    @unittest.skipUnless(parse_sql_json, 'Optional pglast parser is not installed')
    def test_verifier_ast_is_readonly_catalog_inspection(self):
        parsed = json.loads(parse_sql_json(VERIFY.read_text(encoding='utf-8')))
        statements = [statement['stmt'] for statement in parsed['stmts']]
        self.assertEqual([next(iter(statement)) for statement in statements],
                         ['TransactionStmt', 'SelectStmt', 'TransactionStmt'])
        options = statements[0]['TransactionStmt']['options']
        self.assertTrue(any(option['DefElem']['defname'] == 'transaction_read_only'
                            and option['DefElem']['arg']['A_Const']['ival']['ival'] == 1 for option in options))
        ctes = {'expected', 'targets', 'functions', 'execute_acl', 'role_access', 'role_report', 'report'}
        for node in nodes(parsed):
            self.assertFalse(set(node) & {'InsertStmt', 'UpdateStmt', 'DeleteStmt', 'MergeStmt',
                                         'CreateFunctionStmt', 'GrantStmt', 'DoStmt', 'CallStmt', 'ExecuteStmt'})
            if 'RangeVar' in node:
                relation = node['RangeVar']
                self.assertTrue(relation.get('schemaname') == 'pg_catalog'
                                or relation.get('relname') in ctes, relation)
            if 'FuncCall' in node:
                name = [part['String']['sval'] for part in node['FuncCall']['funcname']]
                self.assertEqual(name[0], 'pg_catalog', name)
            if 'SelectStmt' in node:
                self.assertNotIn('intoClause', node['SelectStmt'])
                self.assertNotIn('lockingClause', node['SelectStmt'])


if __name__ == '__main__':
    unittest.main()
