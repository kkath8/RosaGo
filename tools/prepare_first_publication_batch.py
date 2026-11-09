"""Prepare the first content batch from accepted research, never hosted writes."""
from copy import deepcopy
import hashlib

from tools.local_destination_catalog import read_json, require, write_new
from tools.export_owner_destination_review import csv_text
from tools.prepare_publication_decision_checklist import ROOT, TARGET

DESCRIPTIONS={
    56:'An outdoor beach volleyball court on Nuvali Boulevard in Santa Rosa, Laguna.',
    58:'An indoor badminton venue in the San Lorenzo South area of Santa Rosa, Laguna.',
    59:'An indoor pickleball venue at Building 26, Daystar Santa Rosa Industrial Park, Santa Rosa, Laguna.',
    60:'An indoor badminton venue at One Sta. Rosa Prime on the National Highway in Santa Rosa, Laguna.',
}


def prepare(plan,research,images,parents,registry):
    require(plan['target_project_ref']==research['target_project_ref']==images['target_project_ref']==TARGET,
            'First batch target mismatch.')
    by_research={r['csv_record']:r for r in research['records']}
    by_image={r['csv_record']:r for r in images['records']}
    require(len(plan['records'])==len(by_research)==len(by_image)==98,'First batch inventory mismatch.')
    records=[]; descriptions=[]; corrections=[]
    for source in plan['records']:
        number=source['csv_record']; evidence=by_research[number]; photo=by_image[number]
        require(source['name']==evidence['name']==photo['name'] and
                source['existing_id']==evidence['existing_id']==photo['existing_id'],'Record evidence mismatch.')
        accepted=evidence['csv_pair_numeric_valid'] and not evidence['coordinate_followup_required']
        issues=[]
        if not accepted:issues.append('Unresolved location: retain Draft')
        if source['identity_basis']=='proposed_alias_requires_owner_confirmation':issues.append('Approve existing UUID alias')
        if not source['proposed_values'].get('description'):issues.append('Approve supported description proposal')
        if not source['proposed_values'].get('category'):issues.append('Approve shared resort category/parent')
        if not source['proposed_values'].get('tourism_type'):issues.append('Decide tourism type or explicitly accept NULL')
        selected=accepted and not issues
        row=deepcopy(source)
        row.update(research_location_accepted=accepted,
            accepted_location_evidence='Owner-confirmed original CSV research; explicit instruction accepting the 81 sound locations' if accepted else None,
            accepted_pair=[evidence['candidate_latitude'],evidence['candidate_longitude']] if accepted else None,
            first_content_batch_candidate=selected,remaining_record_decisions=issues,
            final_status_proposal='published' if selected else 'draft',
            publication_record_ready=selected,
            ready_to_execute=False,
            coordinate_verification=dict(verified=accepted,
                evidence_class='owner_confirmed_original_research' if accepted else 'unresolved_exception',
                independently_surveyed=False,
                existing_alias_approval_pending=source['identity_basis']=='proposed_alias_requires_owner_confirmation'),
            image_final_mapping=deepcopy(photo))
        # Staging values remain Draft; status mutation is a separate approved step.
        row['proposed_values']['status']='draft'
        row['publication_steps']=(['stage_through_existing_audited_admin_flow',
            'record_accepted_research_through_qualified_location_rpc',
            'publish_only_after_global_gates_and_exact_change_set_approval'] if selected else ['hold_draft_until_listed_decisions_resolved'])
        row['unresolved_record_blockers']=issues
        records.append(row)
        if number in DESCRIPTIONS:
            descriptions.append(dict(csv_record=number,name=source['name'],description=DESCRIPTIONS[number],
                basis='Rephrased only from researched CSV name, category, environment and address; no new venue claims.',
                supporting_fields={k:source['proposed_values'][k] for k in ('name','tourism_category','environment','address')},approved=False))
        if number in (2,10):
            old=source['original_row']
            corrections.append(dict(csv_record=number,name=source['name'],existing_name=old['name'],existing_id=old['id'],
                existing_slug=old['slug'],expected_updated_at=old['updated_at'],
                proposed_pair=[old['latitude'],old['longitude']],
                condition='Confirm same physical destination and approve reuse of complete stored pair; #10 must not be the Bel-Air outlet.',approved=False))
    accepted=sum(r['research_location_accepted'] for r in records)
    require(accepted==81,'Accepted 81-location inventory changed; stop for review.')
    categories=[deepcopy(r) for r in registry['categories'] if r['key'] and r['parent_key'] is None and r['key'] in
                ('attraction','dining','shopping','accommodation','nature','heritage','industrial')]
    for parent in parents['categories']:
        if parent['proposed_parent'] is None:continue
        row=next(r for r in registry['categories'] if r['label']==parent['label'])
        categories.append(dict(key=row['key'],label=row['label'],parent_key=parent['proposed_parent']))
    categories.append(dict(key='resort-swimming-pool',label='Resort / Swimming Pool',parent_key='attraction'))
    candidate_registry=dict(schema_version=1,approved=False,project_ref=TARGET,categories=categories,
        review_notes=['All category/parent proposals remain pending batch approval.',
            'Both resort source labels map to resort-swimming-pool; source tourism_category text remains unchanged.',
            'attraction parent is based on pool/events descriptions; no overnight accommodation claim is added.'])
    result=dict(review_only=True,executable=False,hosted_writes=0,target_project_ref=TARGET,
        accepted_researched_locations=accepted,
        first_batch_count=sum(r['first_content_batch_candidate'] for r in records),
        accepted_locations_held_for_content_decisions=sum(r['research_location_accepted'] and not r['first_content_batch_candidate'] for r in records),
        unresolved_location_draft_count=98-accepted,
        existing_published_csv_records_outside_first_batch=[dict(csv_record=r['csv_record'],id=r['existing_id'],
            name=r['name'],expected_updated_at=r['expected_updated_at'],
            proposed_status='draft',separate_status_change_approval_required=True)
            for r in records if r['expected_status']=='published' and not r['first_content_batch_candidate']],
        note_on_totals='65 is the selected CSV batch, not automatically the whole hosted Published set. Existing Published records outside it require explicit retain/Draft/archive decisions.',
        records=records,description_proposals=descriptions,coordinate_correction_proposals=corrections,
        proposed_archives=deepcopy(plan['proposed_archives']),
        global_release_blockers=['Approve full category registry and legacy-interest-parent mapping.',
            'Qualify production provider authority and direct API Auth restore/replay protection.',
            'Qualify exact migration, guarded authenticated verification/mutation path and maintenance/atomic cutover.',
            'Refresh target/schema/row-version evidence; approve exact field diffs and every status transition.',
            'Image uploads/assignments remain separate; preserve all existing hosted covers.'],
        note='First batch means content candidates after accepting owner research, NOT hosted publication approval. Pending description/category/alias proposals are not applied automatically.')
    return result,candidate_registry


