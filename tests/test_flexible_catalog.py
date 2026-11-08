"""Offline registry, destination rendering contracts and category eligibility."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from destination_categories import (CATEGORIES, CATEGORY_LABELS, CategoryConfigurationError,
                                    LEGACY_LABELS, category_matches, parse_registry)
from admin_management_service import DestinationValidationError, validate_destination
from places_service import PlacesConsistencyError, PlacesService, parse_place_row
from recommendation_engine import rank_candidates
from itinerary_selection_policy import select_destinations
from tests import test_places_service as places_fixture


def document():
    return dict(schema_version=1, approved=True, project_ref='synthetic-project', categories=[
        dict(key=key, label=label, parent_key=None) for key, label in LEGACY_LABELS.items()
    ] + [dict(key='specialty-coffee', label='Specialty Coffee', parent_key='dining')])


class FlexibleCatalogTests(unittest.TestCase):
    def test_registry_requires_owner_approval_target_unique_keys_and_acyclic_relationships(self):
        base = document()
        for change in [dict(approved=False), dict(project_ref='wrong-project')]:
            with self.assertRaises(CategoryConfigurationError):
                parse_registry(base | change, project_ref='synthetic-project')
        for kind in ('duplicate', 'cycle', 'dangling', 'bad_key', 'missing_legacy'):
            bad = deepcopy(base)
            if kind == 'duplicate': bad['categories'].append(bad['categories'][-1])
            elif kind == 'cycle': bad['categories'][-1]['parent_key'] = 'specialty-coffee'
            elif kind == 'dangling': bad['categories'][-1]['parent_key'] = 'missing'
            elif kind == 'bad_key': bad['categories'][-1]['key'] = '<script>'
            else: bad['categories'][0]['key'] = 'not-attraction'
            with self.subTest(kind=kind), self.assertRaises(CategoryConfigurationError):
                parse_registry(bad, project_ref='synthetic-project')

    def test_legacy_behavior_unchanged_and_unapproved_rollout_fails_closed(self):
        with patch.dict(os.environ, {'ROSAGO_FLEXIBLE_CATALOG_ENABLED': 'false'}):
            self.assertEqual(set(CATEGORIES), set(LEGACY_LABELS))
            self.assertNotIn('specialty-coffee', CATEGORIES)
        with patch.dict(os.environ, {'ROSAGO_FLEXIBLE_CATALOG_ENABLED': 'true', 'ROSAGO_CATEGORY_REGISTRY_PATH': ''}):
            with self.assertRaises(CategoryConfigurationError):
                list(CATEGORIES)

    def test_dynamic_categories_schedule_parsing_recommendations_and_legacy_interests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'registry.json'; path.write_text(json.dumps(document()), encoding='utf-8')
            env = {'ROSAGO_FLEXIBLE_CATALOG_ENABLED': 'true', 'ROSAGO_CATEGORY_REGISTRY_PATH': str(path),
                   'SUPABASE_URL': 'https://synthetic-project.supabase.co'}
            with patch.dict(os.environ, env):
                self.assertIn('specialty-coffee', CATEGORIES)
                self.assertEqual(CATEGORY_LABELS['specialty-coffee'], 'Specialty Coffee')
                self.assertTrue(category_matches('specialty-coffee', 'dining'))
                self.assertFalse(category_matches('dining', 'specialty-coffee'))
                row = places_fixture.PlacesServiceTests.row(); row.update(category='specialty-coffee', operating_days_raw='Monday–Friday\nVerify holidays')
                place = parse_place_row(row)
                self.assertEqual(place.operating_days_raw, row['operating_days_raw'])
                for interest in ('dining', 'specialty-coffee'):
                    prefs = dict(interests=[interest], trip_pace='balanced', start_date='2026-11-09', end_date='2026-11-09')
                    ranked = rank_candidates(prefs, (place,))
                    self.assertEqual(ranked.match_count, 1)
                    self.assertEqual(select_destinations(prefs, ranked.matched, places=(place,))[0].place_id, place.id)
                service = PlacesService(lambda: None)
                self.assertIn('operating_days_raw', service._projection)
                candidates = tuple(replace(place, id=f'00000000-0000-4000-8000-{i:012d}',
                                           slug=f'synthetic-{i}', latitude=None, longitude=None)
                                   for i in range(1, 99))
                ranked = rank_candidates(dict(interests=['dining']), candidates)
                self.assertEqual(ranked.match_count, 98)
                self.assertEqual(ranked.total_candidate_count, 98)
                row['operating_days_raw'] = 'x' * 2001
                with self.assertRaises(PlacesConsistencyError): parse_place_row(row)

    def test_user_browse_and_detail_render_qualified_labels_and_unverified_days(self):
        from test_places_routes import PlacesRouteTests
        fixture = PlacesRouteTests('test_logged_out_list_and_exact_template_boundary')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'registry.json'
            path.write_text(json.dumps(document()), encoding='utf-8')
            env = {'ROSAGO_FLEXIBLE_CATALOG_ENABLED': 'true', 'ROSAGO_CATEGORY_REGISTRY_PATH': str(path),
                   'SUPABASE_URL': 'https://synthetic-project.supabase.co'}
            with patch.dict(os.environ, env):
                place = replace(fixture.place, category='specialty-coffee', operating_days_raw='Monday–Friday <unverified>')
                fixture.service.list_published.return_value = (place,)
                fixture.service.get_published_by_slug.return_value = place
                for url in ['/places?category=specialty-coffee', '/places/synthetic-place']:
                    response = fixture.get(url)
                    self.assertEqual(response.status_code, 200)
                    html = response.get_data(as_text=True)
                    self.assertIn('Specialty Coffee', html)
                    self.assertIn('category-registry-data', html)
                self.assertIn('Monday–Friday &lt;unverified&gt;', html)

    def test_schedule_mutation_is_gated_and_text_is_not_parsed_into_fake_hours(self):
        payload = dict(name='Synthetic', category='nature', description='Synthetic record', address='Synthetic address',
                       latitude='', longitude='', operating_days_raw='Mon–Fri\nVerify')
        with patch.dict(os.environ, {'ROSAGO_FLEXIBLE_CATALOG_ENABLED': 'false'}):
            with self.assertRaises(DestinationValidationError): validate_destination(payload, tourism_enabled=False)
        # The category resolver remains legacy in this unit test; parser qualification above tests the registry itself.
        with patch('admin_management_service.flexible_catalog_enabled', return_value=True):
            result = validate_destination(payload, tourism_enabled=False)
            self.assertEqual(result['operating_days_raw'], payload['operating_days_raw'])
            self.assertNotIn('opening_time', result)
            provenance = payload | dict(tourism_source='reviewed.csv', tourism_source_row=2)
            self.assertEqual(validate_destination(provenance, tourism_enabled=False)['tourism_source_row'], 2)
            for bad in [provenance | dict(tourism_source_row=True), provenance | dict(tourism_source_row=1),
                        provenance | dict(tourism_source=None)]:
                with self.assertRaises(DestinationValidationError): validate_destination(bad, tourism_enabled=False)


if __name__ == '__main__':
    unittest.main()
