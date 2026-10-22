"""Static SQL contracts only: never execute migrations or contact a database."""
import hashlib
from pathlib import Path
import re
import unittest

from itinerary_draft_service import (
    REQUIRED, EXTENDED_REQUIRED, TEXT_LIMITS, TRANSPORTATION, TRIP_PACES, ACTIVITIES, ENVIRONMENTS,
)

ROOT = Path(__file__).resolve().parents[1]


class PreferenceExtensionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.sql = re.sub(r'--[^\n]*', '', (ROOT / 'migrations/0006_itinerary_preference_extension.sql').read_text())
        self.flat = ' '.join(self.sql.split())

    def test_live_migrations_0001_through_0005_unchanged(self):
        hashes = {
            '0001_profiles.sql': '3d1164c291775e56a6d52eec0f47f8169a5ae811c5de8410864b705a00b406f5',
            '0002_places.sql': '472757526f37398e67408bd4871f6cb729c66084c29d09a38349d4e0d81864ea',
            '0003_trips.sql': '419cbf2977a0b3646326d041338af66277d4f7a8340e3a6a1ad24f4eb187cb6d',
            '0004_itinerary_foundation.sql': '0754c2aa007f95d61158468f627ece33bf8b8183ccb7d0cc8d372a4b840b9298',
            '0005_itinerary_draft_lifecycle.sql': '935cc40b7d783e78b11f1ee64f660456d3f3f42c6617fe35d7d32442bc382e9a',
        }
        for name, expected in hashes.items():
            data = (ROOT / 'migrations' / name).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, name)

    def test_replaces_only_private_validator_and_preserves_security(self):
        top = re.sub(r'\$\$.*?\$\$', '$$BODY$$', self.sql, flags=re.S)
        statements = [' '.join(part.split()) for part in top.split(';') if part.strip()]
        self.assertEqual(statements, [
            'BEGIN',
            "CREATE OR REPLACE FUNCTION public.rosago_validate_draft_preferences(p_preferences jsonb) "
            "RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$BODY$$",
            'ALTER FUNCTION public.rosago_validate_draft_preferences(jsonb) OWNER TO postgres',
            'REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_validate_draft_preferences(jsonb) '
            'FROM PUBLIC, anon, authenticated, service_role',
            'COMMIT',
        ])
        self.assertNotRegex(self.flat, r'\b(GRANT|SECURITY DEFINER|CREATE TABLE|ALTER TABLE|POLICY|DROP|INSERT|UPDATE|DELETE|EXECUTE)\b')
        self.assertNotIn('rosago_itinerary_draft_create', self.sql)
        self.assertNotIn('rosago_itinerary_draft_update_preferences', self.sql)
        self.assertNotIn('SQLERRM', self.sql)
        errors = re.findall(r'RAISE EXCEPTION(.*?);', self.sql, re.S)
        self.assertTrue(errors)
        for error in errors:
            self.assertEqual(' '.join(error.split()),
                             "USING ERRCODE = '22023', MESSAGE = 'Invalid draft preferences.'")

    def test_exact_keys_and_enums_match_python(self):
        required = re.search(r'p_preferences \?& ARRAY\[(.*?)\]', self.sql, re.S).group(1)
        allowed = re.search(r'WHERE k.key NOT IN \((.*?)\)', self.sql, re.S).group(1)
        quoted = lambda value: set(re.findall(r"'([^']*)'", value))
        self.assertEqual(quoted(required), REQUIRED | EXTENDED_REQUIRED)
        self.assertEqual(quoted(allowed), REQUIRED | EXTENDED_REQUIRED | TEXT_LIMITS.keys() | {'budget_centavos', 'timezone'})
        for key, values in (('transportation', TRANSPORTATION), ('trip_pace', TRIP_PACES),
                            ('environment_preference', ENVIRONMENTS)):
            clause = re.search(r"p_preferences ->> '" + key + r"' NOT IN \((.*?)\)", self.sql, re.S).group(1)
            self.assertEqual(quoted(clause), set(values))
        activity = re.search(r"i.value #>> '\{\}' NOT IN \((.*?)\)", self.sql, re.S).group(1)
        self.assertEqual(quoted(activity), set(ACTIVITIES))

    def test_new_types_arrays_text_normalization_and_bounds(self):
        for clause in (
            "jsonb_typeof(p_preferences -> 'activity_preferences') IS DISTINCT FROM 'array'",
            "jsonb_array_length(p_preferences -> 'activity_preferences') NOT BETWEEN 1 AND 6",
            "jsonb_typeof(i.value) <> 'string'", 'pg_catalog.count(DISTINCT i.value)',
            "jsonb_typeof(p_preferences -> field_name) IS DISTINCT FROM 'string'",
            "ARRAY['other_interests', 'additional_preferences']",
            "CASE WHEN field_name = 'other_interests' THEN 200 ELSE 500 END",
            'pg_catalog.char_length(free_text) > text_limit',
            "pg_catalog.jsonb_build_object(field_name, NULLIF(free_text, ''))",
        ):
            self.assertIn(clause, self.flat)
        trim = re.search(r"U&'([^']+)'", self.sql).group(1)
        actual = {int(code, 16) for code in re.findall(r'\\([0-9A-F]{4})', trim)}
        # Python's Unicode whitespace is contained in the BMP.
        self.assertEqual(actual, {cp for cp in range(65536) if chr(cp).isspace()})

    def test_existing_budget_date_time_and_timezone_rules_retained(self):
        for clause in (
            'octet_length(p_preferences::text) > 16384',
            'rosago_itinerary_interests_valid(selected_interests)',
            "('solo', 'couple', 'family', 'friends', 'group')",
            "jsonb_typeof(p_preferences -> 'budget_centavos') <> 'number'",
            "'^(0|[1-9][0-9]{0,7})$'", "(p_preferences ->> 'budget_centavos')::bigint > 10000000",
            "'^[0-9]{4}-[0-9]{2}-[0-9]{2}$'",
            "'^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$'",
            'EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow',
            "first_date NOT BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'",
            "last_date NOT BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'",
            'last_date NOT BETWEEN first_date AND first_date + 6', 'last_time <= first_time',
            "IS DISTINCT FROM '\"Asia/Manila\"'::jsonb",
            "'timezone', 'Asia/Manila', 'budget_centavos', COALESCE(p_preferences -> 'budget_centavos', 'null'::jsonb)",
        ):
            self.assertIn(clause, self.flat)


if __name__ == '__main__':
    unittest.main()
