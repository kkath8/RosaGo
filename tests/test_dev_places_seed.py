"""Static data/SQL contracts only: never connect to a database or execute SQL."""
from collections import Counter
import json
import math
from pathlib import Path
import re
import socket
import subprocess
import unittest
from unittest.mock import patch
from uuid import UUID

from places_service import CATEGORIES, PROJECTION, parse_place_row


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/dev/places_v1'
DISCLOSURE = ('DEVELOPMENT TEST DATA ONLY. Synthetic place; not a real attraction or business. '
              'Not verified or endorsed by the Santa Rosa City Tourism Office.')
IDENTITIES = [
    ('Attraction 01', 'attraction-01', 'attraction', 'published'),
    ('Attraction 02', 'attraction-02', 'attraction', 'published'),
    ('Dining Spot 01', 'dining-01', 'dining', 'published'),
    ('Dining Spot 02', 'dining-02', 'dining', 'published'),
    ('Shopping Spot 01', 'shopping-01', 'shopping', 'published'),
    ('Accommodation 01', 'accommodation-01', 'accommodation', 'published'),
    ('Nature Spot 01', 'nature-01', 'nature', 'published'),
    ('Nature Spot 02', 'nature-02', 'nature', 'published'),
    ('Heritage Site 01', 'heritage-01', 'heritage', 'published'),
    ('Heritage Site 02', 'heritage-02', 'heritage', 'published'),
    ('Draft Attraction 01', 'draft-attraction-01', 'attraction', 'draft'),
    ('Archived Heritage Site 01', 'archived-heritage-01', 'heritage', 'archived'),
]


