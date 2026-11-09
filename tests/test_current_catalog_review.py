"""Synthetic, offline tests for the owner inventory and approval-only diff."""
from copy import deepcopy
import json
import unittest

from tests.test_local_destination_catalog import row
from tools.local_destination_catalog import CatalogError, normalized_name
from tools.prepare_current_catalog_review import TARGET, build_plan, validate_inventory


def inventory(rows=None):
    rows = rows if rows is not None else [row(1, status='published'), row(2), row(3, status='archived')]
    return dict(export_format='rosago_owner_destination_inventory_v1',
                owner_selected_project_ref=TARGET, project_identity_requires_dashboard_confirmation=True,
                table='public.places', scope='all_publication_statuses', transaction_read_only='on',
                database_role='postgres', row_security_active_for_export_role=False,
                unexpected_status_count=0, exported_at='2026-11-08T01:33:39Z',
                rows=rows, row_count=len(rows),
                status_counts={s: sum(r['status'] == s for r in rows) for s in ('published', 'draft', 'archived')})


def source(name='Synthetic destination 1', category='Flexible Category'):
    return {'Place Name': name, 'Type': 'Local', 'Category': category, 'Environment': 'Outdoor',
            'Latitude': '', 'Longitude': '', 'Days of the Week': '',
            'Opening Hours': '', 'Closing Hours': '', 'Description': 'Revised synthetic description.',
            'Address': 'Revised synthetic address', 'Picture / Photo Link': 'https://example.org/not-promoted.jpg', '': ''}


def review(sources):
    return dict(source_categories={s['Category']: 1 for s in sources}, duplicate_normalized_names=[],
                records=[dict(record_number=i, csv_line_start=i + 1, name=s['Place Name'], errors=[], warnings=[],
                              proposed_coordinates={'latitude': None, 'longitude': None})
                         for i, s in enumerate(sources, 1)])


