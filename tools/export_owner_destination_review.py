"""Export editable review CSVs from completed reviews only. No import or hosted I/O."""
import csv
import hashlib
import io
from pathlib import Path

from tools.local_destination_catalog import read_json, require, write_new
from tools.prepare_publication_decision_checklist import build_checklist, ROOT

ORIGINS = {
    'csv_valid_syntax_not_verified': 'CSV: valid numeric pair only; geographic location unverified',
    'stored_pair_reuse_requires_identity_and_location_approval': 'Existing stored pair: conditional reuse; identity and geographic approval required',
    'no_valid_csv_pair': 'No usable pair available; retain Draft',
}
IMAGES = {
    'preserve_existing_hosted_image': 'Preserve existing hosted cover',
    'proposed_attachment_requires_approval': 'Proposed attachment; upload/assignment NOT approved',
    'placeholder_no_matching_photo': 'Placeholder: no matching photo',
    'placeholder_unassigned_mismatched_photo': 'Placeholder: incorrect court photo UNASSIGNED',
    'placeholder_pending_venue_confirmation': 'Placeholder: venue identity pending; photo UNASSIGNED',
}
OVERLAPS = {
    'mama-lous-italian-kitchen': 'Other Italian restaurants are distinct; no confirmed CSV match.',
    'lakeside-activities-nuvali': '#2 Nuvali Lakeside / Park: confirm activity versus park scope; no automatic merge.',
    'cibo-solenad': '#3 Solenad is the mall, not this restaurant.',
    'perlas-ancestral-house': '#44-46 name other houses; do not merge distinct identities.',
    'tiongco-ancestral-house': '#44-46 name other houses; do not merge distinct identities.',
    'kanin-club': 'No same-name CSV match; other restaurants remain separate.',
    'waltermart-bel-air': '#10 WalterMart Santa Rosa: confirm separate physical branch before archiving.',
}


def csv_text(rows):
    require(bool(rows), 'Empty review table.')
    def cell(value):
        # Quoting alone does not stop spreadsheet formula evaluation.
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + value
        return value
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows({k: cell(v) for k, v in row.items()} for row in rows)
    return buffer.getvalue()


