"""Offline editable worksheet contracts; no CSV rematching or image access."""
import csv
from copy import deepcopy
import io
from pathlib import Path
import unittest

from tools.export_owner_destination_review import csv_text, review_tables
from tools.local_destination_catalog import read_json, CatalogError

ROOT=Path(__file__).resolve().parents[1]


class OwnerDestinationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names=['production-mapped-publication-v4.review.json','location-verification.review.json',
               'destination-images.final-mapping.review.json','category-registry.review.json',
               'category-parent-mapping.proposed.review.json']
        cls.documents=[read_json(ROOT/'local_catalog'/name) for name in names]
        cls.tables=review_tables(*cls.documents)

    def test_all_rows_keep_identity_action_status_and_source_content(self):
        rows=self.tables['destinations-98.csv']; plan=self.documents[0]
        self.assertEqual([r['csv_number'] for r in rows],list(range(1,99)))
        self.assertEqual(sum(r['proposed_action']=='Update' for r in rows),28)
        self.assertEqual(sum(r['proposed_action']=='Add' for r in rows),70)
        self.assertTrue(all(r['proposed_publication_status']=='Draft' for r in rows))
        for row,source in zip(rows,plan['records']):
            self.assertEqual(row['existing_id'],source['existing_id'] or '')
            self.assertEqual(row['description'],source['proposed_values']['description'] or '')
            self.assertEqual(row['category'],source['category_label'])
            self.assertEqual(row['owner_decision'],'Pending')
        self.assertEqual([r['csv_number'] for r in rows if r['description_completeness'].startswith('MISSING')],[56,58,59,60])

    def test_numeric_and_stored_coordinates_never_become_geographic_verification(self):
        rows=self.tables['destinations-98.csv']
        self.assertEqual(sum(r['coordinate_basis'].startswith('CSV:') for r in rows),83)
        self.assertEqual([r['csv_number'] for r in rows if r['coordinate_basis'].startswith('Existing stored')],[2,10,90])
        self.assertEqual(sum(r['candidate_latitude'] is None and r['candidate_longitude'] is None for r in rows),12)
        self.assertTrue(all(r['geographic_verification']=='NOT independently verified' for r in rows))
        self.assertTrue(all(not r['recorded_verification_evidence'] and not r['owner_location_evidence'] for r in rows))

    def test_completed_images_are_dispositions_not_assignments(self):
        rows=self.tables['destinations-98.csv']
        self.assertEqual(sum(r['image_assignment_status'].startswith('Preserve') for r in rows),3)
        self.assertEqual(sum(bool(r['proposed_image_file']) for r in rows),79)
        self.assertEqual(sum(r['image_assignment_status'].startswith('Placeholder') for r in rows),16)
        for number in (56,58):
            self.assertIn('UNASSIGNED',rows[number-1]['image_assignment_status'])
            self.assertEqual(rows[number-1]['proposed_image_file'],'')

    def test_separate_decisions_and_conflict_scope_are_exact_and_pending(self):
        self.assertEqual(len(self.tables['aliases.csv']),10)
        self.assertEqual(len(self.tables['proposed-archives.csv']),7)
        conflicts=self.tables['category-conflicts.csv']
        self.assertEqual(len(conflicts),2)
        self.assertEqual({r['conflicting_normalized_key'] for r in conflicts},{'resort-swimming-pool'})
        self.assertEqual({r['csv_numbers'] for r in conflicts},{'70','72; 73'})
        self.assertEqual(len(self.tables['category-parents.csv']),73)
        self.assertTrue(all(r['owner_decision']=='Pending' for rows in self.tables.values() for r in rows))
        before=deepcopy(self.documents);review_tables(*self.documents)
        self.assertEqual(self.documents,before)

    def test_csv_quoting_preserves_commas_quotes_newlines_and_unicode_and_blocks_formulas(self):
        text='Owner note, with "quotes"\nand café text'
        parsed=list(csv.DictReader(io.StringIO(csv_text([dict(note=text,latitude=-14.2,unsafe=' =1+1')]))))[0]
        self.assertEqual(parsed['note'],text)
        self.assertEqual(parsed['latitude'],'-14.2')
        self.assertEqual(parsed['unsafe'],"' =1+1")
        for name,rows in self.tables.items():
            decoded=list(csv.DictReader(io.StringIO(csv_text(rows))))
            self.assertEqual(len(decoded),len(rows),name)
            self.assertTrue(all(None not in row for row in decoded),name)

    def test_wrong_target_or_held_image_drift_rejected_before_export(self):
        docs=deepcopy(self.documents);docs[0]['target_project_ref']='wrong'
        with self.assertRaises(CatalogError):review_tables(*docs)
        docs=deepcopy(self.documents);docs[2]['records'][55]['selected_local_candidate']={'staged_file':'wrong.jpg'}
        with self.assertRaises(CatalogError):review_tables(*docs)


if __name__=='__main__':unittest.main()
