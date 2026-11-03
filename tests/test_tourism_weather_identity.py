"""Offline identity reconciliation checks; no research, SQL or live requests."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from destination_weather_metadata import load_weather_catalog, validate_weather_catalog
from places_service import parse_place_row

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/santa_rosa_places'
CURATED = {'enchanted-kingdom': 'mixed', 'sm-city-santa-rosa': 'indoor',
           'robinson-s-santa-rosa': 'indoor'}


def transition_plan():
    return json.loads((FOLDER / 'tourism_transition_plan.json').read_text(encoding='utf-8'))


def current_catalog_rows():
    """Applied transition identities, including two drafts; excludes old test data."""
    plan = transition_plan()
    return plan['rows'] + plan['untouched']


def catalog_place(row):
    return parse_place_row(dict(image_url=None, created_at='2026-10-26T00:00:00Z',
                                updated_at='2026-10-26T00:00:00Z') | row)


def pre_reconciliation_bytes(document):
    """Undo only allowed identity fields and reconstruct the original CRLF file.

    The Phase 3 immutable hash then proves every other row/value, classification,
    official source, verification date and metadata coverage stayed unchanged.
    """
    original = deepcopy(document)
    old = {r['slug']: r['existing'] for r in transition_plan()['rows'] if r['existing']}
    for row in original['destinations']:
        if row['slug'] in CURATED:
            for field in ('name', 'category', 'address'):
                row[field] = old[row['slug']][field]
    return (json.dumps(original, ensure_ascii=False, indent=2) + '\n').replace('\n', '\r\n').encode('utf-8')


class TourismWeatherIdentityTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((FOLDER / 'weather_metadata.json').read_text(encoding='utf-8'))
        self.catalog = validate_weather_catalog(self.document)
        self.current = {r['slug']: r for r in current_catalog_rows()}

    def test_valid_catalog_same_three_curated_and_twenty_five_unknown(self):
        self.assertTrue(load_weather_catalog().available)
        self.assertEqual(len(self.catalog.records), 28)
        self.assertEqual({r['slug']: r['exposure'] for r in self.document['destinations']
                          if r['exposure'] != 'unknown'}, CURATED)
        self.assertEqual(sum(r['exposure'] == 'unknown' for r in self.document['destinations']), 25)

    def test_only_permitted_identities_changed_preserving_all_provenance_and_dates(self):
        expected = transition_plan()['protected_sha256']['data/santa_rosa_places/weather_metadata.json']
        self.assertEqual(hashlib.sha256(pre_reconciliation_bytes(self.document)).hexdigest(), expected)
        for row in self.document['destinations']:
            if row['slug'] in CURATED:
                self.assertEqual(row['verified_on'], '2026-10-26')

    def test_all_three_bind_to_current_uuid_slug_name_address_category(self):
        ids = {'enchanted-kingdom': '7544a303-a669-41ad-9723-21b440c8e1ff',
               'sm-city-santa-rosa': '277837ea-06bf-43ab-a509-c6d88cb44956',
               'robinson-s-santa-rosa': '428a525e-259d-4a89-90f4-1c231c6d6eae'}
        for row in self.document['destinations']:
            if row['slug'] in CURATED:
                place = catalog_place(self.current[row['slug']])
                self.assertEqual(place.id, ids[place.slug])
                for field in ('slug', 'name', 'category', 'address'):
                    self.assertEqual(row[field], getattr(place, field))
                metadata = self.catalog.for_place(place)
                self.assertEqual(metadata.exposure, CURATED[place.slug])
                for field in ('source_url', 'source_note', 'verified_on'):
                    self.assertEqual(getattr(metadata, field), row[field])

    def test_every_other_current_destination_including_drafts_stays_unknown(self):
        for row in self.current.values():
            if row['slug'] not in CURATED:
                self.assertEqual(self.catalog.for_place(catalog_place(row)).exposure, 'unknown')
        drafts = [r for r in self.current.values() if r.get('status') == 'draft']
        self.assertEqual(len(drafts), 2)
        for row in drafts:
            self.assertNotIn(row['slug'], self.catalog.records)

    def test_local_common_and_null_type_do_not_change_classification(self):
        for slug in CURATED:
            place = catalog_place(self.current[slug])
            expected = self.catalog.for_place(place)
            for classification in ('Local', 'Common', None):
                self.assertEqual(self.catalog.for_place(replace(place, tourism_type=classification)), expected)

    def test_archived_test_identities_are_not_in_weather_catalog(self):
        self.assertFalse(any(slug.startswith('rosago-test-v1-') for slug in self.catalog.records))
        sample = catalog_place(self.current['enchanted-kingdom'])
        self.assertEqual(self.catalog.for_place(replace(sample, slug='rosago-test-v1-archived')).exposure, 'unknown')

    def test_lookup_stays_strict_and_metadata_fingerprint_changes(self):
        current = catalog_place(self.current['robinson-s-santa-rosa'])
        self.assertEqual(self.catalog.for_place(current).exposure, 'indoor')
        for field in ('slug', 'name', 'category', 'address'):
            value = 'heritage' if field == 'category' else 'different'
            self.assertEqual(self.catalog.for_place(replace(current, **{field: value})).exposure, 'unknown')
        old = validate_weather_catalog(json.loads(pre_reconciliation_bytes(self.document)))
        self.assertNotEqual(self.catalog.fingerprint, old.fingerprint)


if __name__ == '__main__':
    unittest.main()