def review_tables(plan, evidence, images, registry, parents):
    checklist = build_checklist(plan, evidence, images, registry, parents)
    locations = {r['csv_record']: r for r in evidence['records']}
    photos = {r['csv_record']: r for r in images['records']}
    main = []
    for row in sorted(plan['records'], key=lambda r: r['csv_record']):
        number = row['csv_record']; loc = locations[number]; photo = photos[number]
        values = row['proposed_values']; original = row['original_row']
        candidate = photo['selected_local_candidate']
        issues = list(row['unresolved_record_blockers'])
        if row['identity_basis'] == 'proposed_alias_requires_owner_confirmation':
            issues.append('Approve alias in aliases.csv')
        if photo['action'] == 'proposed_attachment_requires_approval':
            issues.append('Approve proposed photo identity/assignment separately')
        elif number in (56,58):
            issues.append(photo['reason'])
        if row['expected_status'] == 'published' and row['final_status_proposal'] == 'draft':
            issues.append('Existing Published-to-Draft transition requires separate explicit approval')
        description = values.get('description')
        main.append(dict(csv_number=number, destination_name=row['name'],
            existing_match=original['name'] if original else '', existing_id=row['existing_id'] or '',
            proposed_action='Update' if original else 'Add',
            current_stored_status=row['expected_status'] or 'Not yet stored',
            proposed_publication_status=row['final_status_proposal'].title(),
            address=values.get('address') or '',
            candidate_latitude=loc['candidate_latitude'], candidate_longitude=loc['candidate_longitude'],
            coordinate_basis=ORIGINS[loc['candidate_origin']],
            geographic_verification='Verified with recorded evidence' if loc['coordinate_pair_verified'] else 'NOT independently verified',
            recorded_verification_evidence=loc.get('evidence_ref') or '',
            category=row['category_label'], proposed_category_key=values.get('category') or 'UNRESOLVED',
            tourism_type=values.get('tourism_type') or 'Not recorded; decision pending',
            description_completeness='Present in source; content not independently verified' if description else 'MISSING: source-backed text required',
            description=description or '', image_assignment_status=IMAGES[photo['action']],
            proposed_image_file=candidate['staged_file'] if candidate else '',
            issues_requiring_approval='; '.join(issues),
            owner_decision='Pending', owner_notes='',
            owner_confirmed_latitude='', owner_confirmed_longitude='',
            owner_location_evidence='', owner_location_reviewer='', owner_location_reviewed_at='',
            owner_description_correction='', owner_tourism_type_decision=''))
    aliases = [dict(csv_number=r['csv_record'], existing_name=r['existing_name'],
        csv_name=r['csv_name'], existing_id=r['existing_id'],
        recommendation=r['decision'],
        specific_issue=('#2 scope versus Lakeside Activities archive' if r['csv_record']==2 else
                        'Confirm physical destination identity; this does not verify its coordinates'),
        owner_decision='Pending', owner_evidence='', owner_notes='') for r in checklist['aliases']]
    archives = [dict(existing_name=r['name'], existing_id=r['id'], current_status=r['expected_status'],
        proposed_action='Archive - approval required', reason=r['reason'],
        possible_overlap=OVERLAPS[r['slug']], owner_decision='Pending', owner_notes='')
        for r in plan['proposed_archives']]
    proposals = {r['label']: r for r in plan['proposed_category_registry']}
    parent_rows = []
    for row in parents['categories']:
        label = row['label']
        affected = [r for r in plan['records'] if r['category_label']==label]
        parent_rows.append(dict(category_label=label,
            csv_numbers='; '.join(str(r['csv_record']) for r in affected),
            destination_names='; '.join(r['name'] for r in affected),
            proposed_key=proposals[label]['proposed_key'] or 'UNRESOLVED',
            proposed_legacy_parent=row['proposed_parent'] or 'UNRESOLVED',
            parent_options='; '.join(row['parent_options']), basis=row['reason'],
            owner_decision='Pending', owner_approved_key='', owner_approved_parent='', owner_notes=''))
    conflicts = [dict(row | dict(conflicting_normalized_key=proposals[row['category_label']]['collision_candidate_key'],
        required_decision='Approve merge with explicit mapping OR distinct keys; choose lodging/recreation parent.'))
        for row in parent_rows if row['proposed_key']=='UNRESOLVED']
    require(len(aliases)==10 and len(archives)==7 and len(conflicts)==2 and len(parent_rows)==73,
            'Decision table inventories changed; review before export.')
    return {'destinations-98.csv':main, 'aliases.csv':aliases, 'proposed-archives.csv':archives,
            'category-conflicts.csv':conflicts, 'category-parents.csv':parent_rows}


def main():
    names=['production-mapped-publication-v4.review.json','location-verification.review.json',
           'destination-images.final-mapping.review.json','category-registry.review.json',
           'category-parent-mapping.proposed.review.json']
    paths=[ROOT/'local_catalog'/name for name in names]
    documents=[read_json(path) for path in paths]
    digests={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    require(documents[0]['location_evidence_sha256']==digests[names[1]], 'Location evidence changed; regenerate plan before exporting.')
    tables=review_tables(*documents)
    output=ROOT/'local_catalog/owner-review'
    require(not output.exists(), 'Owner review folder exists; never overwrite owner edits.')
    output.mkdir()
    files=[]
    for name,rows in tables.items():
        path=output/name
        with path.open('x',encoding='utf-8-sig',newline='') as handle:handle.write(csv_text(rows))
        files.append(dict(file=name,rows=len(rows),initial_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    write_new(output/'manifest.json',dict(review_only=True,executable=False,
        target_project_ref=documents[0]['target_project_ref'],input_sha256=digests,files=files,
        note='Initial worksheet hashes for traceability only; owner edits are expected. No importer or hosted mutation is provided.'))
    print({name:len(rows) for name,rows in tables.items()})


if __name__=='__main__': main()
