"""Static SQL contracts only; no database execution or live RLS proof."""
import hashlib
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DraftMigrationTests(unittest.TestCase):
    def setUp(self):
        raw = (ROOT / 'migrations/0005_itinerary_draft_lifecycle.sql').read_text()
        self.sql = re.sub(r'--[^\n]*', '', raw)
        self.flat = ' '.join(self.sql.split())
        self.functions = dict(re.findall(r'CREATE FUNCTION public\.(\w+)(\(.*?\$\$;)', self.sql, re.S))
        top = re.sub(r'\$\$.*?\$\$', '$$BODY$$', self.sql, flags=re.S)
        self.statements = [' '.join(s.split()) for s in top.split(';') if s.strip()]

    def body(self, name):
        return ' '.join(self.functions[name].split())

    def test_applied_0001_through_0004_unchanged(self):
        hashes = {
            '0001_profiles.sql': '3d1164c291775e56a6d52eec0f47f8169a5ae811c5de8410864b705a00b406f5',
            '0002_places.sql': '472757526f37398e67408bd4871f6cb729c66084c29d09a38349d4e0d81864ea',
            '0003_trips.sql': '419cbf2977a0b3646326d041338af66277d4f7a8340e3a6a1ad24f4eb187cb6d',
            '0004_itinerary_foundation.sql': '0754c2aa007f95d61158468f627ece33bf8b8183ccb7d0cc8d372a4b840b9298',
        }
        for name, expected in hashes.items():
            data = (ROOT / 'migrations' / name).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, name)

    def test_function_scope_owner_security_and_grants(self):
        signatures = {'rosago_validate_draft_preferences': '(jsonb)',
                      'rosago_itinerary_draft_create': '()',
                      'rosago_itinerary_draft_update_preferences': '(uuid, bigint, jsonb)'}
        self.assertEqual(set(self.functions), set(signatures))
        for name, signature in signatures.items():
            self.assertIn("SET search_path = ''", self.body(name))
            self.assertIn(f'ALTER FUNCTION public.{name}{signature} OWNER TO postgres', self.statements)
        self.assertIn('SECURITY INVOKER', self.body('rosago_validate_draft_preferences'))
        for name in ('rosago_itinerary_draft_create', 'rosago_itinerary_draft_update_preferences'):
            body = self.body(name)
            self.assertIn('SECURITY DEFINER', body)
            self.assertIn('owner_id uuid := auth.uid()', body)
            self.assertIn("IF owner_id IS NULL THEN RAISE EXCEPTION USING ERRCODE = '42501'", body)
            self.assertIn('RETURNS TABLE (draft_id uuid, state text, revision bigint)', body)
            self.assertNotIn('user_id', body.split('RETURNS')[0])
        self.assertEqual([s for s in self.statements if s.startswith('GRANT')], [
            'GRANT EXECUTE ON FUNCTION public.rosago_itinerary_draft_create(), '
            'public.rosago_itinerary_draft_update_preferences(uuid, bigint, jsonb) TO authenticated'])
        self.assertIn('REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_validate_draft_preferences(jsonb), '
                      'public.rosago_itinerary_draft_create(), '
                      'public.rosago_itinerary_draft_update_preferences(uuid, bigint, jsonb) '
                      'FROM PUBLIC, anon, authenticated, service_role', self.statements)

    def test_no_schema_policy_or_direct_table_privilege_changes(self):
        self.assertEqual(self.statements[0], 'BEGIN')
        self.assertEqual(self.statements[-1], 'COMMIT')
        for statement in self.statements[1:-1]:
            self.assertRegex(statement, r'^(CREATE FUNCTION|ALTER FUNCTION|REVOKE ALL PRIVILEGES ON FUNCTION|GRANT EXECUTE ON FUNCTION) ')
            if 'service_role' in statement:
                self.assertTrue(statement.startswith('REVOKE'))
        self.assertNotRegex(self.flat, r'(?i)\b(DROP|TRUNCATE|DELETE FROM|CREATE OR REPLACE|EXECUTE IMMEDIATE)\b')
        self.assertNotRegex(self.flat, r'(?i)(INSERT INTO|UPDATE) public\.(trips|trip_places|places|trip_itinerary|trip_stop_plans)\b')
        self.assertNotRegex(self.flat, r'(?i)\b(access_token|refresh_token|http|dblink)\b')

    def test_create_fixed_state_owner_and_existing_defaults(self):
        body = self.body('rosago_itinerary_draft_create')
        self.assertTrue(body.startswith('() RETURNS TABLE'))
        self.assertIn("(user_id, state, schema_version, revision) VALUES (owner_id, 'editing', 1, 1)", body)
        self.assertIn('RETURNING draft.id, draft.state, draft.revision', body)
        self.assertNotRegex(body, r'\b(preview|saved_at|saved_trip_id|preferences|expires_at)\b')

    def test_update_only_preferences_revision_with_post_lock_expiry(self):
        body = self.body('rosago_itinerary_draft_update_preferences')
        self.assertTrue(body.startswith('( p_draft_id uuid, p_expected_revision bigint, p_preferences jsonb)'))
        self.assertNotIn('transaction_isolation', self.sql)
        self.assertNotIn('current_setting', body)
        for clause in ('p_draft_id IS NULL OR p_expected_revision IS NULL',
                       'p_expected_revision NOT BETWEEN 1 AND 9223372036854775806',
                       'WHERE draft.id = p_draft_id AND draft.user_id = owner_id FOR UPDATE',
                       'SET preferences = validated_preferences, revision = draft.revision + 1',
                       "draft.state = 'editing' AND draft.schema_version = 1",
                       'draft.expires_at > pg_catalog.clock_timestamp()',
                       'draft.revision = p_expected_revision',
                       "IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0002'"):
            self.assertIn(clause, body)
        self.assertLess(body.index('FOR UPDATE'), body.index('draft.expires_at >'))
        assignments = body.split('UPDATE public.itinerary_drafts AS draft SET ', 1)[1].split(' WHERE ', 1)[0]
        self.assertEqual(assignments, 'preferences = validated_preferences, revision = draft.revision + 1')
        self.assertEqual(body.count("MESSAGE = 'Draft update rejected.'"), 2)

    def test_complete_json_shape_types_and_server_timezone(self):
        body = self.body('rosago_validate_draft_preferences')
        for clause in ("jsonb_typeof(p_preferences) <> 'object'", 'octet_length(p_preferences::text) > 16384',
                       'p_preferences ?& ARRAY[', 'jsonb_object_keys(p_preferences)', 'WHERE k.key NOT IN',
                       "jsonb_typeof(p_preferences -> field_name) IS DISTINCT FROM 'string'",
                       "IS DISTINCT FROM '\"Asia/Manila\"'::jsonb",
                       "jsonb_typeof(p_preferences -> 'interests') IS DISTINCT FROM 'array'",
                       "jsonb_array_length(p_preferences -> 'interests') NOT BETWEEN 1 AND 6",
                       "jsonb_typeof(i.value) <> 'string'", 'rosago_itinerary_interests_valid(selected_interests)',
                       "'timezone', 'Asia/Manila', 'budget_centavos', COALESCE(p_preferences -> 'budget_centavos', 'null'::jsonb)"):
            self.assertIn(clause, body)

    def test_preference_enum_budget_date_time_bounds(self):
        body = self.body('rosago_validate_draft_preferences')
        for clause in ("('solo', 'couple', 'family', 'friends', 'group')",
                       "('walking', 'private_car', 'public_transport')",
                       "jsonb_typeof(p_preferences -> 'budget_centavos') <> 'number'",
                       "'^(0|[1-9][0-9]{0,7})$'", "(p_preferences ->> 'budget_centavos')::bigint > 10000000",
                       "'^[0-9]{4}-[0-9]{2}-[0-9]{2}$'",
                       "'^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$'",
                       'EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow',
                       "first_date NOT BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'",
                       'last_date NOT BETWEEN first_date AND first_date + 6', 'last_time <= first_time'):
            self.assertIn(clause, body)

        self.assertNotIn('24:00:00', body)

    def test_fixed_errors_no_raw_diagnostics(self):
        for statement in re.findall(r'RAISE EXCEPTION(.*?);', self.sql, re.S):
            self.assertRegex(' '.join(statement.split()),
                             r"^USING ERRCODE = '(22023|42501|P0002)', MESSAGE = '[A-Za-z .]+'$")
        self.assertNotIn('SQLERRM', self.sql)
        for definition in self.functions.values():
            self.assertNotRegex(definition.split('$$')[1], r'\bEXECUTE\b')


if __name__ == '__main__':
    unittest.main()
