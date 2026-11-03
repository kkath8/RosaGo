"""Read-only/offline checks of the proposed Tourism transition; never execute SQL."""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import unittest

from itinerary_selection_policy import select_destinations, POLICY_VERSION as SELECTION_POLICY_VERSION
from places_service import parse_place_row
from recommendation_engine import rank_candidates, POLICY_VERSION as RANKING_POLICY_VERSION
from tourism_catalog_transition import (CATEGORY_MAPPING, SOURCE, SOURCE_FIELDS, VALUE_FIELDS,
    hours_status, map_category, read_workbook, render_review_sql, validate_plan)
from test_recommendation_engine import preferences

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/santa_rosa_places'


class TourismTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads((FOLDER / 'tourism_transition_plan.json').read_text(encoding='utf-8'))
        cls.rows = cls.plan['rows']
        cls.sql = (FOLDER / 'tourism_transition_review.sql').read_text(encoding='utf-8')

    def test_twenty_rows_twelve_reused_eight_new_no_duplicates(self):
        validate_plan(self.plan)
        self.assertEqual(len(self.rows), 20)
        self.assertEqual(Counter(r['action'] for r in self.rows), {'UPDATE EXISTING': 12, 'INSERT NEW': 8})
        self.assertEqual({r['tourism_source_row'] for r in self.rows}, set(range(2, 22)))
        for field in ('id', 'slug', 'tourism_source_row'):
            self.assertEqual(len({r[field] for r in self.rows}), 20)
        self.assertEqual(Counter(r['tourism_type'] for r in self.rows), {'Local': 9, 'Common': 11})

    def test_all_source_fields_match_authoritative_workbook_exactly(self):
        workbook = Path.home() / 'Downloads' / self.plan['source_workbook']
        if not workbook.is_file():
            self.skipTest('Authoritative workbook not available on this machine.')
        self.assertEqual(hashlib.sha256(workbook.read_bytes()).hexdigest(), self.plan['source_sha256'])
        actual = read_workbook(workbook)
        selected = (*SOURCE_FIELDS, 'tourism_source', 'tourism_source_row')
        self.assertEqual([{k: r[k] for k in selected} for r in self.rows], actual)

    def test_exact_category_mapping_and_original_labels_are_independent(self):
        self.assertEqual(len(CATEGORY_MAPPING), 17)
        self.assertEqual(map_category('Public Park / Recreation'), 'nature')
        self.assertEqual(map_category('Nature / Outdoor Recreation'), 'nature')
        self.assertEqual(map_category('Farm / Family Recreation'), 'attraction')
        for r in self.rows:
            self.assertEqual(r['category'], map_category(r['tourism_category']))
            self.assertNotEqual(r['category'], r['tourism_category'])
        self.assertEqual(Counter(r['category'] for r in self.rows),
                         {'attraction': 2, 'nature': 3, 'shopping': 5, 'heritage': 4, 'dining': 6})
        for invalid in ('public park / recreation', 'Public Park / Recreation ', 'unknown', None, []):
            with self.assertRaises(ValueError):
                map_category(invalid)

    def test_hours_verify_starred_missing_midnight_and_no_verified_state(self):
        self.assertEqual(Counter(r['tourism_hours_status'] for r in self.rows),
                         {'unverified': 18, 'verify_required': 2})
        self.assertEqual(hours_status(None, None), 'not_supplied')
        self.assertEqual(hours_status('', None), 'not_supplied')
        self.assertEqual(hours_status('Verify', '8:00 PM*'), 'verify_required')
        self.assertEqual(hours_status('8:00 AM*', 'Verify'), 'verify_required')
        self.assertEqual(hours_status(None, '8:00 PM*'), 'unverified')
        self.assertEqual(hours_status('8:00 AM', '9:00 PM'), 'unverified')
        self.assertEqual(hours_status('verify', '9:00 PM'), 'unverified')  # exact source terminology
        for r in self.rows:
            self.assertNotEqual(r['tourism_hours_status'], 'verified')
            self.assertEqual(r['tourism_hours_status'], hours_status(r['tourism_opening_hours_raw'], r['tourism_closing_hours_raw']))
        stars = sum('*' in r[k] for r in self.rows for k in ('tourism_opening_hours_raw', 'tourism_closing_hours_raw'))
        self.assertEqual(stars, 36)
        self.assertEqual(next(r for r in self.rows if r['name'] == 'Yamazaki Kitchen Laguna')['tourism_closing_hours_raw'], '12:00 AM*')
        self.assertIn('exact location to verify', next(r for r in self.rows if r['name'] == 'Centennial Garden')['address'])

    def test_twelve_known_uuid_mappings_and_preservation(self):
        expected = {
            2: '7544a303-a669-41ad-9723-21b440c8e1ff', 3: '4751680c-faab-4043-9d5b-d55053e54415',
            4: '772aa257-089e-426b-9669-d4da7a6492c1', 5: 'a984ad59-ed4d-43b8-89c1-33852877cfe0',
            6: '277837ea-06bf-43ab-a509-c6d88cb44956', 7: '1f04e93e-6227-42fb-be7f-e19970476efb',
            8: '428a525e-259d-4a89-90f4-1c231c6d6eae', 9: 'b2b0dab7-f8b1-4c1a-8828-bcff6fa5db40',
            10: '2b258daf-2ede-4e12-8961-c36965d1f278', 11: '5591677c-107e-4960-b36a-fbd475965e4f',
            12: '20fb152e-b13b-422a-a21f-4c24dc487a0e', 14: '184cb1aa-fa72-42ba-a94d-07e097f33d83',
        }
        self.assertEqual({r['tourism_source_row']: r['id'] for r in self.rows if r['existing']}, expected)
        for r in self.rows:
            if r['existing']:
                for k in ('id', 'slug', 'latitude', 'longitude'):
                    self.assertEqual(r[k], r['existing'][k])
        nuvali = next(r for r in self.rows if r['name'] == 'Nuvali Park')
        self.assertEqual(nuvali['slug'], 'nuvali')
        self.assertEqual((nuvali['latitude'], nuvali['longitude']), (14.239906, 121.059477))

    def test_eight_new_explicit_statuses_and_null_coordinates(self):
        expected = {
            '50f6fa0f-8e79-41c1-8f15-654bde693185': 'draft',
            '90e42f09-5375-4935-aabe-28ca8f02d539': 'draft',
            '929c8840-9203-4ceb-929a-a47b80240305': 'published',
            'cc208fcc-bfff-4846-ad51-08915d0c3100': 'published',
            '4a436763-acde-4968-94d9-c3453e1bfc44': 'published',
            'defa76fd-3ab9-4043-9ca7-b1c86e696722': 'published',
            '99cc7af3-6c4b-4b49-801d-3b901b04af3f': 'published',
            '128cfb4c-7fca-45e8-8ad7-5ba7ba11a100': 'published',
        }
        self.assertEqual({r['id']: r['status'] for r in self.rows if not r['existing']}, expected)
        for r in self.rows:
            if not r['existing']:
                self.assertEqual(r['action'], 'INSERT NEW')
                self.assertIsNone(r['latitude'])
                self.assertIsNone(r['longitude'])
                if r['status'] == 'published':
                    self.assertEqual(r['category'], 'dining')
                    self.assertEqual(r['tourism_hours_status'], 'unverified')
                    self.assertIn('*', r['tourism_opening_hours_raw'])
                    self.assertIn('*', r['tourism_closing_hours_raw'])
            else:
                self.assertEqual(r['status'], 'published')
        self.assertEqual(sum(r['latitude'] is not None for r in self.rows), 9)

    def test_sixteen_unmatched_records_remain_outside_transition(self):
        unchanged = self.plan['untouched']
        self.assertEqual(len(unchanged), 16)
        self.assertIn('Lakeside Activities (Nuvali)', [r['name'] for r in unchanged])
        self.assertTrue({r['id'] for r in unchanged}.isdisjoint(r['id'] for r in self.rows))
        for r in unchanged:
            self.assertIsNone(r['tourism_type'])
            self.assertNotIn(r['id'], self.sql)
        self.assertEqual(self.plan['baseline_published_count'], 28)

    def test_review_sql_exactly_matches_plan_without_executing_it(self):
        self.assertEqual(self.sql, render_review_sql(self.plan))
        section = self.sql.split(') VALUES\n', 1)[1].split('DO $guard$', 1)[0]
        tuples = []
        for line in section.strip().splitlines():
            tokens = re.findall(r"'(?:''|[^'])*'|NULL|\d+", line)
            tuples.append([None if t == 'NULL' else t[1:-1].replace("''", "'") if t.startswith("'") else int(t) for t in tokens])
        self.assertEqual(len(tuples), 20)
        for r, values in zip(self.rows, tuples):
            old = r['existing'] or {}
            expected = [r['id'], r['slug'], old.get('name'), old.get('category')]
            expected += [r[k] for k in VALUE_FIELDS if k != 'tourism_source']
            expected.append(r['status'])
            self.assertEqual(values, expected)
        self.assertIn('AND p.status = r.final_status', self.sql)
        self.assertNotIn("CASE WHEN r.expected_name IS NULL THEN 'draft'", self.sql)

    def test_sql_explicit_uuid_updates_preserve_protected_fields_and_no_retirements(self):
        updates = re.findall(r'UPDATE public\.places SET\s+(.*?)WHERE id = \'([^\']+)\'::uuid;', self.sql, re.S)
        self.assertEqual(len(updates), 12)
        self.assertEqual({identity for _, identity in updates}, {r['id'] for r in self.rows if r['existing']})
        for assignments, identity in updates:
            fields = assignments.split(') =', 1)[0]
            for field in ('latitude', 'longitude', 'slug', 'status', 'created_at', 'id'):
                self.assertNotRegex(fields, r'\b' + field + r'\b')
        self.assertEqual(self.sql.count('INSERT INTO public.places ('), 8)
        self.assertEqual(self.sql.count("NULL, NULL, NULL, 'draft'"), 2)
        self.assertEqual(self.sql.count("NULL, NULL, NULL, 'published'"), 6)
        inserts = re.findall(r"SELECT '([^']+)'::uuid, .*?NULL, NULL, NULL, '([^']+)'\nFROM tourism_review WHERE tourism_source_row = (\d+);", self.sql)
        self.assertEqual({identity: status for identity, status, _ in inserts},
                         {r['id']: r['status'] for r in self.rows if not r['existing']})
        self.assertNotRegex(self.sql.upper(), r'\bDELETE\b|\bARCHIVE(?:D)?\b|ON CONFLICT|CREATE FUNCTION|ALTER TABLE')

    def test_guards_and_atomicity_are_present(self):
        for text in ('BEGIN;', 'COMMIT;', 'LOCK TABLE public.places IN SHARE ROW EXCLUSIVE MODE;',
                     'Existing identity/metadata drift', 'New UUID or slug already exists',
                     'p.tourism_type IS NULL', 'Unmatched existing records changed',
                     'Existing identity/location preservation failed', 'Expected exactly eight new records'):
            self.assertIn(text, self.sql)
        self.assertLess(self.sql.index('$guard$;'), self.sql.index('UPDATE public.places SET'))
        self.assertLess(self.sql.index('$verify$;'), self.sql.index('COMMIT;'))

    def test_provenance_is_stable_and_does_not_contain_local_paths(self):
        for r in self.rows:
            self.assertEqual(r['tourism_source'], SOURCE)
            self.assertNotRegex(r['tourism_source'], r'[A-Za-z]:|\\|/Users/|/home/')
        self.assertNotRegex(self.sql, r'[A-Za-z]:\\|C:/|C:\\')

    def test_protected_transition_data_unchanged_and_current_policy_versions(self):
        # The transition's immutable data baseline remains authoritative. Ranking
        # and selection intentionally evolved later; do not replace their old
        # hashes in the historical plan with digests of today's implementation.
        protected_data = {'migrations/0011_places_tourism_metadata.sql',
                          'data/santa_rosa_places/weather_metadata.json'}
        current_policies = {'recommendation_engine.py', 'itinerary_selection_policy.py'}
        self.assertEqual(set(self.plan['protected_sha256']), protected_data | current_policies)
        for path in sorted(protected_data):
            expected = self.plan['protected_sha256'][path]
            data = (ROOT / path).read_bytes()
            if path == 'data/santa_rosa_places/weather_metadata.json':
                # Phase 4 permits only identity reconciliation for the original
                # three curated records; retain the immutable Phase 3 baseline.
                from test_tourism_weather_identity import pre_reconciliation_bytes
                data = pre_reconciliation_bytes(json.loads(data))
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, path)
        self.assertEqual(RANKING_POLICY_VERSION, 'category-interest-tourism-v2')
        self.assertEqual(SELECTION_POLICY_VERSION, 'pace-count-category-tourism-cluster-v3')

    def test_tourism_priority_preserves_category_scores_and_eligibility(self):
        base = tuple(parse_place_row(r['existing']) for r in self.rows if r['existing'])
        proposed = tuple(parse_place_row(r['existing'] | {k: r[k] for k in (
            'tourism_type', 'tourism_category', 'tourism_opening_hours_raw', 'tourism_closing_hours_raw',
            'tourism_hours_status', 'tourism_source', 'tourism_source_row')}) for r in self.rows if r['existing'])
        prefs = preferences(interests=['attraction', 'shopping', 'heritage'])
        before, after = rank_candidates(prefs, base), rank_candidates(prefs, proposed)
        self.assertEqual({c.place_id for c in before.matched}, {c.place_id for c in after.matched})
        self.assertEqual({c.place_id for c in before.unmatched}, {c.place_id for c in after.unmatched})
        before_by_id = {c.place_id: c for c in (*before.matched, *before.unmatched)}
        places_by_id = {p.id: p for p in proposed}
        priority = {'Local': 0, None: 1, 'Common': 2}
        for candidate in (*after.matched, *after.unmatched):
            original = before_by_id[candidate.place_id]
            self.assertEqual((candidate.category, candidate.deterministic_score, candidate.matched_signals),
                             (original.category, original.deterministic_score, original.matched_signals))
            self.assertEqual(candidate.tourism_priority, priority[places_by_id[candidate.place_id].tourism_type])
        self.assertEqual({c.deterministic_score for c in after.matched}, {1})
        self.assertEqual([(c.tourism_priority, c.place_id) for c in after.matched],
                         sorted((c.tourism_priority, c.place_id) for c in after.matched))
        selected = select_destinations(prefs, after.matched)
        self.assertEqual({c.category for c in selected}, set(prefs['interests']))
        self.assertTrue(any(c.category == 'shopping' and c.tourism_priority == 2 for c in selected))

        # Explicitly cover the NULL tier, which is absent from the proposed
        # classified fixture. This is an in-memory copy, never a catalog write.
        local = next(p for p in proposed if p.category in prefs['interests'] and p.tourism_type == 'Local')
        common = next(p for p in proposed if p.category in prefs['interests'] and p.tourism_type == 'Common')
        unknown = replace(common, id='ffffffff-ffff-4fff-8fff-ffffffffffff', tourism_type=None)
        tiers = rank_candidates(prefs, (common, unknown, local))
        self.assertEqual([c.place_id for c in tiers.matched], [local.id, unknown.id, common.id])
        self.assertEqual([c.place_id for c in select_destinations(prefs, tiers.matched, place_count=1)],
                         [local.id])
        self.assertIsNone(unknown.tourism_type)

    def test_plan_validation_rejects_collisions_bad_status_mapping_and_identity_changes(self):
        for field, value in (('id', self.rows[1]['id']), ('slug', self.rows[1]['slug']),
                             ('tourism_source_row', 3), ('category', 'shopping'),
                             ('tourism_hours_status', 'verified'), ('tourism_type', None),
                             ('latitude', None), ('tourism_source', 'C:\\source.xlsx')):
            invalid = deepcopy(self.plan)
            invalid['rows'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_plan(invalid)

    def test_invalid_final_statuses_are_rejected(self):
        for index in (0, 11, 14):
            invalid = deepcopy(self.plan)
            invalid['rows'][index]['status'] = 'archived'
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_plan(invalid)
        invalid = deepcopy(self.plan)
        invalid['rows'][0]['status'] = 'draft'
        with self.assertRaises(ValueError):
            validate_plan(invalid)


if __name__ == '__main__':
    unittest.main()
