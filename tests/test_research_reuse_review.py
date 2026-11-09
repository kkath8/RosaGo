"""Owner research reuse is not fabricated independent evidence or write approval."""
from copy import deepcopy
from pathlib import Path
import unittest

from tools.local_destination_catalog import read_json, CatalogError
from tools.prepare_research_reuse_review import assess, table_rows

ROOT=Path(__file__).resolve().parents[1]


class ResearchReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs=[read_json(ROOT/name) for name in (
            'local_catalog/production-mapped-publication-v4.review.json',
            'local_catalog/csv-review-c55ed7076b59-v2.json',
            'local_catalog/destination-images.final-mapping.review.json',
            'data/santa_rosa_places/archive/tourism_transition_plan.json')]
        cls.result=assess(*cls.docs)

    def test_owner_confirmation_is_retained_without_independent_verification_claim(self):
        counts=self.result['counts']
        self.assertEqual(counts['owner_confirmed_researched_destinations'],98)
        self.assertEqual(counts['numeric_csv_pairs'],83)
        self.assertEqual(counts['researched_pairs_reusable_without_new_location_question'],81)
        self.assertEqual(counts['independently_documented_geographic_verifications'],0)
        self.assertTrue(all(r['research_evidence_class']=='owner_confirmed_original_research' for r in self.result['records']))

    def test_research_confirmation_cannot_fill_or_repair_bad_coordinates(self):
        rows=self.result['records']; exceptions=[r['csv_record'] for r in rows if not r['csv_pair_numeric_valid']]
        self.assertEqual(exceptions,[2,10,22,87,88,89,90,91,92,93,94,95,96,97,98])
        self.assertTrue(all(rows[n-1]['candidate_latitude'] is None and rows[n-1]['candidate_longitude'] is None for n in exceptions))
        self.assertEqual([r['csv_record'] for r in rows if r['conditional_stored_pair']],[2,10,90])
        self.assertTrue(all(rows[n-1]['location_policy_outcome']=='Draft until corrected' for n in exceptions))

    def test_pin_question_is_targeted_not_blanket_colocation_rejection(self):
        rows=self.result['records']
        self.assertTrue(all(rows[n-1]['coordinate_followup_required'] for n in (44,46)))
        self.assertTrue(all(not rows[n-1]['coordinate_followup_required'] for n in (5,24,32,36,33,34,35,38)))

    def test_missing_content_and_alias_decisions_survive_research_reuse(self):
        rows=self.result['records']
        self.assertEqual([r['csv_record'] for r in rows if not r['description_complete']],[56,58,59,60])
        self.assertEqual(sum(any('UUID alias' in x for x in r['additional_decisions']) for r in rows),10)
        self.assertEqual(sum(any('category key' in x for x in r['additional_decisions']) for r in rows),3)
        self.assertEqual(len(self.result['archives_remain_unapproved']),7)

    def test_image_and_security_state_never_mutated_or_authorized(self):
        before=deepcopy(self.docs);result=assess(*self.docs)
        self.assertEqual(self.docs,before);self.assertFalse(result['executable'])
        self.assertEqual(result['hosted_writes'],0)
        self.assertTrue(all(not r['hosted_application_approved'] for r in result['records']))
        self.assertIn('unassigned',result['records'][55]['image_action'])
        self.assertEqual(len(table_rows(result)),98)

    def test_target_source_and_identity_binding_mismatch_rejects_reuse(self):
        for index,key in [(0,'target_project_ref'),(1,'source_sha256')]:
            docs=deepcopy(self.docs);docs[index][key]='wrong'
            with self.subTest(key=key),self.assertRaises(CatalogError):assess(*docs)
        docs=deepcopy(self.docs);docs[1]['records'][0]['name']='different'
        with self.assertRaises(CatalogError):assess(*docs)


if __name__=='__main__':unittest.main()
