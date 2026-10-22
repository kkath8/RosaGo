"""Offline SQL contract checks, not PostgreSQL execution or proof of live RLS.

Security clauses are checked outside comments; SQL bodies remain unexecuted.
Real-role, concurrency, trigger/cascade and constraint semantics need the
separately authorized database verification described in migrations/README.md.
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
    return '\n'.join(line for line in path.read_text(encoding='utf-8').splitlines()
                     if not line.lstrip().startswith('--'))


class TripsMigrationTests(unittest.TestCase):
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
        self.forward = sql_text(ROOT / 'migrations/0003_trips.sql')
        self.rollback = sql_text(ROOT / 'migrations/rollback/0003_trips.sql')
        self.readme = (ROOT / 'migrations/README.md').read_text(encoding='utf-8')
        self.tables = dict(re.findall(r'CREATE TABLE public\.(\w+) \((.*?)\);',
                                     self.forward, re.S))
        self.functions = dict(re.findall(r'CREATE FUNCTION public\.(\w+)(\(.*?\$\$;)',
                                        self.forward, re.S))
        self.statements = [compact(s) for s in re.sub(r'\$\$.*?\$\$', '$$BODY$$',
                           self.forward, flags=re.S).split(';') if s.strip()]
        self.policies = {s.split()[2]: s for s in self.statements if s.startswith('CREATE POLICY ')}

    def columns(self, table):
        declarations = self.tables[table].split('CONSTRAINT', 1)[0].rstrip(', \n')
        return [compact(value) for value in declarations.split(',')]

    def body(self, function):
        return compact(self.functions[function].split('$$')[1])

    def test_trips_exact_columns_defaults_and_auth_fk(self):
        self.assertEqual(set(self.tables), {'trips', 'trip_places'})
        self.assertEqual(self.columns('trips'), [
            'id uuid NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()',
            'user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE',
            'name text NOT NULL', 'visit_date date',
            'created_at timestamptz NOT NULL DEFAULT now()',
            'updated_at timestamptz NOT NULL DEFAULT now()',
        ])

    def test_trip_name_and_python_date_range(self):
        constraints = compact(self.tables['trips']).split('CONSTRAINT ', 1)[1]
        self.assertEqual(constraints,
            'trips_name_check CHECK ( char_length(name) BETWEEN 1 AND 100 '
            "AND name = regexp_replace(name, '^[[:space:]]+|[[:space:]]+$', '', 'g')), "
            'CONSTRAINT trips_visit_date_check CHECK ( visit_date IS NULL OR '
            "visit_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31')")
        self.assertNotIn('CURRENT_DATE', self.forward)

    def test_membership_exact_columns_fks_and_constraints(self):
        self.assertEqual(self.columns('trip_places'), [
            'trip_id uuid NOT NULL REFERENCES public.trips(id) ON DELETE CASCADE',
            'place_id uuid NOT NULL REFERENCES public.places(id) ON DELETE RESTRICT',
            'position integer NOT NULL', 'created_at timestamptz NOT NULL DEFAULT now()',
        ])
        constraints = compact(self.tables['trip_places']).split('CONSTRAINT ', 1)[1]
        self.assertEqual(constraints,
            'trip_places_pkey PRIMARY KEY (trip_id, place_id), '
            'CONSTRAINT trip_places_position_check CHECK (position >= 1), '
            'CONSTRAINT trip_places_trip_position_unique UNIQUE (trip_id, position) '
            'DEFERRABLE INITIALLY IMMEDIATE')

    def test_exact_listing_and_fk_indexes(self):
        self.assertEqual([s for s in self.statements if s.startswith('CREATE INDEX')], [
            'CREATE INDEX trips_owner_listing_idx ON public.trips (user_id, created_at, id)',
            'CREATE INDEX trip_places_place_id_idx ON public.trip_places (place_id)',
        ])

    def test_rls_enabled_and_exact_own_trip_policies(self):
        self.assertEqual([s for s in self.statements if s.startswith('ALTER TABLE')], [
            'ALTER TABLE public.trips ENABLE ROW LEVEL SECURITY',
            'ALTER TABLE public.trip_places ENABLE ROW LEVEL SECURITY',
        ])
        self.assertEqual(len(self.policies), 8)
        for operation in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
            name = f'trips_{operation.lower()}_own'
            condition = 'user_id = (SELECT auth.uid())'
            clause = (f'WITH CHECK ({condition})' if operation == 'INSERT' else
                      f'USING ({condition})')
            if operation == 'UPDATE':
                clause += f' WITH CHECK ({condition})'
            self.assertEqual(self.policies[name],
                f'CREATE POLICY {name} ON public.trips FOR {operation} TO authenticated {clause}')

    def test_membership_ownership_and_publication_only_on_insert(self):
        own = ('EXISTS ( SELECT 1 FROM public.trips AS trip WHERE '
               'trip.id = trip_places.trip_id AND trip.user_id = (SELECT auth.uid()) )')
        for operation in ('SELECT', 'UPDATE', 'DELETE'):
            name = f'trip_places_{operation.lower()}_own'
            expected = (f'CREATE POLICY {name} ON public.trip_places FOR {operation} '
                        f'TO authenticated USING ({own})')
            if operation == 'UPDATE':
                expected += f' WITH CHECK ({own})'
            self.assertEqual(self.policies[name], expected)
            self.assertNotIn('public.places', self.policies[name])
            self.assertNotIn('published', self.policies[name])
        self.assertEqual(self.policies['trip_places_insert_own_published'],
            'CREATE POLICY trip_places_insert_own_published ON public.trip_places '
            f'FOR INSERT TO authenticated WITH CHECK ( {own} AND EXISTS ( '
            "SELECT 1 FROM public.places AS place WHERE place.id = trip_places.place_id "
            "AND place.status = 'published' ) )")
        for policy in self.policies.values():
            self.assertNotRegex(policy, r'\b(anon|PUBLIC|service_role)\b')

    def test_exact_acl_no_writable_generated_columns_or_membership_identity(self):
        acl = [s for s in self.statements if s.startswith(('GRANT ', 'REVOKE '))]
        self.assertEqual(acl, [
            'REVOKE ALL PRIVILEGES ON TABLE public.trips, public.trip_places '
            'FROM PUBLIC, anon, authenticated, service_role',
            'GRANT SELECT, DELETE ON TABLE public.trips TO authenticated',
            'GRANT INSERT (name, visit_date) ON TABLE public.trips TO authenticated',
            'GRANT UPDATE (name, visit_date) ON TABLE public.trips TO authenticated',
            'GRANT SELECT, DELETE ON TABLE public.trip_places TO authenticated',
            'GRANT INSERT (trip_id, place_id, position) ON TABLE public.trip_places TO authenticated',
            'GRANT UPDATE (position) ON TABLE public.trip_places TO authenticated',
            'REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_trips_set_updated_at() '
            'FROM PUBLIC, anon, authenticated, service_role',
            'REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_trip_places_lock_parent() '
            'FROM PUBLIC, anon, authenticated, service_role',
            'REVOKE ALL PRIVILEGES ON FUNCTION public.rosago_trip_add_place(uuid, uuid), '
            'public.rosago_trip_remove_place(uuid, uuid), public.rosago_trip_reorder_places(uuid, uuid[]) '
            'FROM PUBLIC, anon, authenticated, service_role',
            'GRANT EXECUTE ON FUNCTION public.rosago_trip_add_place(uuid, uuid), '
            'public.rosago_trip_remove_place(uuid, uuid), public.rosago_trip_reorder_places(uuid, uuid[]) '
            'TO authenticated',
        ])

    def test_function_signatures_security_mode_and_fixed_search_path(self):
        signatures = {
            'rosago_trips_set_updated_at': '() RETURNS trigger',
            'rosago_trip_places_lock_parent': '() RETURNS trigger',
            'rosago_trip_add_place': '(p_trip_id uuid, p_place_id uuid) RETURNS void',
            'rosago_trip_remove_place': '(p_trip_id uuid, p_place_id uuid) RETURNS void',
            'rosago_trip_reorder_places': '(p_trip_id uuid, p_place_ids uuid[]) RETURNS void',
        }
        self.assertEqual(set(self.functions), set(signatures))
        for name, signature in signatures.items():
            self.assertEqual(compact(self.functions[name].split('$$')[0]),
                signature + " LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS")
        self.assertNotRegex(self.forward, r'(?i)SECURITY DEFINER|SET ROLE|SET SESSION|row_security|EXECUTE\s+[\'\"]')

    def test_metadata_only_timestamp_and_exact_triggers(self):
        self.assertEqual(self.body('rosago_trips_set_updated_at'),
            'BEGIN NEW.updated_at := pg_catalog.now(); RETURN NEW; END;')
        self.assertEqual([s for s in self.statements if s.startswith('CREATE TRIGGER')], [
            'CREATE TRIGGER rosago_trips_updated_at BEFORE UPDATE ON public.trips '
            'FOR EACH ROW EXECUTE FUNCTION public.rosago_trips_set_updated_at()',
            'CREATE TRIGGER rosago_trip_places_parent_lock BEFORE INSERT OR UPDATE OR DELETE '
            'ON public.trip_places FOR EACH ROW EXECUTE FUNCTION public.rosago_trip_places_lock_parent()',
        ])
        for name in self.functions:
            if name != 'rosago_trips_set_updated_at':
                self.assertNotIn('updated_at', self.body(name))

    def test_direct_write_lock_immutable_keys_and_cascade_exception(self):
        body = self.body('rosago_trip_places_lock_parent')
        self.assertIn("IF TG_OP = 'UPDATE' THEN IF NEW.trip_id IS DISTINCT FROM OLD.trip_id "
                      'OR NEW.place_id IS DISTINCT FROM OLD.place_id THEN', body)
        self.assertIn("IF TG_OP = 'DELETE' THEN target_trip_id := OLD.trip_id; "
                      'ELSE target_trip_id := NEW.trip_id; END IF;', body)
        lock = ('PERFORM trip.id FROM public.trips AS trip '
                'WHERE trip.id = target_trip_id FOR UPDATE;')
        self.assertIn(lock, body)
        self.assertIn("IF NOT FOUND AND TG_OP <> 'DELETE' THEN", body)
        self.assertIn("IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW;", body)
        self.assertLess(body.index(lock), body.index('RETURN OLD'))
        self.assertNotIn('published', body)
        self.assertNotIn('pg_trigger_depth', body)

    def test_all_rpcs_lock_owned_parent_before_membership_access(self):
        for name in ('rosago_trip_add_place', 'rosago_trip_remove_place', 'rosago_trip_reorder_places'):
            body = self.body(name)
            lock = ('PERFORM trip.id FROM public.trips AS trip WHERE trip.id = p_trip_id '
                    'AND trip.user_id = (SELECT auth.uid()) FOR UPDATE;')
            self.assertIn(lock, body)
            self.assertLess(body.index(lock), body.index('public.trip_places'))
            self.assertIn("IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE = 'P0002', "
                          "MESSAGE = 'Trip not found.'; END IF;", body)
            self.assertNotRegex(body, r'\b(COMMIT|ROLLBACK|EXCEPTION WHEN)\b')

    def test_rpcs_require_fresh_snapshots_after_parent_lock_waits(self):
        for name in ('rosago_trip_add_place', 'rosago_trip_remove_place', 'rosago_trip_reorder_places'):
            body = self.body(name)
            self.assertTrue(body.startswith(
                ('DECLARE last_position integer; ' if name == 'rosago_trip_add_place' else '') +
                "BEGIN IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN "
                "RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'Unsupported transaction isolation.'; "
                'END IF; PERFORM trip.id'))

    def test_add_published_duplicate_check_append_and_overflow(self):
        body = self.body('rosago_trip_add_place')
        publication = "WHERE place.id = p_place_id AND place.status = 'published'"
        mutation = 'INSERT INTO public.trip_places (trip_id, place_id, position)'
        self.assertIn(publication, body)
        self.assertIn('membership.trip_id = p_trip_id AND membership.place_id = p_place_id', body)
        self.assertIn('SELECT COALESCE(pg_catalog.max(membership.position), 0) INTO last_position '
                      'FROM public.trip_places AS membership WHERE membership.trip_id = p_trip_id;', body)
        self.assertIn('IF last_position = 2147483647 THEN', body)
        self.assertIn('VALUES (p_trip_id, p_place_id, last_position + 1);', body)
        self.assertLess(body.index(publication), body.index(mutation))

    def test_remove_is_own_membership_only_and_allows_unavailable_places(self):
        body = self.body('rosago_trip_remove_place')
        self.assertIn('IF p_place_id IS NULL THEN', body)
        self.assertIn('DELETE FROM public.trip_places AS membership WHERE '
                      'membership.trip_id = p_trip_id AND membership.place_id = p_place_id;', body)
        self.assertNotIn('public.places', body)
        self.assertNotIn('published', body)

    def test_reorder_requires_exact_nonnull_duplicate_free_permutation(self):
        body = self.body('rosago_trip_reorder_places')
        self.assertIn('IF p_place_ids IS NULL OR '
                      'COALESCE(pg_catalog.array_ndims(p_place_ids), 1) <> 1', body)
        self.assertIn('pg_catalog.cardinality(p_place_ids) <> ( SELECT '
                      'pg_catalog.count(DISTINCT item.place_id) FROM '
                      'pg_catalog.unnest(p_place_ids) AS item(place_id) )', body)
        self.assertIn('pg_catalog.cardinality(p_place_ids) <> ( SELECT pg_catalog.count(*) '
                      'FROM public.trip_places AS membership WHERE membership.trip_id = p_trip_id )', body)
        self.assertIn('OR EXISTS ( SELECT 1 FROM pg_catalog.unnest(p_place_ids) AS item(place_id) '
                      'WHERE NOT EXISTS ( SELECT 1 FROM public.trip_places AS membership WHERE '
                      'membership.trip_id = p_trip_id AND membership.place_id = item.place_id ) )', body)
        self.assertLess(body.index("MESSAGE = 'Invalid trip order.'"), body.index('UPDATE public.'))
        self.assertNotIn('public.places', body)

    def test_reorder_defers_only_position_constraint_then_validates(self):
        body = self.body('rosago_trip_reorder_places')
        self.assertTrue(body.endswith(
            'SET CONSTRAINTS public.trip_places_trip_position_unique DEFERRED; '
            'UPDATE public.trip_places AS membership SET position = item.ordinality::integer '
            'FROM pg_catalog.unnest(p_place_ids) WITH ORDINALITY AS item(place_id, ordinality) '
            'WHERE membership.trip_id = p_trip_id AND membership.place_id = item.place_id; '
            'SET CONSTRAINTS public.trip_places_trip_position_unique IMMEDIATE; END;'))
        self.assertNotIn('SET CONSTRAINTS ALL', body)

    def test_transaction_object_scope_no_execution_seeds_or_existing_schema_changes(self):
        self.assertEqual(self.statements[0], 'BEGIN')
        self.assertEqual(self.statements[-1], 'COMMIT')
        self.assertEqual(self.forward.count('$$'), 10)
        for statement in self.statements[1:-1]:
            self.assertRegex(statement, r'^(CREATE (TABLE|INDEX|POLICY|FUNCTION|TRIGGER)|ALTER TABLE|REVOKE ALL|GRANT )')
        # IF NOT EXISTS is valid PL/pgSQL publication validation; prohibit it
        # only in top-level DDL, where it could silently reuse an existing object.
        self.assertNotRegex(' '.join(self.statements), r'(?i)IF NOT EXISTS|CREATE OR REPLACE')
        self.assertNotRegex(self.forward, r'(?i)DISABLE ROW LEVEL SECURITY|TRUNCATE|CREATE EXTENSION')
        self.assertNotRegex(self.forward, r'(?i)(?:UPDATE|INSERT INTO|DELETE FROM|ALTER TABLE|DROP TABLE)\s+(?:public\.(?:places|profiles)|auth\.)')
        self.assertNotRegex(self.forward, r'(?i)\b(access_token|refresh_token|service_key|http|dblink)\b')
        self.assertNotIn('profiles', self.forward)

    def test_fixed_rpc_errors_do_not_interpolate_values(self):
        raises = re.findall(r'RAISE EXCEPTION(.*?);', self.forward, re.S)
        self.assertEqual(len(raises), 13)
        for statement in raises:
            self.assertRegex(compact(statement), r"^USING ERRCODE = '(P0002|22023)', MESSAGE = '[A-Za-z .]+'$")
        self.assertNotIn('SQLERRM', self.forward)

    def test_rollback_exact_scope_order_and_no_cascade(self):
        statements = [compact(s) for s in self.rollback.split(';') if s.strip()]
        self.assertEqual(statements, [
            'BEGIN',
            'DROP FUNCTION public.rosago_trip_reorder_places(uuid, uuid[])',
            'DROP FUNCTION public.rosago_trip_remove_place(uuid, uuid)',
            'DROP FUNCTION public.rosago_trip_add_place(uuid, uuid)',
            'DROP TRIGGER rosago_trip_places_parent_lock ON public.trip_places',
            'DROP FUNCTION public.rosago_trip_places_lock_parent()',
            'DROP TRIGGER rosago_trips_updated_at ON public.trips',
            'DROP FUNCTION public.rosago_trips_set_updated_at()',
            'DROP POLICY trip_places_delete_own ON public.trip_places',
            'DROP POLICY trip_places_update_own ON public.trip_places',
            'DROP POLICY trip_places_insert_own_published ON public.trip_places',
            'DROP POLICY trip_places_select_own ON public.trip_places',
            'DROP POLICY trips_delete_own ON public.trips',
            'DROP POLICY trips_update_own ON public.trips',
            'DROP POLICY trips_insert_own ON public.trips',
            'DROP POLICY trips_select_own ON public.trips',
            'DROP TABLE public.trip_places', 'DROP TABLE public.trips', 'COMMIT',
        ])
        self.assertNotRegex(self.rollback, r'(?i)\b(CASCADE|places|profiles|auth)\b|IF EXISTS')

    def test_readme_records_status_order_and_runtime_verification_limits(self):
        self.assertIn('0002 has been applied and post-execution verified in the current development database.', self.readme)
        self.assertNotIn('It has NOT been\nexecuted against Supabase', self.readme)
        self.assertIn('`0003_trips.sql` is unexecuted.', self.readme)
        self.assertIn('`0001_profiles.sql` -> `0002_places.sql` -> `0003_trips.sql`', self.readme)
        for phrase in ('Do not rerun 0002', 'Apply manually once', 'post-execution verification',
                       '`rollback/0003_trips.sql`', 'deadlock', 'cascade',
                       'earlier SELECT', 'No elevated function', 'two users, anon, missing subject',
                       'static tests do not establish SQL runtime validity'):
            self.assertIn(phrase, self.readme)


if __name__ == '__main__':
    unittest.main()
