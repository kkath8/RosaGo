"""Prepared batch and reserved upload/gateway boundaries, never hosted I/O."""
from copy import deepcopy
import os
from pathlib import Path
import re
import socket
import unittest
from unittest.mock import Mock,patch
from contextlib import contextmanager
from types import SimpleNamespace

from tools.local_destination_catalog import read_json,CatalogError
from tools.prepare_current_catalog_review import validate_inventory
from tools.prepare_production_publication import build
from admin_photo_service import PreparedPhoto,upload_photo,photo_object_path,PhotoValidationError,PhotoAccessError
from normal_auth_coordinator import AuthenticatedContext
from server_data_gateway import GatewayClient,GatewayDenied,GatewayUnavailable,ServerDataGateway
from tools.validate_publication_evidence import storage_status,unwrap

ROOT=Path(__file__).resolve().parents[1]


class PublicationPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs=[read_json(ROOT/'local_catalog'/name) for name in (
            'production-first-publication-batch-v2.review.json','production-destinations-owner-export.json',
            'category-registry.merged-resort.review.json','image-upload-payloads.review.json')]
        cls.docs[1]=validate_inventory(cls.docs[1])
        cls.plan,cls.registry=build(*cls.docs)

    def test_65_batch_exact_ids_status_holds_and_no_unapproved_archives(self):
        plan=self.plan
        self.assertEqual(len(plan['records']),65);self.assertEqual(len(plan['hold_draft']),21)
        self.assertEqual(sum(bool(r['existing_id']) for r in plan['records']),14)
        self.assertEqual(len(plan['pending_new_records_not_inserted']),19)
        self.assertTrue(all(r['proposed_status']=='draft' for r in plan['hold_draft']))
        self.assertEqual(plan['counts']['archives'],0);self.assertEqual(plan['counts']['proposed_final_total'],101)
        self.assertEqual(len(self.registry['categories']),59);self.assertFalse(self.registry['approved'])
        self.assertFalse(plan['executable'])

    def test_51_reserved_images_match_approved_payload_evidence_and_never_replace_old_objects(self):
        images=self.plan['images']
        self.assertEqual(len(images),51);self.assertEqual(len({r['object_name'] for r in images}),51)
        self.assertTrue(all(re.fullmatch(r'destinations/[0-9a-f]{32}\.(jpg|png|webp)',r['object_name']) for r in images))
        self.assertTrue(all(not r['upsert'] and not r['uploaded'] for r in images))
        covers=[r for r in self.plan['records'] if r['csv_record'] in (1,21,52)]
        original={r['id']:r for r in self.plan['baseline_rows']}
        self.assertTrue(all(r['values']['image_url']==original[r['existing_id']]['image_url'] for r in covers))
        self.assertEqual(sum(r['values']['image_url'] is None for r in self.plan['records']),11)

    def test_wrong_target_pending_record_and_payload_drift_are_rejected(self):
        docs=deepcopy(self.docs);docs[0]['target_project_ref']='wrong'
        with self.assertRaises(CatalogError):build(*docs)
        docs=deepcopy(self.docs);docs[0]['records'][0]['research_location_accepted']=False
        with self.assertRaises(CatalogError):build(*docs)
        docs=deepcopy(self.docs);candidate=next(r for r in docs[0]['records'] if r['first_content_batch_candidate'] and r['image_final_mapping']['selected_local_candidate'])
        candidate['image_final_mapping']['selected_local_candidate']['staged_sha256']='changed'
        with self.assertRaises(CatalogError):build(*docs)


class ReservedUploadTests(unittest.TestCase):
    def test_reserved_identity_cannot_inject_paths_or_remove_no_upsert_rule(self):
        for value in ('../secret','a'*31,'A'*32,'a'*32+'.jpg',1):
            with self.subTest(value=value),self.assertRaises(PhotoValidationError):photo_object_path('jpg',value)
        self.assertEqual(photo_object_path('jpg','a'*32),'destinations/'+'a'*32+'.jpg')
        self.assertRegex(photo_object_path('png'),r'^destinations/[0-9a-f]{32}\.png$')

    def test_reserved_upload_keeps_admin_authorization_and_existing_storage_transport(self):
        context=AuthenticatedContext('synthetic-handle','synthetic-admin','fixture@example.invalid',object(),'admin')
        prepared=PreparedPhoto(b'synthetic-payload','image/jpeg','jpg')
        storage=Mock();http=Mock();http.return_value.__enter__=Mock(return_value=object());http.return_value.__exit__=Mock(return_value=False)
        with patch.dict(os.environ,{'SUPABASE_URL':'https://fixture.supabase.co','SUPABASE_STORAGE_BUCKET':'destination-images','SUPABASE_STORAGE_SECRET_KEY':'sb_secret_synthetic_only'}),\
                patch('admin_photo_service.is_current_admin',return_value=True),patch('admin_photo_service._http_client',http),patch('admin_photo_service.SyncStorageClient',return_value=storage):
            url=upload_photo(context,prepared,planned_object_id='a'*32)
        args=storage.from_.return_value.upload.call_args.args
        self.assertEqual(args[0],'destinations/'+'a'*32+'.jpg');self.assertEqual(args[1],prepared.content)
        self.assertEqual(args[2]['upsert'],'false');self.assertTrue(url.endswith(args[0]))
        with patch('admin_photo_service.is_current_admin',return_value=False),patch('admin_photo_service._http_client') as client:
            with self.assertRaises(PhotoAccessError):upload_photo(context,prepared,planned_object_id='a'*32)
            client.assert_not_called()


