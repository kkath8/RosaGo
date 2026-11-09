"""Validate owner-operated exports only; no credentials or hosted connections."""
import hashlib
import json
from pathlib import Path

from tools.local_destination_catalog import read_json,require,timestamp
from tools.prepare_current_catalog_review import validate_inventory
from tools.prepare_catalog_from_preflight import validate
from tools.prepare_publication_decision_checklist import ROOT,TARGET


def unwrap(document,key):
    if isinstance(document,list):
        require(len(document)==1 and isinstance(document[0],dict) and set(document[0])=={key},'Wrong or incomplete export wrapper.')
        document=document[0][key]
    if isinstance(document,str):document=json.loads(document)
    require(type(document) is dict,'Export must contain a JSON object.')
    return document


def storage_status(document,permissions,images,preserved_covers):
    document=unwrap(document,'publication_storage_preflight_json')
    permissions=unwrap(permissions,'publication_storage_permissions_json')
    require(document.get('export_format')=='rosago_publication_storage_preflight_v1','Wrong Storage format.')
    for item in (document,permissions):
        require(item.get('owner_selected_project_ref')==TARGET and item.get('transaction_read_only')=='on','Storage target/read-only mismatch.')
    require(document.get('database_role')=='postgres' and document.get('project_identity_requires_dashboard_confirmation') is True,'Owner Storage attestation missing.')
    timestamp(document['exported_at'])
    require(set(document)>= {'bucket','objects','policies','identity_counts','membership_identity_digest'},'Incomplete Storage evidence.')
    bucket=document['bucket'];require(bucket and bucket['id']=='destination-images' and bucket['public'] is True,'Existing public destination bucket required.')
    require(type(document['objects']) is list and (document['policies'] is None or type(document['policies']) is list),'Incomplete object/policy evidence.')
    names=[r['name'] for r in document['objects']];require(len(names)==len(set(names)),'Duplicate Storage names.')
    require(all(r['object_name'] not in names for r in images),'Reserved upload key already exists; reconcile before any retry.')
    for image in images:
        require(bucket['file_size_limit'] is None or image['bytes']<=bucket['file_size_limit'],'Upload exceeds existing bucket limit.')
        require(bucket['allowed_mime_types'] is None or image['mime_type'] in bucket['allowed_mime_types'],'Upload MIME not permitted by existing bucket.')
    require(all(url.split('/destination-images/',1)[1] in names for url in preserved_covers),'Existing cover absent from Storage inventory.')
    tables={r['table']:r for r in permissions['tables']};roles={r['role']:r for r in permissions['api_roles']}
    require(set(tables)=={'objects','buckets'} and all(r['rls_enabled'] is True for r in tables.values()),'Storage RLS must be enabled.')
    require(all(k in roles and roles[k]['superuser'] is False and roles[k]['bypass_rls'] is False for k in ('anon','authenticated')),'Ordinary API role can bypass RLS.')
    require(not document['policies'],'Unexpected Storage policy: review before claiming ordinary writes denied.')
    require(type(document['identity_counts']) is dict and all(type(document['identity_counts'].get(k)) is int for k in ('auth_users','profiles','admin_memberships')),'Identity count checkpoint missing.')
    return dict(target_project_ref=TARGET,bucket_compatible=True,existing_objects=len(names),reserved_collisions=0,
        storage_rls_enabled=True,ordinary_api_writes_denied_by_no_allow_policies=True,
        service_role_bypass=roles.get('service_role',{}).get('bypass_rls'),
        account_counts=document['identity_counts'],membership_identity_digest=document['membership_identity_digest'],
        upload_approved=False,note='Public bucket downloads remain public. Privileged server-only Storage secret is required; credentials and live uploads were not tested.')


def main():
    b=ROOT/'local_catalog';package=b/'production-publication'
    names=['production-destinations-latest-owner-export.json','production-catalog-latest-schema-preflight-corrected.json',
           'production-storage-latest-preflight.json','production-storage-permissions-latest.json']
    latest=validate_inventory(read_json(b/names[0]));old=validate_inventory(read_json(b/'production-destinations-owner-export.json'))
    require({r['id']:r for r in latest['rows']}=={r['id']:r for r in old['rows']},'Destination drift requires a new reviewed change set.')
    schema=validate(read_json(b/names[1]));previous=validate(read_json(b/'production-catalog-schema-preflight.json'))
    differences=[]
    for key in ('functions','columns','constraints','policies','table_grants','indexes','table_security','migration_history_relation_present'):
        x=previous[key];y=schema[key]
        if isinstance(x,list):x=sorted(x,key=lambda r:json.dumps(r,sort_keys=True));y=sorted(y,key=lambda r:json.dumps(r,sort_keys=True))
        if x!=y:differences.append(key)
    require(not differences,'Schema drift requires migration requalification: '+','.join(differences))
    plan=read_json(package/'change-set.review.json')
    covers=[r['values']['image_url'] for r in plan['records'] if r['csv_record'] in (1,21,52)]
    status=storage_status(read_json(b/names[2]),read_json(b/names[3]),plan['images'],covers)
    result=dict(inventory_validated=True,destination_drift=False,schema_validated=True,schema_drift=False,
        owner_selected_project_ref=TARGET,identity_basis='Owner-confirmed Dashboard selection; SQL literals are not independent server identity proof.',
        existing_status_counts=latest['status_counts'],schema_functions=len(schema['functions']),
        schema_columns=len(schema['columns']),schema_constraints=len(schema['constraints']),schema_policies=len(schema['policies']),
        production_provider_helper_present=any('rosago_provider_session_current(' in r['identity'] for r in schema['functions']),
        migration_history_relation_present=schema['migration_history_relation_present'],storage=status,
        input_sha256={n:hashlib.sha256((b/n).read_bytes()).hexdigest() for n in names},
        security_blocker_resolved=False,hosted_application_qualified=False)
    # Derived assessment only; raw exports and approved/reviewed SQL never change.
    (package/'fresh-evidence.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('inventory_validated','destination_drift','schema_validated','schema_drift','production_provider_helper_present','storage')},indent=2))


if __name__=='__main__':main()
