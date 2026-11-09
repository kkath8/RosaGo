"""Synthetic cross-artifact drift and approval-boundary checks, no image reads."""
from copy import deepcopy
import unittest

from tools.local_destination_catalog import CatalogError
from tools.prepare_publication_decision_checklist import build_checklist, TARGET
from tests.test_mapped_publication import fixture, approved
from tools.prepare_mapped_publication import disposition


def documents():
    plan, _, evidence = fixture()
    template = plan['records'][0]; location = evidence['records'][0]
    plan['records'] = []; evidence['records'] = []; photos = []
    missing = {65,66,67,70,71,72,73,74,75,76,77,78,80,81}
    for number in range(1,99):
        row = deepcopy(template); loc = deepcopy(location)
        row.update(csv_record=number, name=f'Synthetic {number}', existing_id=f'synthetic-{number}')
        loc.update(csv_record=number, name=row['name'], existing_id=row['existing_id'])
        hosted = 'https://fixture.invalid/cover.jpg' if number in (1,21,52) else None
        row['original_row']['image_url'] = hosted
        row = disposition(row, loc)
        plan['records'].append(row); evidence['records'].append(loc)
        action = ('preserve_existing_hosted_image' if hosted else
            'placeholder_no_matching_photo' if number in missing else
            'placeholder_held_court' if number in (56,58) else 'proposed_attachment_requires_approval')
        photos.append(dict(csv_record=number, name=row['name'], existing_id=row['existing_id'],
            selected_hosted_image_url=hosted, proposed_database_image_url=hosted, action=action,
            approved_for_upload=False, approved_for_assignment=False, publishing_authorized=False,
            selected_local_candidate=None if action.startswith('placeholder') else {'file':'synthetic'}))
    plan.update(target_project_ref=TARGET, executable=False, hosted_writes=0, record_ready_for_publication_count=0)
    evidence['target_project_ref']=TARGET
    return [plan, evidence, dict(target_project_ref=TARGET,records=photos),
        dict(project_ref=TARGET,categories=[]), dict(source_csv_sha256=plan['source_csv_sha256'],categories=[])]


class PublicationDecisionChecklistTests(unittest.TestCase):
    def test_complete_inventory_preserves_images_and_never_authorizes_execution(self):
        docs=documents(); before=deepcopy(docs); result=build_checklist(*docs)
        self.assertEqual(result['counts']['held_draft'],98)
        self.assertEqual(result['image_counts'],dict(preserved_hosted=3,proposed_attachments=79,placeholders=16))
        self.assertFalse(result['executable']); self.assertFalse(result['security_and_migration_approval'])
        self.assertEqual(docs,before)

    def test_target_source_and_duplicate_or_missing_inventory_are_rejected(self):
        for index,key in [(0,'target_project_ref'),(1,'source_csv_sha256'),(2,'target_project_ref'),(3,'project_ref')]:
            docs=documents(); docs[index][key]='wrong'
            with self.subTest(index=index),self.assertRaises(CatalogError):build_checklist(*docs)
        for index in (0,1,2):
            docs=documents();docs[index]['records'][-1]=deepcopy(docs[index]['records'][0])
            with self.subTest(inventory=index),self.assertRaises(CatalogError):build_checklist(*docs)

    def test_image_identity_replacement_approval_or_court_assignment_drift_stops_review(self):
        for field,value in [('name','different'),('proposed_database_image_url',None),
                            ('approved_for_upload',True)]:
            docs=documents();docs[2]['records'][0][field]=value
            with self.subTest(field=field),self.assertRaises(CatalogError):build_checklist(*docs)
        docs=documents();docs[2]['records'][55]['selected_local_candidate']={'file':'wrong-court'}
        with self.assertRaises(CatalogError):build_checklist(*docs)

    def test_stale_location_evidence_requires_regeneration(self):
        docs=documents();docs[1]['records'][0]=approved(docs[1]['records'][0])
        with self.assertRaises(CatalogError):build_checklist(*docs)

    def test_ready_record_never_authorizes_database_or_image_operations(self):
        docs=documents();docs[1]['records'][0]=approved(docs[1]['records'][0])
        docs[0]['records'][0]=disposition(docs[0]['records'][0],docs[1]['records'][0])
        docs[0]['record_ready_for_publication_count']=1
        result=build_checklist(*docs)
        self.assertEqual(result['counts']['publication_record_ready'],1)
        self.assertFalse(result['executable']);self.assertEqual(result['hosted_writes'],0)


if __name__=='__main__':unittest.main()
