"""Offline mapped-only publication policy. Never treats coordinate syntax as verification."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path

from tools.local_destination_catalog import inspect_csv, read_json, require, timestamp, write_new
from tools.prepare_current_catalog_review import validate_inventory

ROOT = Path(__file__).resolve().parents[1]
COORDINATE_ERRORS = {'latitude_hemisphere_mismatch', 'longitude_hemisphere_mismatch'}


def valid_pair(latitude, longitude):
    return all(type(value) in (int, float) and math.isfinite(value) and -limit <= value <= limit
               for value, limit in ((latitude, 90), (longitude, 180)))


def seed_evidence(plan, csv_review):
    records = []
    for entry, reviewed in zip(plan['records'], csv_review['records']):
        pair = reviewed['proposed_coordinates']
        latitude, longitude = pair.get('latitude'), pair.get('longitude')
        origin = 'csv_valid_syntax_not_verified' if valid_pair(latitude, longitude) else 'no_valid_csv_pair'
        old = entry['original_row']
        if origin == 'no_valid_csv_pair' and old and valid_pair(old['latitude'], old['longitude']):
            latitude, longitude = old['latitude'], old['longitude']
            origin = 'stored_pair_reuse_requires_identity_and_location_approval'
        records.append(dict(csv_record=entry['csv_record'], name=entry['name'], existing_id=entry['existing_id'],
            candidate_origin=origin, candidate_latitude=latitude, candidate_longitude=longitude,
            matching_identity_approved=False, coordinate_pair_verified=False,
            verified_latitude=None, verified_longitude=None, evidence_ref=None, verified_by=None,
            verified_at=None, description_correction=None, description_correction_approved=False,
            tourism_type_decision_approved=False, category_relationships_approved=False))
    return dict(review_only=True, target_project_ref=plan['target_project_ref'],
        source_csv_sha256=plan['source_csv_sha256'], export_file_sha256=plan['export_file_sha256'],
        note='Pending owner review. Candidate numbers are not verified evidence. Never set verification automatically.',
        approved_archive_ids=[], records=records)


def disposition(entry, evidence):
    require(evidence['csv_record'] == entry['csv_record'] and evidence['name'] == entry['name']
            and evidence['existing_id'] == entry['existing_id'], 'Verification identity binding mismatch.')
    blockers = []
    confirmed = evidence.get('matching_identity_approved') is True
    verified = evidence.get('coordinate_pair_verified') is True
    if not confirmed:
        blockers.append('identity_not_confirmed')
    if not verified:
        blockers.append('coordinate_pair_not_verified')
    if verified:
        require(confirmed, 'Coordinate evidence cannot approve an unconfirmed identity.')
        require(valid_pair(evidence.get('verified_latitude'), evidence.get('verified_longitude')),
                'Verified coordinate evidence has an invalid or incomplete pair.')
        require(all(type(evidence.get(key)) is str and evidence[key].strip()
                    for key in ('evidence_ref', 'verified_by', 'verified_at')), 'Coordinate verification evidence is incomplete.')
        verified_at = timestamp(evidence['verified_at'])
        require(verified_at <= datetime.now(timezone.utc), 'Coordinate verification timestamp is in the future.')
    if evidence.get('description_correction_approved') is True:
        value = evidence.get('description_correction')
        require(type(value) is str and 1 <= len(value) <= 3000 and value == value.strip(),
                'Invalid approved description correction.')
    for error in entry['source_errors']:
        if error in COORDINATE_ERRORS and verified:
            continue
        if error == 'missing_required:Description' and evidence.get('description_correction_approved') is True:
            value = evidence.get('description_correction')
            require(type(value) is str and 1 <= len(value) <= 3000 and value == value.strip(), 'Invalid approved description correction.')
            continue
        blockers.append(error)
    if 'tourism_type_not_supplied' in entry['warnings'] and evidence.get('tourism_type_decision_approved') is not True:
        blockers.append('tourism_type_decision_pending')
    if evidence.get('category_relationships_approved') is not True:
        blockers.append('category_relationships_not_approved')
    if entry['proposed_values']['category'] is None:
        blockers.append('category_key_collision_unresolved')
    values = dict(entry['proposed_values'])
    if verified:
        values.update(latitude=evidence['verified_latitude'], longitude=evidence['verified_longitude'])
    if evidence.get('description_correction_approved') is True:
        values['description'] = evidence['description_correction']
    status = 'published' if not blockers else 'draft'
    # Actual status is controlled only in this new review plan, never in source
    # data or the older proposal. All new creates still stage as Draft first.
    values['status'] = status if entry['existing_id'] else 'draft'
    steps = ['create_draft'] if not entry['existing_id'] else (
        ['move_to_draft_with_separate_approved_status_action','apply_approved_field_changes']
        if entry['expected_status']=='published' else ['apply_approved_field_changes'])
    steps += ['verify_draft_location_through_guarded_audited_rpc','publish_after_qualified_preflight'] if not blockers else ['hold_draft_until_all_record_blockers_resolved']
    return dict(entry | dict(proposed_values=values, final_status_proposal=status,
        proposed_action='prepare_verified_publication' if not blockers else 'create_or_update_draft_only',
        publication_steps=steps,
        coordinate_verification=dict(verified=verified, identity_confirmed=confirmed,
            evidence_ref=evidence.get('evidence_ref'), verified_at=evidence.get('verified_at'),
            verified_by=evidence.get('verified_by')),
        publication_record_ready=not blockers, unresolved_record_blockers=blockers,
        ready_to_execute=False))


def apply_policy(plan, csv_review, evidence):
    require(evidence.get('target_project_ref') == plan['target_project_ref']
            and evidence.get('source_csv_sha256') == plan['source_csv_sha256']
            and evidence.get('export_file_sha256') == plan['export_file_sha256'], 'Evidence source/target binding mismatch.')
    evidence_rows = evidence.get('records')
    require(type(evidence_rows) is list and len(evidence_rows) == len(plan['records']), 'Incomplete evidence inventory.')
    by_record = {row['csv_record']: row for row in evidence_rows}
    require(len(by_record) == len(evidence_rows), 'Duplicate evidence record numbers.')
    entries = [disposition(entry, by_record[entry['csv_record']]) for entry in plan['records']]
    syntax_valid = sum(valid_pair(row['proposed_coordinates'].get('latitude'),
                                 row['proposed_coordinates'].get('longitude')) for row in csv_review['records'])
    count = Counter(entry['final_status_proposal'] for entry in entries)
    approved_ids = evidence.get('approved_archive_ids')
    require(type(approved_ids) is list and len(approved_ids) == len(set(approved_ids))
            and set(approved_ids) <= {row['id'] for row in plan['proposed_archives']}, 'Unrecognized archive approval.')
    archives = [row | dict(owner_explicit_approval_recorded=row['id'] in approved_ids,
                          ready_to_execute=False) for row in plan['proposed_archives']]
    return dict(plan | dict(policy='verified_mapped_only_v1',
        policy_approval='Owner instruction: Final Destination Publication Policy; hosted application NOT approved.',
        csv_syntactically_valid_coordinate_pairs=syntax_valid,
        approved_verified_coordinate_pairs=sum(e['coordinate_verification']['verified'] for e in entries),
        record_ready_for_publication_count=count['published'],
        final_csv_published_count=count['published'], final_csv_draft_count=count['draft'],
        actual_hosted_statuses_changed=False, records=entries, proposed_archives=archives,
        existing_published_to_draft_proposals=[dict(id=e['existing_id'], name=e['name'],
            expected_updated_at=e['expected_updated_at'], reason=e['unresolved_record_blockers'],
            owner_status_change_approval_required=True) for e in entries
            if e['existing_id'] and e['expected_status']=='published' and e['final_status_proposal']=='draft'],
        ready_to_execute_count=0, executable=False,
        global_blockers=plan['global_blockers']+[
            'Mapped-only location evidence policy and guarded approval RPC require current-schema qualification and separate migration/cutover approval.',
            'Approve record-bound identity and geographic evidence; syntax and existing publication status do not establish verification.'
        ],
        projected_final_status_counts_if_all_approved_and_resolved=None,
        warning='Earlier all-98-Published projection is superseded. Counts reflect current approved evidence; future verification requires regeneration. Existing hosted Published records are unchanged.',
        prepared_at=datetime.now(timezone.utc).isoformat()))


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='local_catalog/production-mapped-publication-next.review.json')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    require(output.parent == (ROOT/'local_catalog').resolve() and output.name.endswith('.review.json'),
            'Output must be a new review JSON inside local_catalog.')
    plan_path = ROOT / 'local_catalog/production-catalog-change-set.review.json'
    plan = read_json(plan_path)
    source = ROOT / 'data/imports/rosago_pois_import_source.csv'
    export = ROOT / 'local_catalog/production-destinations-owner-export.json'
    require(hashlib.sha256(source.read_bytes()).hexdigest() == plan['source_csv_sha256']
            and hashlib.sha256(export.read_bytes()).hexdigest() == plan['export_file_sha256'], 'Source evidence changed.')
    validate_inventory(read_json(export))
    review = inspect_csv(source)
    evidence_path = ROOT / 'local_catalog/location-verification.review.json'
    if not evidence_path.exists():
        write_new(evidence_path, seed_evidence(plan, review))
    result = apply_policy(plan, review, read_json(evidence_path))
    result.update(previous_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                  location_evidence_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest())
    write_new(output, result)
    print({key:result[key] for key in ('csv_syntactically_valid_coordinate_pairs',
        'approved_verified_coordinate_pairs','record_ready_for_publication_count','final_csv_published_count','final_csv_draft_count')})


if __name__ == '__main__':
    main()
