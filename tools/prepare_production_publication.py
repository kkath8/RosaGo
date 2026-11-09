"""Build one reviewable first-65 package. No image processing or hosted I/O."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid5,NAMESPACE_URL

from tools.local_destination_catalog import read_json,require,write_new
from tools.prepare_current_catalog_review import validate_inventory,SOURCE_HASH
from tools.prepare_publication_decision_checklist import ROOT,TARGET

FIELDS=('name','category','description','address','latitude','longitude','image_url','environment',
    'tourism_type','tourism_category','tourism_opening_hours_raw','tourism_closing_hours_raw',
    'tourism_hours_status','tourism_source','tourism_source_row','operating_days_raw')


def literal(value):return "'"+json.dumps(value,ensure_ascii=False,separators=(',',':')).replace("'","''")+"'::jsonb"


def build(batch,inventory,registry,payloads):
    require(batch['target_project_ref']==inventory['owner_selected_project_ref']==registry['project_ref']==TARGET,'Publication target mismatch.')
    require(inventory['row_count']==50 and inventory['status_counts']==dict(published=35,draft=2,archived=13),'Baseline changed; regenerate the reviewed change set.')
    source_rows=[r for r in batch['records'] if r['first_content_batch_candidate']]
    require(len(source_rows)==65,'First batch must contain exactly 65 records.')
    payload_by_path={p['staged_file']:p for p in payloads['payloads']}
    uploads=[];records=[]
    for row in source_rows:
        require(row['research_location_accepted'] and not row['remaining_record_decisions'],'Unresolved destination in first batch.')
        values={k:deepcopy(row['proposed_values'].get(k)) for k in FIELDS}
        image=row['image_final_mapping'];candidate=image['selected_local_candidate']
        if image['action']=='proposed_attachment_requires_approval':
            proof=payload_by_path[candidate['staged_file']]
            require(candidate['staged_sha256']==proof['staged_input_sha256'],'Image payload binding changed.')
            ext=Path(candidate['staged_file']).suffix[1:]
            key='destinations/'+uuid5(NAMESPACE_URL,'rosago:first65:'+str(row['csv_record'])+':'+proof['expected_upload_content_sha256']).hex+'.'+ext
            values['image_url']=f'https://{TARGET}.supabase.co/storage/v1/object/public/destination-images/{key}'
            uploads.append(dict(csv_record=row['csv_record'],name=row['name'],bucket_id='destination-images',
                object_name=key,planned_object_id=Path(key).stem,public_url=values['image_url'],
                staged_file=candidate['staged_file'],staged_sha256=candidate['staged_sha256'],
                expected_upload_sha256=proof['expected_upload_content_sha256'],bytes=proof['validated_upload_bytes'],
                mime_type=proof['mime_type'],upsert=False,approved=False,uploaded=False))
        else:
            require(values['image_url']==image['selected_hosted_image_url'],'Hosted cover preservation changed.')
        records.append(dict(csv_record=row['csv_record'],name=row['name'],existing_id=row['existing_id'],
            existing_slug=row['existing_slug'],expected_updated_at=row['expected_updated_at'],values=values,
            identity_policy='Preserve existing UUID/slug' if row['existing_id'] else 'Database-generated UUID and destination-* slug, captured in receipt'))
    held=[dict(id=r['id'],slug=next(x['slug'] for x in inventory['rows'] if x['id']==r['id']),
        name=r['name'],expected_updated_at=r['expected_updated_at'],proposed_status='draft')
        for r in batch['existing_published_csv_records_outside_first_batch']]
    held += [dict(id=r['id'],slug=r['slug'],name=r['name'],expected_updated_at=r['expected_updated_at'],
                  proposed_status='draft',archive_decision_deferred=True) for r in batch['proposed_archives']]
    require(len(held)==21 and len({r['id'] for r in held})==21,'Held-record inventory mismatch.')
    wanted={r['values']['category'] for r in records}|{'attraction','dining','shopping','nature','heritage','industrial','accommodation'}
    runtime_registry=dict(schema_version=1,project_ref=TARGET,approved=False,
        categories=[deepcopy(r) for r in registry['categories'] if r['key'] in wanted])
    require(len(runtime_registry['categories'])==59,'First-batch category scope changed.')
    result=dict(review_only=True,executable=False,approved=False,target_project_ref=TARGET,
        source_csv_sha256=SOURCE_HASH,
        records=records,hold_draft=held,baseline_rows=inventory['rows'],images=uploads,
        categories=runtime_registry['categories'],
        counts=dict(updates=14,adds=51,existing_published_to_draft=21,archives=0,deletes=0,
            image_uploads=51,preserved_hosted_covers=3,first_batch_placeholders=11,
            proposed_final_total=101,proposed_final_published=65,proposed_final_draft=23,proposed_final_archived=13),
        pending_new_records_not_inserted=[dict(csv_record=r['csv_record'],name=r['name'],status='local Draft hold')
            for r in batch['records'] if not r['first_content_batch_candidate'] and not r['existing_id']],
        note='Conservative first cutover: 7 archive proposals become Draft holds only. All 33 pending CSV destinations remain unpublished; 14 existing records become Draft, 19 uncreated records stay local. No account/member/trip changes.')
    require(len(result['pending_new_records_not_inserted'])==19,'Pending-new inventory mismatch.')
    digest=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    result['batch_id']='csv98-first65-'+digest[:20];result['plan_sha256']=digest
    return result,runtime_registry


def prepare_sql(plan,guard):
    start=guard.index('ALTER TABLE public.places ADD CONSTRAINT places_verified_location_before_publication')
    end=guard.index('CREATE FUNCTION public.rosago_admin_verify_destination_location(')
    policies=guard[start:end]
    preparation=guard[:start]+guard[end:]
    preparation=re.sub(r'DO \$gate\$.*?\$gate\$;',"DO $release_gate$ BEGIN RAISE EXCEPTION 'UNQUALIFIED_RELEASE: security and fresh production evidence required'; END $release_gate$;",preparation,count=1,flags=re.S)
    receipt_table="""
