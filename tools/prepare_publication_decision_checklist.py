"""Summarize completed local reviews; no CSV matching, image reads or hosted I/O."""
import hashlib
from pathlib import Path

from tools.local_destination_catalog import read_json, require, write_new
from tools.prepare_mapped_publication import disposition

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'brnkigrrqdrywahvcbvc'


def build_checklist(plan, evidence, images, registry, parents):
    require(plan.get('target_project_ref') == evidence.get('target_project_ref') ==
            images.get('target_project_ref') == registry.get('project_ref') == TARGET,
            'Review target mismatch.')
    require(plan.get('executable') is False and plan.get('hosted_writes') == 0,
            'Expected a non-executable review plan.')
    for key in ('source_csv_sha256', 'export_file_sha256'):
        require(plan.get(key) == evidence.get(key), 'Evidence binding mismatch.')
    require(parents.get('source_csv_sha256') == plan['source_csv_sha256'], 'Category evidence mismatch.')
    rows, locations, photos = plan['records'], evidence['records'], images['records']
    expected = set(range(1, 99))
    for inventory in (rows, locations, photos):
        require(len(inventory) == 98 and {r['csv_record'] for r in inventory} == expected,
                'Incomplete or duplicate review inventory.')
    by_location = {r['csv_record']: r for r in locations}
    by_photo = {r['csv_record']: r for r in photos}
    decisions = []
    for row in rows:
        number = row['csv_record']; location = by_location[number]; photo = by_photo[number]
        current = disposition(row, location)
        require(current['final_status_proposal'] == row['final_status_proposal'] and
                current['publication_record_ready'] == row['publication_record_ready'],
                'Publication plan is stale against location evidence.')
        require(photo['existing_id'] == row['existing_id'] and photo['name'] == row['name'],
                'Image identity mismatch.')
        hosted = row['original_row']['image_url'] if row['original_row'] else None
        require(photo['selected_hosted_image_url'] == hosted and photo['proposed_database_image_url'] == hosted,
                'Existing hosted image preservation mismatch.')
        require(photo['approved_for_upload'] is False and photo['approved_for_assignment'] is False and
                photo['publishing_authorized'] is False, 'Image approval state changed; separate review required.')
        decisions.append(dict(csv_record=number, name=row['name'], existing_id=row['existing_id'],
            candidate_origin=location['candidate_origin'],
            candidate_pair=[location['candidate_latitude'], location['candidate_longitude']],
            record_blockers=current['unresolved_record_blockers'],
            proposed_final_status=current['final_status_proposal'], image_action=photo['action']))
    ready = sum(r['proposed_final_status'] == 'published' for r in decisions)
    require(ready == plan['record_ready_for_publication_count'], 'Readiness count mismatch.')
    actions = [r['action'] for r in photos]
    image_counts = dict(preserved_hosted=actions.count('preserve_existing_hosted_image'),
        proposed_attachments=actions.count('proposed_attachment_requires_approval'),
        placeholders=sum(a.startswith('placeholder_') for a in actions))
    require(image_counts == dict(preserved_hosted=3, proposed_attachments=79, placeholders=16),
            'Completed image disposition changed.')
    require(by_photo[56]['selected_local_candidate'] is None and
            by_photo[58]['selected_local_candidate'] is None, 'Held court image unexpectedly assigned.')
    return dict(review_only=True, executable=False, target_project_ref=TARGET, hosted_writes=0,
        counts=dict(updates=plan['proposed_update_count'], additions=plan['proposed_new_count'],
            proposed_archives=len(plan['proposed_archives']), unchanged=plan['unchanged_count'],
            publication_record_ready=ready, held_draft=98-ready), image_counts=image_counts,
        aliases=[dict(csv_record=r['csv_record'], existing_id=r['existing_id'],
            existing_name=r['original_row']['name'], csv_name=r['name'],
            decision='Pending owner identity confirmation; preserve existing ID and slug if approved.')
            for r in rows if r['identity_basis']=='proposed_alias_requires_owner_confirmation'],
        archives=[dict(id=r['id'], name=r['name'], reason=r['reason'],
            approved=r['owner_explicit_approval_recorded']) for r in plan['proposed_archives']],
        unresolved_category_keys=[r for r in registry['categories'] if not r['key']],
        ambiguous_category_parents=[r for r in parents['categories'] if len(r['parent_options']) != 1],
        records=decisions,
        security_and_migration_approval=False,
        note='Decision inventory only. Even fully approved record evidence does not authorize SQL, writes, uploads or publication.')


def main():
    names = ['production-mapped-publication-v4.review.json', 'location-verification.review.json',
             'destination-images.final-mapping.review.json', 'category-registry.review.json',
             'category-parent-mapping.proposed.review.json']
    paths = [ROOT/'local_catalog'/name for name in names]
    documents = [read_json(path) for path in paths]
    digests = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    require(documents[0]['location_evidence_sha256'] == digests[names[1]], 'Location evidence changed; regenerate publication review first.')
    result = build_checklist(*documents)
    result['input_sha256'] = digests
    write_new(ROOT/'local_catalog/publication-decision-checklist.review.json', result)
    print(result['counts'])
    print(result['image_counts'])


if __name__ == '__main__': main()