class DevelopmentPlacesSeedTests(unittest.TestCase):
    def setUp(self):
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Network forbidden.'))
                mocked = guard.start()
                self.addCleanup(guard.stop)
                self.addCleanup(mocked.assert_not_called)
        self.sql = {name: (DIRECTORY / name).read_text(encoding='utf-8')
                    for name in ('seed.sql', 'cleanup.sql')}
        self.rows = {}
        self.code = {}
        for name, source in self.sql.items():
            manifests = re.findall(r'\$manifest\$(.*?)\$manifest\$::jsonb', source, re.S)
            self.assertEqual(len(manifests), 1)
            self.rows[name] = json.loads(manifests[0])
            # Remove data/comments so forbidden-operation checks inspect SQL code.
            code = source.replace(manifests[0], '')
            self.code[name] = re.sub(r'--[^\n]*', '', code)
        self.seed = self.rows['seed.sql']

    def test_exact_fixed_identities_and_shared_manifest(self):
        self.assertEqual(len(self.seed), 12)
        self.assertEqual(self.seed, self.rows['cleanup.sql'])
        self.assertEqual(len({r['id'] for r in self.seed}), 12)
        self.assertEqual(len({r['slug'] for r in self.seed}), 12)
        for index, (row, identity) in enumerate(zip(self.seed, IDENTITIES), 1):
            name, slug, category, status = identity
            self.assertEqual(row['id'], f'9f56c6a0-5c4d-4e82-9b31-{index:012d}')
            self.assertEqual(str(UUID(row['id'])), row['id'])
            self.assertEqual(row['name'], 'RosaGO Test ' + name)
            self.assertEqual(row['slug'], 'rosago-test-v1-' + slug)
            self.assertEqual((row['category'], row['status']), (category, status))
            self.assertRegex(row['slug'], r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

    def test_exact_status_and_category_distribution(self):
        self.assertEqual(Counter(r['status'] for r in self.seed), {'published': 10, 'draft': 1, 'archived': 1})
        published = [r for r in self.seed if r['status'] == 'published']
        self.assertEqual(Counter(r['category'] for r in published),
                         {'attraction': 2, 'dining': 2, 'shopping': 1, 'accommodation': 1, 'nature': 2, 'heritage': 2})
        self.assertEqual({r['category'] for r in published}, CATEGORIES)
        self.assertEqual(Counter(r['category'] for r in self.seed),
                         {'attraction': 3, 'dining': 2, 'shopping': 1, 'accommodation': 1, 'nature': 2, 'heritage': 3})

    def test_fields_disclosures_lengths_and_null_images(self):
        expected = set(PROJECTION.split(',')) - {'created_at', 'updated_at'} | {'status'}
        for row in self.seed:
            self.assertEqual(set(row), expected)
            for key, maximum in [('name', 150), ('slug', 120), ('description', 3000), ('address', 500)]:
                self.assertIs(type(row[key]), str)
                self.assertEqual(row[key], row[key].strip())
                self.assertTrue(1 <= len(row[key]) <= maximum)
            self.assertTrue(row['description'].startswith(DISCLOSURE))
            self.assertTrue(row['address'].startswith('Synthetic map point '))
            self.assertIn('UI testing only; not a real visitor address.', row['address'])
            self.assertIsNone(row['image_url'])

    def test_coordinates_are_complete_finite_and_deterministic(self):
        self.assertEqual(len({(r['latitude'], r['longitude']) for r in self.seed}), 12)
        for index, row in enumerate(self.seed):
            for key, bound in [('latitude', 90), ('longitude', 180)]:
                self.assertIn(type(row[key]), (int, float))
                self.assertTrue(math.isfinite(row[key]))
                self.assertTrue(-bound <= row[key] <= bound)
            self.assertAlmostEqual(row['latitude'], 14.28 + (index // 4 - 1) * .002)
            self.assertAlmostEqual(row['longitude'], 121.09 + (index % 4 - 1.5) * .002)

    def test_published_rows_pass_actual_place_validator(self):
        for row in self.seed:
            if row['status'] == 'published':
                parsed = parse_place_row(row | {'created_at': '2026-01-01T00:00:00Z',
                                               'updated_at': '2026-01-01T00:00:00Z'})
                self.assertEqual(parsed.id, row['id'])
                self.assertIsNotNone(parsed.created_at.utcoffset())

    def test_manual_acknowledgement_transactions_and_locking(self):
        for source in self.sql.values():
            self.assertIn('DEVELOPMENT ONLY / NEVER PRODUCTION', source)
            self.assertIn("operator_acknowledgement constant text := '';", source)
        for code in self.code.values():
            self.assertTrue(code.strip().startswith('BEGIN;'))
            self.assertTrue(code.strip().endswith('COMMIT;'))
            self.assertEqual(len(re.findall(r'\bCOMMIT\b', code)), 1)
            self.assertIn("SET LOCAL lock_timeout = '5s';", code)
            self.assertIn("SET LOCAL statement_timeout = '30s';", code)
            self.assertIn("IF operator_acknowledgement IS DISTINCT FROM 'I verified the connected Supabase project. I designated this entire project for RosaGO capstone development/testing only; it is not serving real production users/data. I understand these are synthetic test records and the Supabase main/PRODUCTION branch label does not make this safe automatically. I intentionally authorize this development-only operation.' THEN", code)
            self.assertIn("IF current_setting('transaction_isolation') <> 'read committed' THEN", code)
            self.assertIn('LOCK TABLE public.places IN SHARE ROW EXCLUSIVE MODE;', code)
            self.assertLess(code.index('IF operator_acknowledgement'), code.index('LOCK TABLE'))
            self.assertLess(code.index('LOCK TABLE'), code.index('IF EXISTS'))
            self.assertNotRegex(code, r'(?i)EXCEPTION\s+WHEN')

    def test_seed_guards_uuid_and_slug_and_only_inserts_missing(self):
        code = ' '.join(self.code['seed.sql'].split())
        self.assertIn("ON place.id = (manifest.item->>'id')::uuid OR place.slug = manifest.item->>'slug'", code)
        self.assertIn("WHERE (to_jsonb(place) - 'created_at' - 'updated_at') IS DISTINCT FROM manifest.item", code)
        self.assertIn("RAISE EXCEPTION 'Reserved test UUID or slug conflicts with existing content.';", code)
        self.assertLess(code.index('RAISE EXCEPTION \'Reserved'), code.index('INSERT INTO'))
        self.assertIn('INSERT INTO public.places (id, name, slug, description, category, address, latitude, longitude, image_url, status)', code)
        self.assertIn('WHERE NOT EXISTS (SELECT 1 FROM public.places AS place WHERE place.id = item.id);', code)
        self.assertEqual(len(re.findall(r'\bINSERT INTO\b', code)), 1)
        self.assertNotRegex(code, r'(?i)\bUPDATE\b|\bDELETE\b|ON CONFLICT')

    def test_cleanup_exact_uuid_predicate_content_and_reference_guards(self):
        code = ' '.join(self.code['cleanup.sql'].split())
        self.assertIn("JOIN public.places AS place ON place.id = (manifest.item->>'id')::uuid", code)
        self.assertIn("WHERE (to_jsonb(place) - 'created_at' - 'updated_at') IS DISTINCT FROM manifest.item", code)
        self.assertIn("RAISE EXCEPTION 'Test UUID has unexpected identity or content; cleanup refused.';", code)
        self.assertIn("FROM public.trip_places AS membership JOIN jsonb_array_elements(expected) AS manifest(item) ON membership.place_id = (manifest.item->>'id')::uuid", code)
        self.assertIn("RAISE EXCEPTION 'Test places are referenced by trips; cleanup refused.';", code)
        self.assertTrue(code.index('unexpected identity') < code.index('FROM public.trip_places') < code.index('DELETE FROM'))
        self.assertIn("DELETE FROM public.places AS place USING jsonb_array_elements(expected) AS manifest(item) WHERE place.id = (manifest.item->>'id')::uuid;", code)
        self.assertEqual(len(re.findall(r'\bDELETE FROM\b', code)), 1)
        self.assertNotRegex(code, r'(?i)\bINSERT\b|\bUPDATE\b|\bLIKE\b|\bILIKE\b|place\.(name|slug)')

    def test_no_schema_privilege_dynamic_sql_or_credentials(self):
        for code in self.code.values():
            self.assertNotRegex(code, r'(?i)\b(CREATE|ALTER|DROP|TRUNCATE|CASCADE|GRANT|REVOKE|EXECUTE|COPY)\b')
            self.assertNotRegex(code, r'(?i)\b(row_security|SET ROLE|SET SESSION AUTHORIZATION)\b')
        for source in self.sql.values():
            self.assertNotRegex(source, r'(?i)https?://|postgres(?:ql)?://|sb_secret_|sb_publishable_|eyJ[a-zA-Z0-9_-]+\.|password\s*=|service_role')

    def test_no_tracked_runtime_or_deployment_integration(self):
        # Read-only Git enumeration; does not import application code or run SQL.
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        suffixes = {'.py', '.js', '.json', '.yml', '.yaml', '.toml', '.sh', '.ps1', '.bat'}
        for name in tracked:
            path = Path(name)
            if not name or path.parts[0] in ('tests', 'data', 'migrations') or path.suffix not in suffixes:
                continue
            text = (ROOT / path).read_text(encoding='utf-8')
            self.assertNotRegex(text, r'places_v1|data[/\\]dev|seed\.sql|cleanup\.sql', name)

    def test_documentation_records_execution_limits(self):
        text = (DIRECTORY / 'README.md').read_text(encoding='utf-8')
        for phrase in ('RosaGO Development Places Dataset v1', 'NEVER PRODUCTION',
                       'not verified or endorsed', '10 publicly visible', '1 draft and 1 archived',
                       'manually', 'trip_places', '0002_places.sql', '0003_trips.sql',
                       'no automatic startup/test/deployment execution', 'Official POI',
                       'Static checks do not establish SQL', 'NOT been',
                       'Supabase Free', 'main', 'PRODUCTION', 'entire project',
                       'real production users/data', 'must no longer be executed',
                       'removed before replacing'):
            self.assertIn(phrase.lower(), ' '.join(text.split()).lower())


if __name__ == '__main__':
    unittest.main()
