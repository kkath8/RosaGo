"""Historical candidate semantics only: no project connection or SQL execution."""
from copy import deepcopy
import unittest

from tools.prepare_publication_review import compare_candidates,proposed_categories,historical_rows,TARGET
from tools.local_destination_catalog import CatalogError,PROJECT


def old(index,name,status='published'):
    return dict(id=f'11111111-1111-4111-8111-{index:012d}',name=name,slug=f'fixture-{index}',status=status,category='nature')


def source(*names):
    return dict(review_only=True,record_count=len(names),source_categories={'New Flexible Category':2},
        records=[dict(record_number=i,csv_line_start=i+1,name=name,errors=[]) for i,name in enumerate(names,1)])


class PublicationReviewTests(unittest.TestCase):
    def test_exact_match_is_historical_candidate_and_never_a_verified_write(self):
        result=compare_candidates(source('SYNTHETIC GARDEN'),[old(1,'Synthetic Garden')])
        self.assertEqual(result['historical_candidate_counts']['exact_name_historical_update_candidate'],1)
        self.assertIsNone(result['confirmed_update_count'])
        self.assertEqual(result['records'][0]['current_classification'],'Ambiguous - manual review')
        self.assertFalse(result['records'][0]['live_identity_verified'])
        self.assertFalse(result['executable'])

    def test_parenthetical_alias_is_manual_and_unknown_name_is_not_new(self):
        result=compare_candidates(source('Garden (Visitor Site)','Distinctly Unrelated XYZ'),[old(1,'Garden')])
        self.assertEqual(result['records'][0]['historical_comparison'],'historical_alias_review')
        self.assertEqual(result['records'][1]['historical_comparison'],'unmatched_not_confirmed_new')
        self.assertIsNone(result['confirmed_new_count'])
        self.assertEqual(result['automatic_creates'],[])

    def test_invalid_source_cannot_become_publication_ready_after_an_exact_match(self):
        review=source('Garden');review['records'][0]['errors']=['missing_required:Description']
        result=compare_candidates(review,[old(1,'Garden')])
        self.assertEqual(result['records'][0]['current_classification'],'Invalid - correction required')
        self.assertEqual(result['ready_for_publication_count'],0)

    def test_missing_and_previously_archived_records_are_kept_separate_without_actions(self):
        rows=[old(1,'Existing'),old(2,'Missing other venue'),old(3,'Previously inactive fixture','archived')]
        original=deepcopy(rows)
        result=compare_candidates(source('Existing'),rows)
        self.assertEqual([r['id'] for r in result['historical_missing_from_csv_review']],[rows[1]['id']])
        self.assertEqual([r['id'] for r in result['historical_already_archived_without_candidate']],[rows[2]['id']])
        self.assertEqual(result['automatic_archives'],[]);self.assertEqual(result['automatic_deletes'],[])
        self.assertEqual(rows,original)

    def test_category_proposals_are_dynamic_not_forced_into_legacy_seven(self):
        review=source('Fixture')
        review['source_categories']={f'Custom Category {index}':1 for index in range(30)}
        proposed=proposed_categories(review)
        self.assertEqual(len(proposed),30)
        self.assertTrue(all(r['owner_review_required'] and r['parent_key'] is None for r in proposed))

    def test_category_collisions_require_review_and_evaluation_pin_remains_unchanged(self):
        review=source('Fixture');review['source_categories']={'Category A':1,'CATEGORY-A':1}
        proposed=proposed_categories(review)
        self.assertEqual(len(proposed),2)
        self.assertTrue(all(r['proposed_key'] is None and r['collision_candidate_key']=='category-a' for r in proposed))
        self.assertEqual(PROJECT,'jfaufpfzfhysqkhcdsrs')
        self.assertNotEqual(PROJECT,TARGET)

    def test_multiple_source_candidates_for_one_uuid_require_manual_resolution(self):
        result=compare_candidates(source('Garden (Visitor Site)','Garden (Public Park)'),[old(1,'Garden')])
        self.assertEqual(result['candidate_id_conflicts'][0]['csv_records'],[1,2])
        self.assertEqual(result['automatic_updates'],[])

    def test_historical_index_parser_retains_identifiers_and_requires_target(self):
        text=TARGET+'\n| 11111111-1111-4111-8111-000000000001 | Garden | garden | draft | nature |'
        rows=historical_rows(text)
        self.assertEqual(rows[0]['slug'],'garden')
        with self.assertRaises(CatalogError):historical_rows(text.replace(TARGET,'another-project'))


if __name__=='__main__':unittest.main()
