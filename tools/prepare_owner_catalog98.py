"""Prepare a separate owner-only 98-record review. No network or image processing."""
from collections import Counter
from copy import deepcopy
import argparse
import csv
import hashlib
import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from tools.local_destination_catalog import read_json, require, normalized_name
from tools.prepare_current_catalog_review import validate_inventory, SOURCE_HASH
from tools.prepare_catalog_from_preflight import validate as validate_schema

ROOT=Path(__file__).resolve().parents[1]
TARGET='brnkigrrqdrywahvcbvc'
OUTPUT=ROOT/'local_catalog/owner-publication-98'
FIELDS=('name','category','description','address','latitude','longitude','image_url','environment',
        'tourism_type','tourism_category','tourism_opening_hours_raw','tourism_closing_hours_raw',
        'tourism_hours_status','tourism_source','tourism_source_row','operating_days_raw')


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def literal(value): return "'"+json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace("'","''")+"'::jsonb"
def original_hashes():
    return {str(p.relative_to(ROOT)).replace('\\','/'):digest(p)
        for p in sorted((ROOT/'local_catalog/production-publication').rglob('*')) if p.is_file()}


def content_blockers(records):
    result=[]
    for record in records:
        values=record['values']; fields=[]
        for key,maximum in (('name',150),('description',3000),('address',500),('category',120)):
            value=values.get(key)
            if type(value) is not str or not 1<=len(value)<=maximum or value!=value.strip(): fields.append(key)
        if fields:result.append(dict(csv_record=record['csv_record'],name=values['name'],required_fields=fields))
    return result