CREATE TABLE rosago_catalog_private.publication_batches(
 batch_id text PRIMARY KEY,plan_sha256 text NOT NULL,applied_by uuid NOT NULL,
 applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),receipt jsonb NOT NULL,
 held_at timestamptz,held_by uuid);
ALTER TABLE rosago_catalog_private.publication_batches ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON rosago_catalog_private.publication_batches FROM PUBLIC,anon,authenticated,service_role;
"""
    function=r"""
CREATE FUNCTION public.rosago_admin_apply_first_catalog_batch() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $batch$
DECLARE
 plan jsonb := @PLAN@;
 item jsonb; old jsonb; actual public.places%ROWTYPE; result jsonb;
 receipts jsonb := '[]'::jsonb; payload jsonb; returned_slug text;
BEGIN
 IF pg_catalog.to_regprocedure('public.rosago_provider_session_current()') IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Provider authority unavailable';
 END IF;
 IF public.rosago_provider_session_current() IS NOT TRUE THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Current provider authority required';
 END IF;
 PERFORM m.user_id FROM public.admin_memberships m WHERE m.user_id=(SELECT auth.uid()) FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Admin access required'; END IF;
 LOCK TABLE public.places IN SHARE ROW EXCLUSIVE MODE;
 IF EXISTS(SELECT 1 FROM rosago_catalog_private.publication_batches WHERE batch_id=plan->>'batch_id') THEN
  RAISE EXCEPTION 'Batch already recorded: inspect receipt, never rerun';
 END IF;
 IF (SELECT count(*) FROM public.places)<>50 THEN RAISE EXCEPTION 'Catalog inventory drift'; END IF;
 FOR old IN SELECT value FROM pg_catalog.jsonb_array_elements(plan->'baseline_rows') LOOP
  SELECT * INTO STRICT actual FROM public.places WHERE id=(old->>'id')::uuid FOR UPDATE;
  IF actual.updated_at<>(old->>'updated_at')::timestamptz OR actual.created_at<>(old->>'created_at')::timestamptz
   OR (pg_catalog.to_jsonb(actual)-ARRAY['updated_at','created_at','operating_days_raw'])<>(old-ARRAY['updated_at','created_at'])
   OR actual.operating_days_raw IS NOT NULL THEN RAISE EXCEPTION 'Catalog row drift'; END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(plan->'categories') c
   WHERE NOT EXISTS(SELECT 1 FROM public.destination_categories d WHERE d.key=c->>'key'
     AND d.label=c->>'label' AND d.parent_key IS NOT DISTINCT FROM c->>'parent_key'))
   OR (SELECT count(*) FROM public.destination_categories)<>59 THEN RAISE EXCEPTION 'Registry parity mismatch'; END IF;
 IF NOT EXISTS(SELECT 1 FROM storage.buckets WHERE id='destination-images' AND public IS TRUE) THEN
  RAISE EXCEPTION 'Existing public image bucket required'; END IF;
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(plan->'images') LOOP
  IF NOT EXISTS(SELECT 1 FROM storage.objects o WHERE o.bucket_id='destination-images' AND o.name=item->>'object_name'
    AND o.metadata->>'mimetype'=item->>'mime_type' AND (o.metadata->>'size')::bigint=(item->>'bytes')::bigint) THEN
   RAISE EXCEPTION 'Approved upload receipt/object missing'; END IF;
 END LOOP;
 -- Policy/CHECK installation and every status/row change commit together.
 @POLICIES@
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(plan->'hold_draft') LOOP
  PERFORM public.rosago_admin_mutate_destination('draft',item->>'slug',(item->>'expected_updated_at')::timestamptz,'{}'::jsonb);
 END LOOP;
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(plan->'records') LOOP
  payload=item->'values';
  IF item->>'existing_id' IS NOT NULL THEN
   PERFORM public.rosago_admin_mutate_destination('draft',item->>'existing_slug',(item->>'expected_updated_at')::timestamptz,'{}'::jsonb);
   SELECT * INTO STRICT actual FROM public.places WHERE id=(item->>'existing_id')::uuid;
   result=public.rosago_admin_mutate_destination('edit',actual.slug,actual.updated_at,payload);
  ELSE
   result=public.rosago_admin_mutate_destination('create',NULL,NULL,payload);
  END IF;
  returned_slug=result->>'slug';
  SELECT * INTO STRICT actual FROM public.places WHERE slug=returned_slug;
  IF item->>'existing_id' IS NOT NULL AND (actual.id::text<>item->>'existing_id' OR actual.slug<>item->>'existing_slug') THEN
   RAISE EXCEPTION 'Existing identity changed'; END IF;
  result=public.rosago_admin_verify_destination_location(actual.slug,actual.updated_at,
    pg_catalog.jsonb_build_object('name',actual.name,'category',actual.category,'description',actual.description,
      'address',actual.address,'latitude',actual.latitude,'longitude',actual.longitude),
    'Owner-confirmed researched CSV; record '||(item->>'csv_record')||'; batch '||(plan->>'batch_id'));
  SELECT * INTO STRICT actual FROM public.places WHERE slug=returned_slug;
  PERFORM public.rosago_admin_mutate_destination('publish',actual.slug,actual.updated_at,'{}'::jsonb);
  SELECT * INTO STRICT actual FROM public.places WHERE slug=returned_slug;
  receipts=receipts||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('csv_record',item->'csv_record',
    'id',actual.id,'slug',actual.slug,'updated_at',actual.updated_at,'image_url',actual.image_url));
 END LOOP;
 ALTER TABLE public.places VALIDATE CONSTRAINT places_verified_location_before_publication;
 IF (SELECT count(*) FROM public.places)<>101 OR (SELECT count(*) FROM public.places WHERE status='published')<>65
  OR (SELECT count(*) FROM public.places WHERE status='draft')<>23 OR (SELECT count(*) FROM public.places WHERE status='archived')<>13 THEN
  RAISE EXCEPTION 'Final catalog counts differ'; END IF;
 INSERT INTO rosago_catalog_private.publication_batches(batch_id,plan_sha256,applied_by,receipt)
 VALUES(plan->>'batch_id',plan->>'plan_sha256',(SELECT auth.uid()),receipts);
 RETURN pg_catalog.jsonb_build_object('batch_id',plan->>'batch_id','published',65,'draft',23,'archived',13,'records',receipts);