class GatewayPublicationContractTests(unittest.TestCase):
    def test_unknown_provider_denies_access_without_falsely_recording_revocation(self):
        class Connection:
            def __init__(self,state):self.state=state;self.data_queries=0
            @contextmanager
            def transaction(self):yield
            def execute(self,statement,params=None):
                if isinstance(statement,str) and 'rolsuper' in statement:
                    return SimpleNamespace(fetchone=lambda:dict(rolsuper=False,rolcreatedb=False,rolcreaterole=False,rolinherit=False,rolreplication=False,rolbypassrls=False))
                if isinstance(statement,str) and 'rosago_provider_session_current' in statement:
                    return SimpleNamespace(fetchone=lambda:dict(current=self.state))
                if statement=='fixture-data-query':self.data_queries+=1
                return SimpleNamespace(fetchall=lambda:[dict(data={'synthetic':True})])
        class Pool:
            def __init__(self,connection):self.selected=connection
            @contextmanager
            def connection(self,**kwargs):yield self.selected
        for state in (None,'true',1,False,True):
            connection=Connection(state);gateway=ServerDataGateway(Pool(connection),{'user':object(),'admin':object()})
            query=SimpleNamespace(client=SimpleNamespace(realm='user',handle='fixture'),compile=lambda:('fixture-data-query',[],False))
            with patch.object(gateway,'claims',return_value={'sub':'synthetic'}),patch('server_data_gateway.ExternalPgModel') as model:
                if state is True:
                    self.assertEqual(gateway.execute(query).data,{'synthetic':True});self.assertEqual(connection.data_queries,1)
                    model.assert_not_called()
                else:
                    with self.assertRaises(GatewayDenied if state is False else GatewayUnavailable):gateway.execute(query)
                    self.assertEqual(connection.data_queries,0)
                    if state is False:model.return_value.revoke.assert_called_once_with('fixture')
                    else:model.assert_not_called()

    def test_fixed_apply_and_hold_rpcs_accept_no_injected_actor_or_plan(self):
        client=GatewayClient(object(),'admin','synthetic-handle')
        for name in ('rosago_admin_apply_first_catalog_batch','rosago_admin_hold_first_catalog_batch'):
            _,params,many=client.rpc(name,{}).compile();self.assertEqual(params,[]);self.assertFalse(many)
            for supplied in ({'p_actor_id':'different'},{'p_plan':{}},{'ignore_security':True}):
                with self.assertRaises(GatewayDenied):client.rpc(name,supplied).compile()

    def test_verification_rpc_requires_exact_caller_bound_contract(self):
        client=GatewayClient(object(),'admin','synthetic-handle')
        values=dict(p_slug='fixture',p_expected_updated_at='2026-01-01T00:00:00Z',p_values={},p_evidence_ref='Owner researched CSV')
        _,params,many=client.rpc('rosago_admin_verify_destination_location',values).compile()
        self.assertEqual(len(params),4);self.assertFalse(many)
        with self.assertRaises(GatewayDenied):client.rpc('rosago_admin_verify_destination_location',values|{'p_actor_id':'different'}).compile()


class PublicationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=ROOT/'local_catalog'
        cls.storage=unwrap(read_json(base/'production-storage-latest-preflight.json'),'publication_storage_preflight_json')
        cls.permissions=unwrap(read_json(base/'production-storage-permissions-latest.json'),'publication_storage_permissions_json')
        cls.plan=read_json(base/'production-publication/change-set.review.json')
        cls.covers=[r['values']['image_url'] for r in cls.plan['records'] if r['csv_record'] in (1,21,52)]

    def test_complete_owner_wrappers_validate_without_assuming_upload_approval(self):
        status=storage_status(self.storage,self.permissions,self.plan['images'],self.covers)
        self.assertTrue(status['storage_rls_enabled']);self.assertFalse(status['upload_approved'])
        self.assertEqual(status['existing_objects'],5);self.assertEqual(status['reserved_collisions'],0)
        with self.assertRaises(CatalogError):unwrap([{'destination_inventory_json':'{}'}],'publication_storage_preflight_json')

    def test_disabled_rls_bypass_role_or_new_storage_policy_stops_qualification(self):
        p=deepcopy(self.permissions);p['tables'][0]['rls_enabled']=False
        with self.assertRaises(CatalogError):storage_status(self.storage,p,self.plan['images'],self.covers)
        p=deepcopy(self.permissions);next(r for r in p['api_roles'] if r['role']=='authenticated')['bypass_rls']=True
        with self.assertRaises(CatalogError):storage_status(self.storage,p,self.plan['images'],self.covers)
        s=deepcopy(self.storage);s['policies']=[{'unexpected':'write policy'}]
        with self.assertRaises(CatalogError):storage_status(s,self.permissions,self.plan['images'],self.covers)

    def test_key_collision_bucket_limit_or_target_drift_rejects_upload_plan(self):
        for field,value in [('owner_selected_project_ref','wrong'),('bucket',self.storage['bucket']|dict(file_size_limit=1))]:
            s=deepcopy(self.storage);s[field]=value
            with self.subTest(field=field),self.assertRaises(CatalogError):storage_status(s,self.permissions,self.plan['images'],self.covers)
        s=deepcopy(self.storage);s['objects'].append({'name':self.plan['images'][0]['object_name']})
        with self.assertRaises(CatalogError):storage_status(s,self.permissions,self.plan['images'],self.covers)


if __name__=='__main__':unittest.main()
