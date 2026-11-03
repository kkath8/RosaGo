"""Offline metadata contracts; no workbook import or database writes."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call

from itinerary_preview import compute_catalog_fingerprint
from itinerary_selection_policy import select_destinations
from place_model import CATEGORIES
from places_service import (PlacesService, PlacesConsistencyError, PROJECTION,
                            TOURISM_FIELDS, TOURISM_PROJECTION, parse_place_row)
from recommendation_engine import rank_candidates
import test_places_service as catalog_fixtures
from test_recommendation_engine import preferences


class TourismMetadataTests(unittest.TestCase):
    def row(self, **changes):
        return catalog_fixtures.PlacesServiceTests.row(latitude=None, longitude=None, **changes)

    def test_legacy_and_explicit_null_metadata_without_coordinates(self):
        legacy = parse_place_row(self.row())
        explicit = parse_place_row(self.row(**dict.fromkeys(TOURISM_FIELDS)))
        self.assertEqual(legacy, explicit)
        self.assertIsNone(explicit.latitude)
        self.assertIsNone(explicit.longitude)
        for field in TOURISM_FIELDS:
            self.assertIsNone(getattr(explicit, field))

    def test_types_and_statuses_accept_only_exact_vocabulary_or_null(self):
        for field, valid in (('tourism_type', ('Local', 'Common', None)),
                             ('tourism_hours_status', ('unverified', 'verify_required', 'not_supplied', None))):
            for value in valid:
                with self.subTest(field=field, value=value):
                    self.assertEqual(getattr(parse_place_row(self.row(**{field: value})), field), value)
            for value in ('local', 'Common ', 'verified', '', True, 1, [], {}):
                with self.subTest(field=field, value=value), self.assertRaises(PlacesConsistencyError):
                    parse_place_row(self.row(**{field: value}))

    def test_raw_source_values_are_preserved_independently(self):
        for opening, closing, status in (('11:00 AM*', '12:00 AM*', 'unverified'),
                                         ('Verify', 'Verify', 'verify_required'),
                                         (None, None, 'not_supplied'),
                                         (' 11:00 AM* ', None, 'unverified')):
            item = parse_place_row(self.row(tourism_type='Local',
                tourism_category='Museum / Cultural Heritage', tourism_opening_hours_raw=opening,
                tourism_closing_hours_raw=closing, tourism_hours_status=status,
                tourism_source='City Tourism Office | RosaGO_Santa_Rosa_POIs.xlsx | Santa Rosa POIs',
                tourism_source_row=2))
            self.assertEqual(item.category, 'nature')
            self.assertEqual(item.tourism_category, 'Museum / Cultural Heritage')
            self.assertEqual(item.tourism_opening_hours_raw, opening)
            self.assertEqual(item.tourism_closing_hours_raw, closing)
            self.assertEqual(item.tourism_hours_status, status)
            self.assertEqual(item.tourism_source_row, 2)
            self.assertIn('Santa Rosa POIs', item.tourism_source)

    def test_metadata_text_and_source_row_bounds(self):
        for field, maximum in (('tourism_category', 250), ('tourism_opening_hours_raw', 250),
                               ('tourism_closing_hours_raw', 250), ('tourism_source', 500)):
            self.assertEqual(getattr(parse_place_row(self.row(**{field: 'x' * maximum})), field), 'x' * maximum)
            for value in ('', 'x' * (maximum + 1), True, 1, [], {}):
                with self.subTest(field=field, value=value), self.assertRaises(PlacesConsistencyError):
                    parse_place_row(self.row(**{field: value}))
        for value in (2, 1048576, None):
            self.assertEqual(parse_place_row(self.row(tourism_source_row=value)).tourism_source_row, value)
        for value in (1, 0, -1, 1048577, True, '2', 2.0):
            with self.subTest(value=value), self.assertRaises(PlacesConsistencyError):
                parse_place_row(self.row(tourism_source_row=value))

    def test_categories_and_fingerprint_unchanged_with_tourism_ranking_tiebreak(self):
        self.assertEqual(CATEGORIES, {'attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage', 'industrial'})
        for category in CATEGORIES:
            self.assertEqual(parse_place_row(self.row(category=category, tourism_category='Japanese Restaurant')).category, category)
        with self.assertRaises(PlacesConsistencyError):
            parse_place_row(self.row(category='Japanese Restaurant'))
        base = tuple(parse_place_row(self.row(id=f'00000000-0000-0000-0000-{n:012x}')) for n in range(1, 5))
        decorated = tuple(replace(item, tourism_type='Common' if n == 0 else 'Local',
                                 tourism_opening_hours_raw='Verify', tourism_hours_status='verify_required')
                          for n, item in enumerate(base))
        prefs = preferences()
        before, after = rank_candidates(prefs, base), rank_candidates(prefs, decorated)
        self.assertEqual([candidate.place_id for candidate in after.matched], [base[n].id for n in (1,2,3,0)])
        self.assertTrue(all(candidate.deterministic_score == 1 for candidate in after.matched))
        self.assertEqual(len(select_destinations(prefs, before.matched)),len(select_destinations(prefs, after.matched)))
        self.assertEqual(compute_catalog_fingerprint(base, publication_confirmed=True),
                         compute_catalog_fingerprint(decorated, publication_confirmed=True))

    def test_repository_selects_new_columns_only_when_explicitly_enabled(self):
        query = Mock()
        for method in ('select', 'eq', 'order', 'range', 'limit', 'retry'):
            getattr(query, method).return_value = query
        client = Mock()
        client.table.return_value = query
        @contextmanager
        def factory():
            yield client
        for enabled, projection in ((False, PROJECTION), (True, TOURISM_PROJECTION)):
            query.execute.return_value = SimpleNamespace(data=[
                self.row(tourism_type='Local') if enabled else self.row()])
            service = PlacesService(factory, tourism_metadata_enabled=enabled)
            query.reset_mock()
            self.assertEqual(service.list_published()[0].tourism_type, 'Local' if enabled else None)
            self.assertEqual(service.get_published_by_slug('synthetic-fixture').tourism_type, 'Local' if enabled else None)
            self.assertEqual([call.args[0] for call in query.select.call_args_list], [projection, projection])
            self.assertIn(call('status', 'published'), query.eq.call_args_list)
        with self.assertRaises(TypeError):
            PlacesService(factory, tourism_metadata_enabled='true')

    def test_migration_is_nullable_additive_and_contains_no_data_writes(self):
        path = Path(__file__).resolve().parents[1] / 'migrations/0011_places_tourism_metadata.sql'
        sql = '\n'.join(line for line in path.read_text(encoding='utf-8').splitlines() if not line.startswith('--'))
        self.assertEqual(sql.count('ADD COLUMN '), len(TOURISM_FIELDS))
        for field in TOURISM_FIELDS:
            self.assertIn('ADD COLUMN ' + field + ' ', sql)
        for forbidden in ('INSERT INTO', 'UPDATE public.', 'DELETE FROM', 'DROP ', 'NOT NULL',
                          'DEFAULT ', 'CREATE POLICY', 'GRANT ', 'REVOKE ', 'latitude', 'longitude'):
            self.assertNotIn(forbidden, sql)


if __name__ == '__main__':
    unittest.main()