END $batch$;
REVOKE ALL ON FUNCTION public.rosago_admin_apply_first_catalog_batch() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.rosago_admin_apply_first_catalog_batch() TO authenticated;
""".replace('@PLAN@',literal(plan)).replace('@POLICIES@',policies)
    hold=r"""
CREATE FUNCTION public.rosago_admin_hold_first_catalog_batch() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $hold$
DECLARE saved rosago_catalog_private.publication_batches%ROWTYPE; item jsonb; destination public.places%ROWTYPE;
BEGIN
 IF pg_catalog.to_regprocedure('public.rosago_provider_session_current()') IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Provider authority unavailable'; END IF;
 IF public.rosago_provider_session_current() IS NOT TRUE THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Current provider authority required'; END IF;
 PERFORM m.user_id FROM public.admin_memberships m WHERE m.user_id=(SELECT auth.uid()) FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Admin access required'; END IF;
 LOCK TABLE public.places IN SHARE ROW EXCLUSIVE MODE;
 SELECT * INTO STRICT saved FROM rosago_catalog_private.publication_batches WHERE batch_id=@BATCH_ID@ FOR UPDATE;
 IF saved.held_at IS NOT NULL THEN RAISE EXCEPTION 'Batch already held; inspect receipt'; END IF;
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(saved.receipt) LOOP
  SELECT * INTO STRICT destination FROM public.places WHERE id=(item->>'id')::uuid FOR UPDATE;
  IF destination.slug<>item->>'slug' OR destination.updated_at<>(item->>'updated_at')::timestamptz OR destination.status<>'published' THEN
   RAISE EXCEPTION 'Published record drift: reconcile before containment rollback'; END IF;
 END LOOP;
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(saved.receipt) LOOP
  PERFORM public.rosago_admin_mutate_destination('draft',item->>'slug',(item->>'updated_at')::timestamptz,'{}'::jsonb);
 END LOOP;
 UPDATE rosago_catalog_private.publication_batches SET held_at=clock_timestamp(),held_by=(SELECT auth.uid()) WHERE batch_id=saved.batch_id;
 RETURN pg_catalog.jsonb_build_object('held',65,'deleted',0,'note','All batch records retained Draft; no Auth/schema/history restore.');
