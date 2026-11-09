"""First batch content decisions do not authorize database or security changes."""
from copy import deepcopy
from pathlib import Path
import unittest

from destination_categories import parse_registry,CategoryConfigurationError
from tools.local_destination_catalog import read_json,CatalogError
from tools.prepare_first_publication_batch import prepare,DESCRIPTIONS

ROOT=Path(__file__).resolve().parents[1]


class FirstPublicationBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs=[read_json(ROOT/'local_catalog'/n) for n in (
            'production-mapped-publication-v4.review.json','owner-research-reuse.review.json',
            'destination-images.final-mapping.review.json','category-parent-mapping.proposed.review.json','category-registry.review.json')]
        cls.result,cls.registry=prepare(*cls.docs)

    def test_81_locations_accepted_without_approving_17_exceptions(self):
        result=self.result
        self.assertEqual(result['accepted_researched_locations'],81)
        self.assertEqual(result['first_batch_count'],65)
        self.assertEqual(result['accepted_locations_held_for_content_decisions'],16)
        self.assertEqual(result['unresolved_location_draft_count'],17)
        self.assertEqual(len(result['existing_published_csv_records_outside_first_batch']),14)
        self.assertTrue(all(r['separate_status_change_approval_required'] for r in result['existing_published_csv_records_outside_first_batch']))
        rows=result['records']
        for n in (2,10,22,44,46,87,88,89,90,91,92,93,94,95,96,97,98):
            self.assertFalse(rows[n-1]['research_location_accepted'])
            self.assertEqual(rows[n-1]['final_status_proposal'],'draft')

    def test_descriptions_categories_and_aliases_wait_for_approval(self):
        result=self.result
        self.assertEqual({r['csv_record'] for r in result['description_proposals']},{56,58,59,60})
        for proposal in result['description_proposals']:
            self.assertFalse(proposal['approved'])
            self.assertEqual(proposal['description'],DESCRIPTIONS[proposal['csv_record']])
            self.assertIsNone(result['records'][proposal['csv_record']-1]['proposed_values']['description'])
        for n in (3,12,42,43,47,48,49,50,51,56,58,59,60,70,72,73):
            self.assertFalse(result['records'][n-1]['first_content_batch_candidate'])

    def test_stored_coordinate_corrections_remain_complete_unapproved_pairs(self):
        corrections=self.result['coordinate_correction_proposals']
        self.assertEqual([(r['csv_record'],r['proposed_pair']) for r in corrections],[(2,[14.239906,121.059477]),(10,[14.28803,121.09437])])
        self.assertTrue(all(not r['approved'] for r in corrections))

    def test_merged_registry_keeps_specific_categories_legacy_keys_and_is_not_active(self):
        registry=self.registry
        self.assertFalse(registry['approved']);self.assertEqual(len(registry['categories']),79)
        with self.assertRaises(CategoryConfigurationError):parse_registry(registry,project_ref=registry['project_ref'])
        # A synthetic approval copy checks structural compatibility, not owner approval.
        parsed=parse_registry(registry|dict(approved=True),project_ref=registry['project_ref'])
        self.assertEqual(parsed['resort-swimming-pool']['parent_key'],'attraction')
        self.assertEqual(parsed['badminton-court']['parent_key'],'attraction')

    def test_images_inputs_and_staging_security_state_preserved(self):
        before=deepcopy(self.docs);result,_=prepare(*self.docs)
        self.assertEqual(before,self.docs);self.assertFalse(result['executable'])
        self.assertTrue(all(not r['ready_to_execute'] and r['proposed_values']['status']=='draft' for r in result['records']))
        self.assertEqual([r['image_final_mapping'] for r in result['records']],self.docs[2]['records'])
        self.assertEqual(len(result['proposed_archives']),7)
        self.assertTrue(all(not r['owner_explicit_approval_recorded'] for r in result['proposed_archives']))

    def test_wrong_research_identity_or_changed_81_inventory_stops_preparation(self):
        docs=deepcopy(self.docs);docs[1]['records'][0]['name']='wrong'
        with self.assertRaises(CatalogError):prepare(*docs)
        docs=deepcopy(self.docs);docs[1]['records'][0]['coordinate_followup_required']=True
        with self.assertRaises(CatalogError):prepare(*docs)


if __name__=='__main__':unittest.main()
