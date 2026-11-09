"""Offline evidence/identity gates; numeric coordinate validity never approves a place."""
from copy import deepcopy
import unittest

from tools.local_destination_catalog import CatalogError
from tools.prepare_current_catalog_review import build_plan
from tools.prepare_mapped_publication import apply_policy, disposition, seed_evidence, valid_pair
from tests.test_current_catalog_review import inventory, source, review


def fixture():
    sources = [source()]
    reviewed = review(sources)
    reviewed['records'][0]['proposed_coordinates'] = dict(latitude=14.25, longitude=121.05)
    plan = build_plan(inventory(), reviewed, sources, aliases={})
    plan.update(source_csv_sha256='synthetic-source', export_file_sha256='synthetic-export')
    return plan, reviewed, seed_evidence(plan, reviewed)


def approved(row):
    return row | dict(matching_identity_approved=True, coordinate_pair_verified=True,
        verified_latitude=14.25, verified_longitude=121.05,
        evidence_ref='Synthetic independently checked place/point', verified_by='Synthetic owner',
        verified_at='2026-01-01T00:00:00Z', category_relationships_approved=True)


class MappedPublicationTests(unittest.TestCase):
    def test_valid_numbers_and_previously_published_status_are_not_verification(self):
        plan, reviewed, evidence = fixture()
        result = apply_policy(plan, reviewed, evidence)
        self.assertEqual(result['csv_syntactically_valid_coordinate_pairs'], 1)
        self.assertEqual(result['approved_verified_coordinate_pairs'], 0)
        self.assertEqual(result['final_csv_published_count'], 0)
        self.assertEqual(result['final_csv_draft_count'], 1)
        self.assertFalse(result['actual_hosted_statuses_changed'])
        self.assertTrue(result['existing_published_to_draft_proposals'][0]['owner_status_change_approval_required'])

    def test_complete_evidence_can_make_a_record_ready_but_never_authorizes_execution(self):
        plan, reviewed, evidence = fixture()
        evidence['records'][0] = approved(evidence['records'][0])
        result = apply_policy(plan, reviewed, evidence)
        self.assertEqual(result['final_csv_published_count'], 1)
        self.assertEqual(result['record_ready_for_publication_count'], 1)
        self.assertFalse(result['records'][0]['ready_to_execute'])
        self.assertFalse(result['executable'])

    def test_verified_flag_cannot_bypass_identity_pair_or_evidence_fields(self):
        plan, _, evidence = fixture(); row = approved(evidence['records'][0])
        for fields in [dict(matching_identity_approved=False), dict(verified_latitude=None),
                       dict(verified_longitude=float('nan')), dict(evidence_ref=''), dict(verified_by=None),
                       dict(verified_at='2099-01-01T00:00:00Z')]:
            with self.subTest(fields=fields), self.assertRaises(CatalogError):
                disposition(plan['records'][0], row | fields)

    def test_coordinate_pair_bounds_types_and_completeness(self):
        self.assertTrue(valid_pair(14.25, 121.05))
        for pair in [(None, 121), (14, None), (True, 121), (91, 121), (14, 181), (14, float('inf'))]:
            self.assertFalse(valid_pair(*pair))

    def test_stored_pair_reuse_is_pending_and_cannot_auto_confirm_identity(self):
        plan, reviewed, _ = fixture()
        reviewed['records'][0]['proposed_coordinates'] = dict(latitude=None, longitude=None)
        plan['records'][0]['original_row'].update(latitude=14.25, longitude=121.05)
        evidence = seed_evidence(plan, reviewed)
        self.assertEqual(evidence['records'][0]['candidate_origin'], 'stored_pair_reuse_requires_identity_and_location_approval')
        self.assertFalse(evidence['records'][0]['matching_identity_approved'])
        self.assertEqual(apply_policy(plan, reviewed, evidence)['final_csv_published_count'], 0)

    def test_missing_description_remains_draft_despite_verified_coordinates(self):
        plan, _, evidence = fixture(); entry = plan['records'][0]
        entry['source_errors'] = ['missing_required:Description']
        row = approved(evidence['records'][0])
        self.assertEqual(disposition(entry, row)['final_status_proposal'], 'draft')
        self.assertEqual(disposition(entry, row | dict(description_correction_approved=True,
            description_correction='Owner-supplied synthetic description'))['final_status_proposal'], 'published')
        with self.assertRaises(CatalogError):
            disposition(entry, row | dict(description_correction_approved=True, description_correction=''))

    def test_real_coordinate_error_requires_explicit_verified_replacement(self):
        plan, _, evidence = fixture(); entry = plan['records'][0]
        entry['source_errors'] = ['latitude_hemisphere_mismatch']
        self.assertIn('latitude_hemisphere_mismatch', disposition(entry, evidence['records'][0])['unresolved_record_blockers'])
        self.assertEqual(disposition(entry, approved(evidence['records'][0]))['final_status_proposal'], 'published')

    def test_tourism_unknown_and_category_collision_do_not_become_implicit_approvals(self):
        plan, _, evidence = fixture(); entry = plan['records'][0]
        entry['warnings'].append('tourism_type_not_supplied')
        row = approved(evidence['records'][0])
        self.assertEqual(disposition(entry, row)['final_status_proposal'], 'draft')
        self.assertEqual(disposition(entry, row | dict(tourism_type_decision_approved=True))['final_status_proposal'], 'published')
        entry['proposed_values']['category'] = None
        self.assertEqual(disposition(entry, row | dict(tourism_type_decision_approved=True))['final_status_proposal'], 'draft')

    def test_evidence_bound_to_exact_source_target_record_and_existing_uuid(self):
        plan, reviewed, evidence = fixture()
        for key in ('target_project_ref', 'source_csv_sha256', 'export_file_sha256'):
            with self.subTest(key=key), self.assertRaises(CatalogError):
                apply_policy(plan, reviewed, evidence | {key:'wrong'})
        for key in ('name','existing_id'):
            bad = deepcopy(evidence); bad['records'][0][key] = 'wrong'
            with self.subTest(key=key), self.assertRaises(CatalogError): apply_policy(plan, reviewed, bad)

    def test_omitted_records_never_auto_archive_or_change_original_proposal(self):
        plan, reviewed, evidence = fixture(); before = deepcopy(plan)
        result = apply_policy(plan, reviewed, evidence)
        self.assertTrue(all(not row['owner_explicit_approval_recorded'] for row in result['proposed_archives']))
        self.assertEqual(plan, before)
        with self.assertRaises(CatalogError): apply_policy(plan, reviewed, evidence | dict(approved_archive_ids=['unknown']))


if __name__ == '__main__':
    unittest.main()