class CurrentCatalogReviewTests(unittest.TestCase):
    def test_complete_owner_inventory_and_dashboard_wrapper(self):
        expected = inventory()
        self.assertEqual(validate_inventory(expected), expected)
        self.assertEqual(validate_inventory([{'destination_inventory_json': json.dumps(expected)}]), expected)

    def test_target_read_only_visibility_scope_and_counts_fail_closed(self):
        changes = [('owner_selected_project_ref', 'jfaufpfzfhysqkhcdsrs'),
                   ('transaction_read_only', 'off'), ('row_security_active_for_export_role', True),
                   ('database_role', 'authenticated'), ('scope', 'published'),
                   ('unexpected_status_count', True), ('row_count', 2),
                   ('status_counts', {'published': 1, 'draft': True, 'archived': 1})]
        for field, value in changes:
            with self.subTest(field=field), self.assertRaises(CatalogError):
                validate_inventory(inventory() | {field: value})

    def test_duplicate_ids_slugs_names_or_unexpected_fields_fail(self):
        for key, value in [('id', row(1)['id']), ('slug', row(1)['slug']), ('name', row(1)['name'])]:
            rows = [row(1), row(2, **{key: value})]
            with self.subTest(key=key), self.assertRaises(CatalogError):
                validate_inventory(inventory(rows))
        bad = row(1) | {'private_session': 'not allowed'}
        with self.assertRaises(CatalogError):
            validate_inventory(inventory([bad]))

    def test_row_timestamps_beyond_export_fail(self):
        with self.assertRaises(CatalogError):
            validate_inventory(inventory([row(1, updated_at='2026-11-09T00:00:00Z')]))

    def test_duplicate_keys_in_wrapped_json_fail(self):
        with self.assertRaises(CatalogError):
            validate_inventory([{'destination_inventory_json': '{"rows":[],"rows":[]}'}])

    def test_update_preserves_identity_photo_coordinates_and_blank_optional_values(self):
        old = row(1, status='published', latitude=14.25, longitude=121.05,
                  image_url='https://example.org/original.jpg', tourism_type='Common',
                  tourism_opening_hours_raw='Preserve raw schedule')
        inv = inventory([old]); sources = [source()]; sources[0]['Type'] = ''
        before = deepcopy(inv)
        result = build_plan(inv, review(sources), sources, aliases={})
        entry = result['records'][0]
        for key in ('id', 'slug', 'created_at', 'updated_at', 'image_url', 'latitude', 'longitude', 'tourism_type', 'tourism_opening_hours_raw'):
            self.assertEqual(entry['proposed_values'][key], old[key])
        self.assertEqual(inv, before)
        self.assertFalse(entry['ready_to_execute'])
        self.assertEqual(entry['expected_updated_at'], old['updated_at'])

    def test_alias_identity_is_explicit_proposal_and_fuzzy_names_never_assign_id(self):
        inv = inventory([row(1, name='Synthetic Park', status='published')])
        sources = [source('Synthetic Park Visitor Area')]
        proposed = build_plan(inv, review(sources), sources, aliases={'Synthetic Park Visitor Area': 'Synthetic Park'})
        self.assertEqual(proposed['alias_update_count'], 1)
        self.assertIn('owner_confirmation_of_alias_identity', proposed['records'][0]['unresolved_record_blockers'])
        unmatched = build_plan(inv, review(sources), sources, aliases={})
        self.assertEqual(unmatched['proposed_new_count'], 1)
        self.assertIsNone(unmatched['records'][0]['existing_id'])
        self.assertTrue(unmatched['records'][0]['other_name_candidates'])

    def test_two_sources_cannot_claim_one_existing_uuid(self):
        inv = inventory([row(1, name='Synthetic Park')])
        sources = [source('Synthetic Park'), source('Synthetic Park Alias')]
        with self.assertRaises(CatalogError):
            build_plan(inv, review(sources), sources, aliases={'Synthetic Park Alias': 'Synthetic Park'})

    def test_archives_are_explicit_proposals_only_for_omitted_published_rows(self):
        sources = [source('Brand New Fixture')]
        result = build_plan(inventory(), review(sources), sources, aliases={})
        self.assertEqual(len(result['proposed_archives']), 1)
        self.assertEqual(result['proposed_archives'][0]['expected_status'], 'published')
        self.assertTrue(result['proposed_archives'][0]['owner_explicit_approval_required'])
        self.assertEqual(len(result['unchanged_records']), 2)
        self.assertEqual(result['automatic_deletes'], [])
        self.assertFalse(result['executable'])
        self.assertEqual(result['projected_final_status_counts_if_all_approved_and_resolved'],
                         {'published': 1, 'draft': 1, 'archived': 2})

    def test_new_records_start_draft_with_no_assigned_uuid_or_promoted_photo(self):
        sources = [source('A New Fixture')]
        entry = build_plan(inventory(), review(sources), sources, aliases={})['records'][0]
        self.assertEqual(entry['proposed_values']['status'], 'draft')
        self.assertNotIn('id', entry['proposed_values'])
        self.assertIsNone(entry['proposed_values']['image_url'])
        self.assertEqual(entry['final_status_proposal'], 'published')

    def test_source_errors_and_category_collisions_remain_blocked(self):
        sources = [source('New One', 'Category / A'), source('New Two', 'Category A')]
        report = review(sources); report['records'][0]['errors'] = ['missing_required:Description']
        result = build_plan(inventory(), report, sources, aliases={})
        self.assertEqual(result['csv_records_requiring_corrections'], [1])
        self.assertTrue(all(e['proposed_values']['category'] is None for e in result['records']))
        self.assertTrue(all('category_key_collision_requires_owner_decision' in e['unresolved_record_blockers']
                            for e in result['records']))

    def test_shared_coordinates_do_not_merge_different_destinations(self):
        sources = [source('Fixture Tenant One'), source('Fixture Tenant Two')]
        report = review(sources)
        for record in report['records']:
            record['proposed_coordinates'] = {'latitude': 14.25, 'longitude': 121.05}
        result = build_plan(inventory(), report, sources, aliases={})
        self.assertEqual(result['proposed_new_count'], 2)
        self.assertEqual(result['exact_shared_coordinate_groups'][0]['csv_records'], [1, 2])


if __name__ == '__main__':
    unittest.main()
