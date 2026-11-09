"""Reuse owner-confirmed research; isolate existing exceptions without rematching."""
import hashlib
from datetime import datetime, timezone

from tools.export_owner_destination_review import csv_text
from tools.local_destination_catalog import read_json, require, write_new
from tools.prepare_mapped_publication import valid_pair
from tools.prepare_publication_decision_checklist import ROOT, TARGET

OWNER_STATEMENT = 'The 98 destinations in our CSV were already researched and verified when we originally created the list.'


def assess(plan, csv_review, images, historical):
    require(plan['target_project_ref'] == images['target_project_ref'] == TARGET,
            'Research review target mismatch.')
    require(plan['source_csv_sha256'] == csv_review['source_sha256'], 'Research source hash mismatch.')
    rows = plan['records']; source_rows = csv_review['records']; photos = images['records']
    for inventory, key in ((rows,'csv_record'),(source_rows,'record_number'),(photos,'csv_record')):
        require(len(inventory)==98 and {r[key] for r in inventory}==set(range(1,99)),
                'Research inventory missing or duplicated.')
    by_source = {r['record_number']:r for r in source_rows}
    by_photo = {r['csv_record']:r for r in photos}
    old_by_id = {r['id']:r for r in historical['rows'] if r.get('id')}
    records = []
    for row in sorted(rows,key=lambda r:r['csv_record']):
        number=row['csv_record']; source=by_source[number]; photo=by_photo[number]
        require(row['name']==source['name']==photo['name'] and row['existing_id']==photo['existing_id'],
                'Research record identity mismatch.')
        pair=source['proposed_coordinates']; numeric=valid_pair(pair.get('latitude'),pair.get('longitude'))
        # Known malformed pairs never inherit dataset-level confirmation.
        coordinate_errors=[e for e in source['errors'] if 'hemisphere_mismatch' in e]
        require(not (numeric and coordinate_errors), 'Inconsistent prior coordinate evidence.')
        issues=[]
        if not numeric:
            issues.append('Correct malformed coordinate pair' if coordinate_errors else 'Supply missing pair OR retain Draft')
        if number in (44,46):
            issues.append('Confirm distinct house locations: nearly identical points and only Poblacion-level addresses')
        if not row['proposed_values'].get('description'):
            issues.append('Supply source-backed description')
        if row['identity_basis']=='proposed_alias_requires_owner_confirmation':
            issues.append('Confirm existing UUID alias mapping; no repeat venue research required')
        if not row['proposed_values'].get('category'):
            issues.append('Resolve resort category key/parent conflict')
        if not row['proposed_values'].get('tourism_type'):
            issues.append('Decide missing tourism type or explicitly retain NULL')
        original=row['original_row']; documented=old_by_id.get(row['existing_id'])
        support=[]
        if original:
            support.append('Matching UUID/name and stored values documented in owner production export; not independent geocoding')
        if documented:
            support.append('Same UUID documented in historical Tourism transition; not new geographic verification')
        records.append(dict(csv_record=number,name=row['name'],existing_id=row['existing_id'],
            existing_match=original['name'] if original else None,
            proposed_action='Update' if original else 'Add',
            research_evidence_class='owner_confirmed_original_research',
            research_evidence_ref='OWNER_RESEARCH_REUSE_REVIEW.md#owner-confirmed-research',
            independently_documented_geographic_verification=False,
            documented_project_support=support,
            csv_pair_numeric_valid=numeric,
            research_coordinate_status=('Owner-confirmed research; targeted house-pin question remains'
                if numeric and number in (44,46) else 'Owner-confirmed researched pair; reuse without blanket re-verification'
                if numeric else 'Dataset research confirmed, but this coordinate pair is missing or malformed'),
            candidate_latitude=pair.get('latitude') if numeric else None,
            candidate_longitude=pair.get('longitude') if numeric else None,
            conditional_stored_pair=([original['latitude'],original['longitude']]
                if not numeric and original and valid_pair(original['latitude'],original['longitude']) else None),
            coordinate_followup_required=not numeric or number in (44,46),
            category=row['category_label'],tourism_type=row['proposed_values'].get('tourism_type'),
            description_complete=bool(row['proposed_values'].get('description')),
            image_action=photo['action'],
            location_policy_outcome=('Draft until corrected' if not numeric else
                'Draft pending targeted house-pin clarification' if number in (44,46) else
                'Location research retained; publication still subject to outstanding decisions and security gates'),
            additional_decisions=issues,hosted_application_approved=False))
    return dict(review_only=True,executable=False,target_project_ref=TARGET,hosted_writes=0,
        owner_statement=OWNER_STATEMENT,
        counts=dict(owner_confirmed_researched_destinations=98,
            numeric_csv_pairs=sum(r['csv_pair_numeric_valid'] for r in records),
            researched_pairs_reusable_without_new_location_question=sum(r['csv_pair_numeric_valid'] and not r['coordinate_followup_required'] for r in records),
            targeted_house_pin_questions=sum(r['csv_pair_numeric_valid'] and r['coordinate_followup_required'] for r in records),
            malformed_or_missing_pairs=sum(not r['csv_pair_numeric_valid'] for r in records),
            independently_documented_geographic_verifications=0,
            records_with_additional_decisions=sum(bool(r['additional_decisions']) for r in records)),
        records=records,
        archives_remain_unapproved=[dict(id=r['id'],name=r['name']) for r in plan['proposed_archives']],
        note='Owner-confirmed research is evidence, not an independent survey or hosted-write approval. Earlier empty worksheet fields do not negate original research. No runtime, RLS, SQL, image mapping or formal execution gate is changed.')


