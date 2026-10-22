"""Static places SQL contract checks; no SQL execution or database connection.

These checks intentionally pin security-sensitive clauses. They do not emulate
PostgreSQL or prove live constraints, privileges, or RLS enforcement.
"""
from pathlib import Path
import re
import socket
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def compact(value):
    return ' '.join(value.split())


def sql_text(path):
    # These drafts use full-line comments only. Do not let comments satisfy tests.
    return '\n'.join(line for line in path.read_text(encoding='utf-8').splitlines()
                     if not line.lstrip().startswith('--'))


class PlacesMigrationTests(unittest.TestCase):
    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname',
                      'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        self.forward = sql_text(ROOT / 'migrations/0002_places.sql')
        self.rollback = sql_text(ROOT / 'migrations/rollback/0002_places.sql')
        tables = re.findall(r'CREATE TABLE public\.places \((.*?)\);', self.forward, re.S)
        self.assertEqual(len(tables), 1)
        self.table = compact(tables[0])
        self.constraints = dict(re.findall(
            r'CONSTRAINT (\w+) (.*?)(?=, CONSTRAINT |$)', self.table))
        self.flat = compact(self.forward)
        # Hide only the function body when splitting top-level SQL statements.
        self.statements = [compact(s) for s in re.sub(r'\$\$.*?\$\$', '$$BODY$$',
                           self.forward, flags=re.S).split(';') if s.strip()]

    def test_exact_columns_types_nullability_and_defaults(self):
        declarations = self.table.split('CONSTRAINT', 1)[0].rstrip(', ')
        columns = [compact(value) for value in declarations.split(',')]
        self.assertEqual(columns, [
            'id uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()',
            'name text NOT NULL', 'slug text NOT NULL', 'description text NOT NULL',
            'category text NOT NULL', 'address text NOT NULL',
            'latitude double precision', 'longitude double precision', 'image_url text',
            "status text NOT NULL DEFAULT 'draft'",
            'created_at timestamptz NOT NULL DEFAULT now()',
            'updated_at timestamptz NOT NULL DEFAULT now()',
        ])

    def test_all_constraints_present_without_unexpected_constraints(self):
        self.assertEqual(set(self.constraints), {
            'places_slug_unique', 'places_name_check', 'places_slug_check',
            'places_description_check', 'places_address_check', 'places_category_check',
            'places_latitude_check', 'places_longitude_check', 'places_coordinate_pair_check',
            'places_published_coordinates_check', 'places_image_url_check', 'places_status_check',
        })
        self.assertEqual(len(re.findall(r'\bCONSTRAINT\b', self.table)), 12)

    def test_text_lengths_and_rejection_instead_of_normalization(self):
        for column, maximum in (('name', 150), ('description', 3000), ('address', 500)):
            self.assertEqual(self.constraints[f'places_{column}_check'],
                f"CHECK ( char_length({column}) BETWEEN 1 AND {maximum} "
                f"AND {column} = regexp_replace({column}, '^[[:space:]]+|[[:space:]]+$', '', 'g'))")

    def test_slug_ascii_format_length_and_global_uniqueness(self):
        self.assertEqual(self.constraints['places_slug_unique'], 'UNIQUE (slug)')
        self.assertEqual(self.constraints['places_slug_check'],
            'CHECK ( char_length(slug) BETWEEN 1 AND 120 '
            'AND slug COLLATE "C" ~ \'^[a-z0-9]+(-[a-z0-9]+)*$\')')
        self.assertEqual(len(re.findall(r'\bUNIQUE\b', self.flat)), 1)
        self.assertEqual(len(re.findall(r'\bPRIMARY KEY\b', self.flat)), 1)
        self.assertNotRegex(self.flat, r'(?i)\bCREATE\s+(?:UNIQUE\s+)?INDEX\b')

    def test_category_and_status_exact_allowlists(self):
        self.assertEqual(self.constraints['places_category_check'],
            "CHECK ( category IN ('attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage'))")
        self.assertEqual(self.constraints['places_status_check'],
            "CHECK ( status IN ('draft', 'published', 'archived'))")

    def test_coordinates_ranges_finiteness_pair_and_publication(self):
        for column, maximum in (('latitude', 90), ('longitude', 180)):
            self.assertEqual(self.constraints[f'places_{column}_check'],
                f'CHECK ( {column} IS NULL OR ({column} BETWEEN -{maximum} AND {maximum} '
                f"AND {column} NOT IN ('NaN'::double precision, 'Infinity'::double precision, '-Infinity'::double precision)))")
        self.assertEqual(self.constraints['places_coordinate_pair_check'],
                         'CHECK ( (latitude IS NULL) = (longitude IS NULL))')
        self.assertEqual(self.constraints['places_published_coordinates_check'],
                         "CHECK ( status <> 'published' OR (latitude IS NOT NULL AND longitude IS NOT NULL))")

    def test_optional_image_baseline(self):
        self.assertEqual(self.constraints['places_image_url_check'],
            "CHECK ( image_url IS NULL OR (char_length(image_url) BETWEEN 9 AND 2048 "
            "AND image_url = regexp_replace(image_url, '^[[:space:]]+|[[:space:]]+$', '', 'g') "
            "AND image_url LIKE 'https://%'))")

    def test_timestamp_function_is_minimal_unprivileged_and_triggered(self):
        functions = re.findall(r'CREATE FUNCTION .*?\$\$;', self.forward, re.S)
        self.assertEqual(len(functions), 1)
        self.assertEqual(compact(functions[0]),
            "CREATE FUNCTION public.rosago_places_set_updated_at() RETURNS trigger "
            "LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$ "
            'BEGIN NEW.updated_at := pg_catalog.now(); RETURN NEW; END; $$;')
        triggers = [s for s in self.statements if s.startswith('CREATE TRIGGER')]
        self.assertEqual(triggers, [
            'CREATE TRIGGER rosago_places_updated_at BEFORE UPDATE ON public.places '
            'FOR EACH ROW EXECUTE FUNCTION public.rosago_places_set_updated_at()'])
        self.assertNotIn('SECURITY DEFINER', self.flat)

    def test_rls_enabled_and_only_published_select_policy(self):
        self.assertIn('ALTER TABLE public.places ENABLE ROW LEVEL SECURITY', self.statements)
        policies = [s for s in self.statements if s.startswith('CREATE POLICY')]
        self.assertEqual(policies, [
            "CREATE POLICY places_select_published ON public.places FOR SELECT TO anon, authenticated USING (status = 'published')"])

    def test_grants_are_select_only_and_function_privileges_revoked(self):
        grants = [s for s in self.statements if s.startswith(('GRANT ', 'REVOKE '))]
        self.assertEqual(grants, [
            'REVOKE ALL PRIVILEGES ON TABLE public.places FROM PUBLIC, anon, authenticated, service_role',
            'GRANT SELECT ON TABLE public.places TO anon, authenticated',
            'REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_places_set_updated_at() FROM PUBLIC, anon, authenticated, service_role',
        ])

    def test_transaction_and_exact_object_scope_no_data_or_extensions(self):
        self.assertEqual(self.statements[0], 'BEGIN')
        self.assertEqual(self.statements[-1], 'COMMIT')
        self.assertEqual(len(self.statements), 10)
        prefixes = [s.split(' ', 2)[:2] for s in self.statements[1:-1]]
        self.assertEqual(prefixes, [
            ['CREATE', 'TABLE'], ['ALTER', 'TABLE'], ['REVOKE', 'ALL'], ['GRANT', 'SELECT'],
            ['CREATE', 'POLICY'], ['CREATE', 'FUNCTION'], ['REVOKE', 'ALL'], ['CREATE', 'TRIGGER']])
        self.assertNotRegex(self.flat, r'(?i)\b(INSERT|DELETE|TRUNCATE|MERGE|COPY|DO|CALL)\b')
        self.assertNotRegex(self.flat, r'(?i)\bUPDATE\s+public\.')
        self.assertNotRegex(self.flat, r'(?i)\b(profiles|auth|postgis|EXTENSION|CASCADE)\b')
        self.assertNotRegex(self.flat, r'(?i)IF NOT EXISTS|CREATE OR REPLACE|DISABLE ROW LEVEL SECURITY')

    def test_rollback_exact_scope_order_and_atomicity(self):
        statements = [compact(s) for s in self.rollback.split(';') if s.strip()]
        self.assertEqual(statements, [
            'BEGIN',
            'DROP TRIGGER rosago_places_updated_at ON public.places',
            'DROP FUNCTION public.rosago_places_set_updated_at()',
            'DROP POLICY places_select_published ON public.places',
            'DROP TABLE public.places', 'COMMIT',
        ])
        self.assertNotRegex(self.rollback, r'(?i)\b(CASCADE|profiles|auth)\b|IF EXISTS')


if __name__ == '__main__':
    unittest.main()
