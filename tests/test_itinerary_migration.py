"""Offline SQL text contracts only; no SQL execution or proof of live RLS."""
import hashlib
from pathlib import Path
import re
import socket
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def compact(text):
    return ' '.join(text.split())


class ItineraryMigrationTests(unittest.TestCase):
    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        raw = (ROOT / 'migrations/0004_itinerary_foundation.sql').read_text(encoding='utf-8')
        self.sql = re.sub(r'--[^\n]*|/\*.*?\*/', '', raw, flags=re.S)
        self.flat = compact(self.sql)
        self.tables = dict(re.findall(r'CREATE TABLE public\.(\w+) \((.*?)\);', self.sql, re.S))
        self.functions = dict(re.findall(r'CREATE FUNCTION public\.(\w+)(\(.*?\$\$;)', self.sql, re.S))
        top = re.sub(r'\$\$.*?\$\$', '$$BODY$$', self.sql, flags=re.S)
        self.statements = [compact(s) for s in top.split(';') if s.strip()]
        self.notes = (ROOT / 'migrations/0004_itinerary_foundation_design.md').read_text(encoding='utf-8')

    def table(self, name):
        return compact(self.tables[name])

    def test_applied_migrations_have_unchanged_normalized_content(self):
        # Normalize line endings only, so Windows checkout settings do not fail this guard.
        expected = {
            '0001_profiles.sql': '3d1164c291775e56a6d52eec0f47f8169a5ae811c5de8410864b705a00b406f5',
            '0002_places.sql': '472757526f37398e67408bd4871f6cb729c66084c29d09a38349d4e0d81864ea',
            '0003_trips.sql': '419cbf2977a0b3646326d041338af66277d4f7a8340e3a6a1ad24f4eb187cb6d',
        }
        for name, digest in expected.items():
            data = (ROOT / 'migrations' / name).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, name)

    def test_only_three_optional_tables_and_additive_objects(self):
        self.assertEqual(set(self.tables), {'itinerary_drafts', 'trip_itinerary', 'trip_stop_plans'})
        self.assertEqual(self.statements[0], 'BEGIN')
        self.assertEqual(self.statements[-1], 'COMMIT')
        for statement in self.statements[1:-1]:
            self.assertRegex(statement, r'^(CREATE (TABLE|INDEX|UNIQUE INDEX|POLICY|FUNCTION|TRIGGER)|ALTER TABLE|GRANT|REVOKE)\b')
        self.assertNotRegex(self.flat, r'(?i)\b(DROP|TRUNCATE|INSERT INTO|DELETE FROM|CREATE EXTENSION|SECURITY DEFINER)\b')
        self.assertNotRegex(self.flat, r'(?i)IF NOT EXISTS|CREATE OR REPLACE|DISABLE ROW LEVEL SECURITY')
        self.assertNotRegex(self.flat, r'(?i)(ALTER TABLE|UPDATE) public\.(trips|trip_places|places|profiles)\b')
        self.assertNotRegex(self.flat, r'(?i)\b(access_token|refresh_token|http|dblink|SET ROLE)\b')
        for statement in self.statements:
            if statement.startswith('CREATE TRIGGER'):
                self.assertRegex(statement, r' ON public\.(itinerary_drafts|trip_itinerary|trip_stop_plans) ')

    def test_read_only_acl_and_exact_owner_policies(self):
        tables = 'public.itinerary_drafts, public.trip_itinerary, public.trip_stop_plans'
        grants = [s for s in self.statements if s.startswith('GRANT')]
        self.assertEqual(grants, [f'GRANT SELECT ON TABLE {tables} TO authenticated'])
        self.assertIn(f'REVOKE ALL PRIVILEGES ON TABLE {tables} FROM PUBLIC, anon, authenticated, service_role', self.statements)
        for name in self.tables:
            self.assertIn(f'ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY', self.statements)
        policies = [s for s in self.statements if s.startswith('CREATE POLICY')]
        self.assertEqual(len(policies), 3)
        self.assertIn('CREATE POLICY itinerary_drafts_select_own ON public.itinerary_drafts '
                      'FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()))', policies)
        for name in ('trip_itinerary', 'trip_stop_plans'):
            self.assertIn(f'CREATE POLICY {name}_select_own ON public.{name} FOR SELECT TO authenticated '
                          'USING (EXISTS ( SELECT 1 FROM public.trips AS trip '
                          f'WHERE trip.id = {name}.trip_id AND trip.user_id = (SELECT auth.uid()) ))', policies)
        # service_role appears only in revocations, never as runtime authority.
        for statement in self.statements:
            if 'service_role' in statement:
                self.assertTrue(statement.startswith('REVOKE ALL PRIVILEGES'))

    def test_draft_identity_documents_lifecycle_and_expiry(self):
        draft = self.table('itinerary_drafts')
        for clause in (
            'id uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()',
            'user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE',
            "state IN ('editing', 'generating', 'preview_ready', 'failed', 'saved', 'expired')",
            'schema_version = 1 AND revision > 0',
            "jsonb_typeof(preferences) = 'object'", 'octet_length(preferences::text) <= 16384',
            "jsonb_typeof(preview) = 'object'", 'octet_length(preview::text) <= 262144',
            "expires_at timestamptz NOT NULL DEFAULT (now() + INTERVAL '24 hours')",
            "expires_at <= created_at + INTERVAL '24 hours'", 'expires_at > created_at',
            'isfinite(created_at) AND isfinite(updated_at) AND isfinite(expires_at)',
        ):
            self.assertIn(clause, draft)

    def test_saved_draft_link_ownership_and_deletion_tombstone(self):
        draft = self.table('itinerary_drafts')
        self.assertIn('saved_trip_id uuid REFERENCES public.trips(id) ON DELETE SET NULL', draft)
        self.assertIn("state = 'saved' AND saved_at IS NOT NULL AND accepted_preview_digest IS NOT NULL", draft)
        self.assertIn("state <> 'saved' AND saved_trip_id IS NULL AND saved_at IS NULL AND accepted_preview_digest IS NULL", draft)
        self.assertIn('saved_at IS NULL OR (isfinite(saved_at) AND saved_at >= created_at)', draft)
        self.assertNotIn('saved_at < expires_at', draft)
        self.assertIn("accepted_preview_digest COLLATE \"C\" ~ '^[0-9a-f]{64}$'", draft)
        self.assertIn('CREATE UNIQUE INDEX itinerary_drafts_saved_trip_idx ON public.itinerary_drafts '
                      '(saved_trip_id) WHERE saved_trip_id IS NOT NULL', self.statements)
        self.assertIn('WHERE trip.id = NEW.saved_trip_id AND trip.user_id = NEW.user_id FOR KEY SHARE', self.flat)
        self.assertIn("IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Saved trip unavailable.'", self.flat)

    def test_interests_are_unique_bounded_supported_and_non_null(self):
        body = compact(self.functions['rosago_itinerary_interests_valid'])
        for clause in ('IMMUTABLE', 'SELECT COALESCE(',
                       'pg_catalog.array_ndims(values_to_check) = 1',
                       'pg_catalog.array_lower(values_to_check, 1) = 1',
                       'pg_catalog.cardinality(values_to_check) BETWEEN 1 AND 6',
                       'values_to_check <@ ARRAY[',
                       'pg_catalog.cardinality(values_to_check) = ( SELECT pg_catalog.count(DISTINCT item.value)',
                       'pg_catalog.unnest(values_to_check) AS item(value)', '), false)'):
            self.assertIn(clause, body)
        categories = {'attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage'}
        self.assertEqual(set(re.findall(r"'([a-z_]+)'", body)), categories)
        places = (ROOT / 'migrations/0002_places.sql').read_text()
        allowed = re.search(r"category IN \((.*?)\)", places).group(1)
        self.assertEqual(set(re.findall(r"'([^']+)'", allowed)), categories)
        self.assertIn('interests text[] NOT NULL', self.table('trip_itinerary'))
        self.assertIn('CHECK ( public.rosago_itinerary_interests_valid(interests))', self.flat)

    def test_typed_preferences_and_fingerprint_bounds(self):
        table = self.table('trip_itinerary')
        for clause in (
            'trip_id uuid NOT NULL PRIMARY KEY REFERENCES public.trips(id) ON DELETE CASCADE',
            "companion_type IN ('solo', 'couple', 'family', 'friends', 'group')",
            'budget_centavos bigint', 'budget_centavos IS NULL OR budget_centavos BETWEEN 0 AND 10000000)',
            "start_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'",
            "end_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'",
            'end_date BETWEEN start_date AND start_date + 6',
            'daily_end_time > daily_start_time',
            "transportation IN ('walking', 'private_car', 'public_transport')",
            "timezone = 'Asia/Manila'", 'schedule_revision > 0 AND fingerprint_version = 1',
            "schedule_fingerprint IS NULL OR schedule_fingerprint COLLATE \"C\" ~ '^[0-9a-f]{64}$'",
        ):
            self.assertIn(clause, table)
        self.assertNotRegex(table, r'\b(user_id|name|description|visit_date)\b')
        self.assertNotIn("TIME '24:00'", table)

    def test_stop_plan_membership_integrity_time_pairs_and_no_second_order(self):
        table = self.table('trip_stop_plans')
        for clause in (
            'PRIMARY KEY (trip_id, place_id)',
            'FOREIGN KEY (trip_id, place_id) REFERENCES public.trip_places(trip_id, place_id) ON DELETE CASCADE',
            'scheduled_date date,', "source text NOT NULL DEFAULT 'manual'",
            'keep_place boolean NOT NULL DEFAULT true', "source IN ('manual', 'recommended')",
            '(planned_start_time IS NULL) = (planned_end_time IS NULL)',
            'planned_start_time IS NULL OR (scheduled_date IS NOT NULL',
            'planned_end_time > planned_start_time',
        ):
            self.assertIn(clause, table)
        self.assertNotRegex(table, r'\b(position|order|ordinal|sequence|rank|cost|weather|distance|score|explanation)\b')
        self.assertNotIn('REFERENCES public.trip_itinerary', table)
        self.assertNotIn("TIME '24:00'", table)

    def test_helpers_are_invoker_only_and_identity_is_guarded(self):
        self.assertEqual(set(self.functions), {'rosago_itinerary_interests_valid', 'rosago_itinerary_guard_metadata'})
        for name, signature in (('rosago_itinerary_interests_valid', '(text[])'),
                                ('rosago_itinerary_guard_metadata', '()')):
            body = compact(self.functions[name])
            self.assertIn("SECURITY INVOKER SET search_path = ''", body)
            self.assertIn(f'REVOKE ALL PRIVILEGES ON FUNCTION public.{name}{signature} '
                          'FROM PUBLIC, anon, authenticated, service_role', self.statements)
        for column in ('id', 'user_id', 'created_at', 'trip_id', 'place_id'):
            self.assertIn(f'NEW.{column} IS DISTINCT FROM OLD.{column}', self.flat)
        self.assertIn('NEW.updated_at := pg_catalog.now()', self.flat)
        for name in self.tables:
            self.assertIn(f'CREATE TRIGGER {name}_metadata BEFORE INSERT OR UPDATE ON public.{name} '
                          'FOR EACH ROW EXECUTE FUNCTION public.rosago_itinerary_guard_metadata()', self.statements)
        for message in re.findall(r'RAISE EXCEPTION(.*?);', self.sql, re.S):
            self.assertRegex(compact(message), r"^USING ERRCODE = '22023', MESSAGE = '[A-Za-z .]+'$")

    def test_notes_defer_save_and_describe_validation_and_freshness_limits(self):
        for phrase in ('unapplied local draft', 'Atomic Save: deferred',
                       'no usable draft-write/Save API yet', 'not a completed JSON schema',
                       'do not parse/execute PostgreSQL or prove live Supabase RLS',
                       'all** memberships', 'READ COMMITTED', 'already saved; trip deleted',
                       'NULL means unvalidated/needs review', 'parent trip **before**',
                       'Existing authenticated trip deletes/remove/reorder'):
            self.assertIn(phrase, self.notes)
        self.assertNotIn('CREATE FUNCTION public.rosago_itinerary_save', self.sql)


if __name__ == '__main__':
    unittest.main()