def main():
    names=['production-mapped-publication-v4.review.json','owner-research-reuse.review.json',
        'destination-images.final-mapping.review.json','category-parent-mapping.proposed.review.json','category-registry.review.json']
    paths=[ROOT/'local_catalog'/n for n in names];docs=[read_json(p) for p in paths]
    for path,digest in docs[1]['input_sha256'].items():
        require(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,'Research source changed.')
    result,registry=prepare(*docs)
    result['input_sha256']={n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in zip(names,paths)}
    require(not (ROOT/'local_catalog/first-publication-batch.csv').exists(),'Never overwrite owner batch edits.')
    for name,doc in [('production-first-publication-batch.review.json',result),('category-registry.merged-resort.review.json',registry)]:
        require(not (ROOT/'local_catalog'/name).exists(),'Never overwrite a review package.')
    write_new(ROOT/'local_catalog/production-first-publication-batch.review.json',result)
    write_new(ROOT/'local_catalog/category-registry.merged-resort.review.json',registry)
    rows=[dict(csv_number=r['csv_record'],name=r['name'],action='Update' if r['existing_id'] else 'Add',
        existing_id=r['existing_id'] or '',latitude=r['accepted_pair'][0],longitude=r['accepted_pair'][1],
        category=r['category_label'],tourism_type=r['proposed_values']['tourism_type'],
        proposed_final_status='Published after approval and security qualification',
        image_status=r['image_final_mapping']['action']) for r in result['records'] if r['first_content_batch_candidate']]
    path=ROOT/'local_catalog/first-publication-batch.csv'
    with path.open('x',encoding='utf-8-sig',newline='') as handle:handle.write(csv_text(rows))
    print({k:result[k] for k in ('accepted_researched_locations','first_batch_count','accepted_locations_held_for_content_decisions','unresolved_location_draft_count')})


if __name__=='__main__':main()
