"""Offline all-98 review, nullable Draft UI and published-only recommendation checks."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.prepare_owner_catalog98 import ROOT, OUTPUT, build, content_blockers, original_hashes
from tools.local_destination_catalog import read_json, CatalogError
from tools.prepare_current_catalog_review import validate_inventory
from destination_categories import parse_registry, CategoryConfigurationError
from places_service import PlacesService, PlacesConsistencyError
from admin_places_service import get_destination
from admin_management_service import validate_destination, DestinationValidationError
from normal_auth_coordinator import AuthenticatedContext
from recommendation_engine import rank_candidates


class Query:
    def __init__(self,rows,trace):self.rows=rows;self.trace=trace;self.filters=[];self.fields=[];self.slice=slice(None)
    def select(self,fields,*args,**kwargs):self.fields=fields.split(',');return self
    def eq(self,key,value):self.filters.append((key,value));self.trace.append((key,value));return self
    def order(self,*args,**kwargs):return self
    def range(self,a,b):self.slice=slice(a,b+1);return self
    def limit(self,n):self.slice=slice(0,n);return self
    def retry(self,value):assert value is False;return self
    def execute(self):
        rows=[r for r in self.rows if all(r[k]==v for k,v in self.filters)][self.slice]
        return SimpleNamespace(data=[{k:r[k] for k in self.fields} for r in rows])


class Owner98Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=read_json(OUTPUT/'change-set.review.json')
        cls.proposed=read_json(OUTPUT/'change-set.with-proposed-resolutions.review.json')
        cls.original=read_json(ROOT/'local_catalog/production-publication/change-set.review.json')

    def test_reconciliation_exact_98_and_final_120_counts(self):
        p=self.plan;self.assertEqual(len(p['records']),98)
        self.assertEqual(sum(r['status']=='published' for r in p['records']),65)
        self.assertEqual(sum(r['status']=='draft' for r in p['records']),33)
        self.assertEqual(sum(bool(r['existing_id']) for r in p['records']),28)
        self.assertEqual(len(p['legacy_holds']),7)
        self.assertEqual(p['counts']['conditional_final_draft'],33+7+2)
        self.assertEqual(p['counts']['conditional_final_total'],50+70)
        self.assertFalse(p['counts']['partial_import_authorized'])

    def test_seven_missing_mandatory_records_are_not_treated_as_nullable_drafts(self):
        self.assertEqual({r['csv_record'] for r in content_blockers(self.plan['records'])},{56,58,59,60,70,72,73})
        for record in self.plan['records']:
            if record['csv_record'] in (56,58,59,60):self.assertIsNone(record['values']['description'])
            if record['csv_record'] in (70,72,73):self.assertIsNone(record['values']['category'])
        self.assertEqual(content_blockers(self.proposed['records']),[])
        self.assertFalse(self.proposed['approved']);self.assertFalse(self.proposed['alias_mappings_approved'])

    def test_only_existing_supported_seven_proposals_differ(self):
        changes=[]
        for before,after in zip(self.plan['records'],self.proposed['records']):
            for key in before['values']:
                if before['values'][key]!=after['values'][key]:changes.append((before['csv_record'],key))
        self.assertEqual(changes,[(56,'description'),(58,'description'),(59,'description'),(60,'description'),(70,'category'),(72,'category'),(73,'category')])
        self.assertTrue(all(not d['approved'] for d in read_json(OUTPUT/'required-content-decisions.review.json')['decisions']))

    def test_every_existing_id_and_slug_preserved_and_no_collision(self):
        p=self.plan;baseline={r['id']:r for r in p['baseline_rows']}
        self.assertEqual(len({r['id'] for r in p['records']}),98)
        self.assertEqual(len({r['slug'] for r in p['records']}),98)
        for r in p['records']:
            if r['existing_id']:
                self.assertEqual(r['id'],r['existing_id']);self.assertEqual(r['slug'],baseline[r['id']]['slug'])
            else:self.assertNotIn(r['id'],baseline)
        self.assertEqual(sum(r['alias_confirmation_required'] for r in p['records']),10)

    def test_same_first65_values_and_21_transitions_and_images(self):
        old={r['csv_record']:r for r in self.original['records']}
        for r in self.plan['records']:
            if r['status']=='published':self.assertEqual(r['values'],old[r['csv_record']]['values'])
        self.assertEqual(self.plan['original_hold_draft'],self.original['hold_draft'])
        self.assertEqual(self.plan['images'],self.original['images'])
        self.assertEqual(len(self.plan['images']),51)
        self.assertTrue(all(r['values']['image_url'] is None for r in self.plan['records'] if r['status']=='draft' and not r['existing_id']))
        self.assertIsNone(next(r for r in self.plan['records'] if r['csv_record']==56)['values']['image_url'])

    def test_unresolved_points_are_null_pairs_without_losing_backup(self):
        for r in self.plan['records']:
            if not r['location_accepted']:
                self.assertIsNone(r['values']['latitude']);self.assertIsNone(r['values']['longitude'])
                self.assertEqual(r['status'],'draft')
        baseline={r['id']:r for r in self.plan['baseline_rows']}
        for number in (2,10):
            record=next(r for r in self.plan['records'] if r['csv_record']==number)
            self.assertIsNotNone(baseline[record['id']]['latitude'])

    def test_registry_requires_approval_and_has_all_79_keys_and_parents(self):
        doc=read_json(OUTPUT/'category-registry.review.json')
        with self.assertRaises(CategoryConfigurationError):parse_registry(doc,project_ref='brnkigrrqdrywahvcbvc')
        registry=parse_registry(doc|dict(approved=True),project_ref='brnkigrrqdrywahvcbvc')
        self.assertEqual(len(registry),79)
        self.assertTrue(all(r['values']['category'] in registry for r in self.proposed['records']))

    def test_original_package_and_generated_file_hashes_preserved(self):
        manifest=read_json(OUTPUT/'manifest.json')
        self.assertEqual(original_hashes(),manifest['preserved_original_package_sha256'])
        for e in manifest['files']:
            self.assertEqual(hashlib.sha256((OUTPUT/e['file']).read_bytes()).hexdigest(),e['sha256'])

    def test_owner_path_never_spoofs_claims_or_installs_public_admin_write_rpc(self):
        sql=(OUTPUT/'apply.review.sql').read_text(encoding='utf-8')
        self.assertIn('SECURITY INVOKER',sql)
        self.assertNotIn('set_config',sql)
        self.assertNotIn('rosago_admin_mutate_destination(',sql)
        self.assertNotIn('rosago_provider_session_current',sql)
        self.assertNotIn('CREATE FUNCTION public.',sql)
        self.assertIn("SESSION_USER<>'postgres' OR CURRENT_USER<>'postgres'",sql)
        self.assertIn('UNAPPROVED_OWNER98_INSTALL',sql)

    def runtime(self):
        registry=parse_registry(read_json(OUTPUT/'category-registry.review.json')|dict(approved=True),project_ref='brnkigrrqdrywahvcbvc')
        from contextlib import ExitStack
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('destination_categories.category_registry',return_value=registry))
        stack.enter_context(patch.dict(os.environ,{'ROSAGO_FLEXIBLE_CATALOG_ENABLED':'true'}))
        rows={r['id']:deepcopy(r)|dict(operating_days_raw=None) for r in self.plan['baseline_rows']}
        for record in self.proposed['records']:
            old=rows.get(record['id'],{})
            rows[record['id']]=old|deepcopy(record['values'])|dict(id=record['id'],slug=record['slug'],status=record['status'],
                created_at=old.get('created_at','2026-11-08T00:00:00+00:00'),updated_at='2026-11-08T01:00:00+00:00')
        for hold in self.plan['legacy_holds']:rows[hold['id']]['status']='draft'
        rows=list(rows.values());trace=[]
        client=SimpleNamespace(table=lambda _:Query(rows,trace))
        @contextmanager
        def clients():yield client
        return rows,trace,client,PlacesService(clients,tourism_metadata_enabled=True,environment_enabled=True)

    def test_normal_explore_source_and_details_exclude_every_csv_draft(self):
        rows,trace,client,service=self.runtime()
        public=service.list_published(limit=100)
        self.assertEqual(len(public),65);self.assertIn(('status','published'),trace)
        draft_ids={r['id'] for r in self.proposed['records'] if r['status']=='draft'}
        self.assertTrue(draft_ids.isdisjoint({p.id for p in public}))
        for record in self.proposed['records']:
            if record['status']=='draft':self.assertIsNone(service.get_published_by_slug(record['slug']))

    def test_recommendations_accept_expanded_categories_and_never_receive_drafts(self):
        rows,trace,client,service=self.runtime()
        places=service.list_published(limit=100)
        result=rank_candidates(dict(interests=['attraction','dining','shopping','nature','heritage','industrial','accommodation']),places)
        self.assertEqual(result.total_candidate_count,65);self.assertEqual(result.match_count,65)
        draft_ids={r['id'] for r in self.proposed['records'] if r['status']=='draft'}
        self.assertTrue(draft_ids.isdisjoint({p.place_id for p in result.ranked}))

    def test_admin_can_open_every_proposed_draft_and_forms_accept_null_optionals(self):
        rows,trace,client,service=self.runtime()
        context=AuthenticatedContext('synthetic','11111111-1111-4111-8111-111111111111','fixture@example.invalid',client,'admin')
        for r in self.proposed['records']:
            if r['status']!='draft':continue
            detail=get_destination(context,r['slug'],tourism_metadata_enabled=True,environment_enabled=True)
            self.assertEqual(detail.status,'draft');self.assertEqual(detail.name,r['values']['name'])
            values={k:'' if r['values'][k] is None else str(r['values'][k]) for k in
                ('name','category','description','address','latitude','longitude','tourism_type','tourism_category',
                 'tourism_opening_hours_raw','tourism_closing_hours_raw','tourism_hours_status')}
            parsed=validate_destination(values,tourism_enabled=True)
            self.assertEqual(parsed['category'],r['values']['category'])
            if r['values']['latitude'] is None:self.assertIsNone(parsed['latitude'])

if __name__=='__main__':unittest.main()