def build(source, original, inventory, registry):
    require(source['target_project_ref']==original['target_project_ref']==inventory['owner_selected_project_ref']==registry['project_ref']==TARGET,'Wrong project.')
    require(len(source['records'])==98 and len(original['records'])==65,'Source inventory changed.')
    require(inventory['row_count']==50 and inventory['status_counts']==dict(published=35,draft=2,archived=13),'Baseline changed.')
    require({r['id']:r for r in inventory['rows']}=={r['id']:r for r in original['baseline_rows']},'Snapshot drift.')
    published={r['csv_record']:r for r in original['records']}
    baseline={r['id']:r for r in inventory['rows']}
    records=[]
    for row in source['records']:
        number=row['csv_record']; existing=row['existing_id']; pending=number not in published
        require((not pending)==row['first_content_batch_candidate'],'Published batch changed.')
        if existing:
            require(existing in baseline and row['existing_slug']==baseline[existing]['slug'],'Existing identity mismatch.')
        identifier=existing or str(uuid5(NAMESPACE_URL,f'rosago:owner98:{SOURCE_HASH}:{number}'))
        slug=baseline[existing]['slug'] if existing else 'destination-'+identifier.replace('-','')
        values=deepcopy(published[number]['values'] if not pending else {k:row['proposed_values'].get(k) for k in FIELDS})
        notes=[]
        if pending:
            # Existing hosted images stay attached. Unuploaded local photos are
            # references for later work, never broken Storage URLs in the table.
            values['image_url']=baseline[existing]['image_url'] if existing else None
            if not row['research_location_accepted']:
                values['latitude']=values['longitude']=None
                notes.append('Unresolved coordinate pair omitted; source/old pair retained in review backup, not asserted verified.')
        record=dict(csv_record=number,id=identifier,slug=slug,existing_id=existing,
            existing_name=baseline[existing]['name'] if existing else None,
            action='update' if existing else 'add',status='draft' if pending else 'published',values=values,
            identity_basis=row['identity_basis'],alias_confirmation_required=row['identity_basis']=='proposed_alias_requires_owner_confirmation',
            location_accepted=bool(row['research_location_accepted']),location_evidence=row.get('accepted_location_evidence'),
            source_coordinates=[row['proposed_values'].get('latitude'),row['proposed_values'].get('longitude')],
            review_issues=list(row['remaining_record_decisions']),notes=notes,
            image_assignment='preserve_existing_or_placeholder' if pending else 'unchanged_first65_assignment',
            local_image_mapping_reference=dict(csv_record=number,action=row['image_final_mapping']['action']))
        records.append(record)
    require(len({r['id'] for r in records})==98 and len({r['slug'] for r in records})==98,'Duplicate identity assignment.')
    require(len({normalized_name(r['values']['name']) for r in records})==98,'Duplicate normalized CSV destination.')
    existing={r['existing_id'] for r in records if r['existing_id']}
    require(len(existing)==28,'Existing match count changed.')
    holds=[deepcopy(r) for r in original['hold_draft'] if r['id'] not in existing]
    require(len(holds)==7 and len(original['hold_draft'])==21,'Published-to-Draft inventory changed.')
    desired_names={normalized_name(r['values']['name']):r['id'] for r in records}
    require(all(normalized_name(r['name']) not in desired_names or desired_names[normalized_name(r['name'])]==r['id']
        for r in inventory['rows'] if r['id'] not in existing),'Unmatched baseline name collision.')
    category_keys={c['key'] for c in registry['categories']}
    require(len(category_keys)==79 and None not in category_keys,'Full researched taxonomy changed.')
    require(all(r['values']['category'] is None or r['values']['category'] in category_keys for r in records),'Unknown category.')
    blockers=content_blockers(records)
    require({r['csv_record'] for r in blockers}=={56,58,59,60,70,72,73},'Required content blockers changed; review new evidence.')
    counts=dict(csv_destinations=98,csv_published=65,csv_draft=33,existing_matches=28,new_destinations=70,
        existing_published_to_draft=21,non_csv_published_to_draft=7,unchanged_original_drafts=2,unchanged_archived=13,
        conditional_final_total=120,conditional_final_published=65,conditional_final_draft=42,conditional_final_archived=13,
        missing_required_records=len(blockers),schema_compatible_csv_records=91,
        hypothetical_partial_total=113,hypothetical_partial_published=65,hypothetical_partial_draft=35,hypothetical_partial_archived=13,
        partial_import_authorized=False,image_uploads=51,preserved_first65_covers=3,first65_placeholders=11,
        additional_draft_image_uploads=0)
    plan=dict(schema_version=1,target_project_ref=TARGET,approved=False,alias_mappings_approved=False,
        registry_approved=False,existing_auth_risk_acknowledged=False,review_only=True,
        source_csv_sha256=SOURCE_HASH,baseline_rows=deepcopy(inventory['rows']),records=records,legacy_holds=holds,
        original_hold_draft=deepcopy(original['hold_draft']),categories=deepcopy(registry['categories']),
        images=deepcopy(original['images']),counts=counts,mandatory_content_blockers=blockers,
        qualification='UNQUALIFIED_OWNER98_RELEASE',
        note='All-or-nothing 98-source plan. Never insert 91 as a fallback. Current NULL mandatory fields block all application.')
    value=json.dumps(plan,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    plan['plan_sha256']=hashlib.sha256(value).hexdigest();plan['batch_id']='owner98-'+plan['plan_sha256'][:20]
    proposals=[]
    for row in source['description_proposals']:
        proposals.append(dict(csv_record=row['csv_record'],field='description',proposed_value=row['description'],
            evidence=row['supporting_fields'],basis=row['basis'],approved=False))
    for number in (70,72,73):
        row=next(r for r in source['records'] if r['csv_record']==number)
        proposals.append(dict(csv_record=number,field='category',proposed_value='resort-swimming-pool',
            evidence=dict(csv_tourism_category=row['proposed_values']['tourism_category'],description=row['proposed_values']['description']),
            basis='Existing merged-resort proposal: attraction parent; no lodging classification inferred.',approved=False))
    resolved=deepcopy(plan)
    for proposal in proposals:
        next(r for r in resolved['records'] if r['csv_record']==proposal['csv_record'])['values'][proposal['field']]=proposal['proposed_value']
    resolved['mandatory_content_blockers']=content_blockers(resolved['records'])
    require(not resolved['mandatory_content_blockers'],'Proposed resolutions are insufficient.')
    resolved['counts']['missing_required_records']=0
    resolved['counts']['schema_compatible_csv_records']=98
    resolved['resolution_proposals_applied_for_review_only']=True
    resolved['note']='Conditional full-98 scenario using seven EXISTING supported proposals; NOT owner-approved and NOT executable.'
    resolved['plan_sha256']=hashlib.sha256(json.dumps(resolved,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    resolved['batch_id']='owner98-proposed-'+resolved['plan_sha256'][:20]
    return plan,resolved,proposals


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--refresh-generated',action='store_true');args=parser.parse_args()
    saved=original_hashes()
    original=ROOT/'local_catalog/production-publication'
    manifest=read_json(original/'manifest.json')
    for e in manifest['files']:require(digest(original/e['file'])==e['sha256'],'Original publication package changed.')
    inputs=['local_catalog/production-first-publication-batch-v2.review.json',
        'local_catalog/production-publication/change-set.review.json','local_catalog/production-destinations-latest-owner-export.json',
        'local_catalog/category-registry.merged-resort.review.json','local_catalog/production-catalog-latest-schema-preflight-corrected.json',
        'local_catalog/catalog_extension.production-bound-v2.review.sql','local_catalog/destination-images.final-mapping.review.json']
    require(digest(ROOT/'data/imports/rosago_pois_import_source.csv')==SOURCE_HASH,'Source CSV hash changed.')
    source,first,inventory,registry=[read_json(ROOT/p) for p in inputs[:4]]
    inventory=validate_inventory(inventory);validate_schema(read_json(ROOT/inputs[4]))
    plan,resolved,proposals=build(source,first,inventory,registry)
    if OUTPUT.exists():
        require(args.refresh_generated,'Separate owner98 package exists; never overwrite without hash checks.')
        old=read_json(OUTPUT/'manifest.json')
        for e in old['files']:require(digest(OUTPUT/e['file'])==e['sha256'],'Owner98 package was edited; stop.')
    OUTPUT.mkdir(exist_ok=True)
    def write(name,value):
        (OUTPUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n' if not isinstance(value,str) else value,encoding='utf-8')
    write('change-set.review.json',plan);write('change-set.with-proposed-resolutions.review.json',resolved)
    write('required-content-decisions.review.json',dict(approved=False,decisions=proposals))
    write('alias-decisions.review.json',dict(approved=False,mappings=[dict(csv_record=r['csv_record'],
        existing_id=r['existing_id'],existing_slug=r['slug'],existing_name=r['existing_name'],csv_name=r['values']['name'],
        decision='Reuse this existing UUID/slug only after exact mapping approval; never create a duplicate.',approved=False)
        for r in plan['records'] if r['alias_confirmation_required']]))
    write('category-registry.review.json',dict(schema_version=1,project_ref=TARGET,approved=False,categories=plan['categories']))
    write('image-uploads.review.json',dict(target_project_ref=TARGET,approved=False,uploads=plan['images'],draft_uploads_deferred=True))
    schema=(ROOT/inputs[5]).read_text(encoding='utf-8')
    write('schema.review.sql',schema.replace('BEGIN;',"BEGIN;\nDO $owner98_install_gate$ BEGIN RAISE EXCEPTION 'UNAPPROVED_OWNER98_SCHEMA'; END $owner98_install_gate$;",1))
    template=(ROOT/'tools/owner_catalog98/apply.sql.in').read_text(encoding='utf-8')
    write('apply.review.sql',template.replace('@PLAN@',literal(plan)))
    write('apply.with-proposed-resolutions.review.sql',template.replace('@PLAN@',literal(resolved)))
    for name in ('rollback.review.sql','postflight.readonly.sql','preflight.readonly.sql','README.md'):
        write(name,(ROOT/'tools/owner_catalog98'/name).read_text(encoding='utf-8'))
    with (OUTPUT/'destinations.review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        fields=('csv_number','name','action','id','slug','status','category','latitude','longitude','description_missing','alias_confirmation_required','issues')
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for r in plan['records']:
            v=r['values'];writer.writerow(dict(csv_number=r['csv_record'],name=v['name'],action=r['action'],id=r['id'],slug=r['slug'],status=r['status'],
                category=v['category'],latitude=v['latitude'],longitude=v['longitude'],description_missing=not v['description'],
                alias_confirmation_required=r['alias_confirmation_required'],issues='; '.join(r['review_issues']+r['notes'])))
    files=[p for p in sorted(OUTPUT.iterdir()) if p.name not in ('manifest.json','qualification-results.json') and p.is_file()]
    write('manifest.json',dict(target_project_ref=TARGET,review_only=True,executable=False,hosted_application_qualified=False,
        inputs_sha256={p:digest(ROOT/p) for p in inputs},preserved_original_package_sha256=saved,
        source_csv_sha256=SOURCE_HASH,counts=plan['counts'],
        files=[dict(file=p.name,sha256=digest(p)) for p in files]))
    require(saved==original_hashes(),'Original package was modified.')
    print(json.dumps(dict(output=str(OUTPUT.relative_to(ROOT)),counts=plan['counts'],mandatory_content_blockers=plan['mandatory_content_blockers']),indent=2))

if __name__=='__main__':main()