def table_rows(result):
    return [dict(csv_number=r['csv_record'],destination_name=r['name'],existing_match=r['existing_match'] or '',
        proposed_action=r['proposed_action'],research_basis=r['research_evidence_class'],
        documented_support='; '.join(r['documented_project_support']),
        independently_documented_location_check='Not found in reviewed project evidence',
        coordinate_research_status=r['research_coordinate_status'],
        latitude=r['candidate_latitude'],longitude=r['candidate_longitude'],
        conditional_stored_pair=str(r['conditional_stored_pair']) if r['conditional_stored_pair'] else '',
        location_policy_outcome=r['location_policy_outcome'],category=r['category'],tourism_type=r['tourism_type'] or '',
        description_completeness='Present' if r['description_complete'] else 'Missing',image_assignment_status=r['image_action'],
        remaining_decisions='; '.join(r['additional_decisions']),owner_response='',owner_evidence='') for r in result['records']]


def main():
    names=['local_catalog/production-mapped-publication-v4.review.json',
        'local_catalog/csv-review-c55ed7076b59-v2.json',
        'local_catalog/destination-images.final-mapping.review.json',
        'data/santa_rosa_places/archive/tourism_transition_plan.json']
    paths=[ROOT/name for name in names]
    documents=[read_json(p) for p in paths]
    require(hashlib.sha256((ROOT/'data/imports/rosago_pois_import_source.csv').read_bytes()).hexdigest()==documents[0]['source_csv_sha256'],
            'Original researched CSV changed.')
    result=assess(*documents)
    result['input_sha256']={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in zip(names,paths)}
    result['owner_confirmation_recorded_at']=datetime.now(timezone.utc).isoformat()
    result['timestamp_meaning']='Time this owner confirmation was recorded locally, NOT the unknown original research/survey date.'
    output=ROOT/'local_catalog/owner-research-reuse.review.json'
    all_rows=table_rows(result)
    csv_outputs={'destinations-98.research-aware.csv':all_rows,
        'remaining-destination-decisions.csv':[r for r in all_rows if r['remaining_decisions']]}
    require(not output.exists() and all(not (ROOT/'local_catalog'/name).exists() for name in csv_outputs),
            'Review output exists; never overwrite owner decisions.')
    write_new(output,result)
    for name,rows in csv_outputs.items():
        with (ROOT/'local_catalog'/name).open('x',encoding='utf-8-sig',newline='') as handle:handle.write(csv_text(rows))
    print(result['counts'])


if __name__=='__main__':main()