END $hold$;
REVOKE ALL ON FUNCTION public.rosago_admin_hold_first_catalog_batch() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.rosago_admin_hold_first_catalog_batch() TO authenticated;
""".replace('@BATCH_ID@',"'"+plan['batch_id']+"'")
    require(preparation.count('COMMIT;')==1,'Unexpected guard transaction.')
    return preparation.replace('COMMIT;',receipt_table+function+hold+'\nCOMMIT;')


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--refresh-generated',action='store_true');args=parser.parse_args()
    base=ROOT/'local_catalog'
    batch=read_json(base/'production-first-publication-batch-v2.review.json')
    require(hashlib.sha256((ROOT/'data/imports/rosago_pois_import_source.csv').read_bytes()).hexdigest()==SOURCE_HASH,'CSV source changed.')
    inventory=validate_inventory(read_json(base/'production-destinations-owner-export.json'))
    inventory_path=base/'production-destinations-owner-export.json'
    latest_path=base/'production-destinations-latest-owner-export.json'
    if latest_path.exists():
        latest=validate_inventory(read_json(latest_path))
        require({r['id']:r for r in latest['rows']}=={r['id']:r for r in inventory['rows']},
                'Production destination drift: review differences before rebuilding.')
        inventory=latest;inventory_path=latest_path
    result,registry=build(batch,inventory,read_json(base/'category-registry.merged-resort.review.json'),read_json(base/'image-upload-payloads.review.json'))
    output=base/'production-publication';previous=None
    if output.exists():
        require(args.refresh_generated,'Never overwrite a publication review package without checking generated-file hashes.')
        old=read_json(output/'manifest.json')
        for entry in old['files']:
            require(Path(entry['file']).name==entry['file'] and hashlib.sha256((output/entry['file']).read_bytes()).hexdigest()==entry['sha256'],'Owner edits detected; do not overwrite.')
        previous=hashlib.sha256((output/'manifest.json').read_bytes()).hexdigest()
    else:output.mkdir()
    def write(path,document):
        path.write_text(json.dumps(document,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    write(output/'change-set.review.json',result);write(output/'category-registry.review.json',registry)
    write(output/'image-uploads.review.json',dict(review_only=True,target_project_ref=TARGET,uploads=result['images']))
    guard=(base/'mapped_publication_guard.authority-fail-closed.review.sql').read_text(encoding='utf-8')
    (output/'prepare-cutover.review.sql').write_text(prepare_sql(result,guard),encoding='utf-8')
    rows=registry['categories'];values=','.join("("+','.join('NULL' if r[k] is None else "'"+r[k].replace("'","''")+"'" for k in ('key','label','parent_key'))+")" for r in rows if r['parent_key'])
    (output/'registry.review.sql').write_text("-- UNQUALIFIED REVIEW ONLY: category registry/content approval pending.\nBEGIN ISOLATION LEVEL SERIALIZABLE;\nDO $release_gate$ BEGIN RAISE EXCEPTION 'UNQUALIFIED_RELEASE'; END $release_gate$;\nINSERT INTO public.destination_categories(key,label,parent_key) VALUES "+values+";\nCOMMIT;\n",encoding='utf-8')
    files=[output/n for n in ('change-set.review.json','category-registry.review.json','image-uploads.review.json','prepare-cutover.review.sql','registry.review.sql')]
    write(output/'manifest.json',dict(review_only=True,hosted_application_qualified=False,security_blocker_resolved=False,
        previous_generated_manifest_sha256=previous,
        target_project_ref=TARGET,inventory_exported_at=inventory['exported_at'],
        source_csv_sha256=read_json(base/'production-mapped-publication-v4.review.json')['source_csv_sha256'],
        baseline_file=inventory_path.name,baseline_sha256=hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        files=[dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]))
    print(result['counts'])


if __name__=='__main__':main()
