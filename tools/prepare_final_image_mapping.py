"""Finalize the existing image review decisions only; never scans/opens images."""
import hashlib
from pathlib import Path

from tools.local_destination_catalog import read_json, require, write_new

ROOT=Path(__file__).resolve().parents[1]


def mapping_records(image_review, payload_review):
    payloads={row['staged_file']:row for row in payload_review['payloads']}
    result=[]
    for image in image_review['records']:
        candidate=image['candidate'];number=image['csv_record'];hosted=image['existing_image_url']
        selected=None
        if hosted:
            action='preserve_existing_hosted_image'
            reason='Existing hosted cover is retained exactly; no replacement proposed.'
        elif number==56:
            action='placeholder_unassigned_mismatched_photo'
            reason='Indoor badminton image is not assigned to Nuvali Sand Courts.'
        elif number==58:
            action='placeholder_pending_venue_confirmation'
            reason='Shares the same source image with #56; Winner venue identity requires confirmation.'
        elif candidate is None:
            action='placeholder_no_matching_photo'
            reason='No matching local image in the completed inventory.'
        else:
            action='proposed_attachment_requires_approval'
            reason='Prepared local mapping only; no upload or assignment approved.'
            require(candidate['staged_file'] in payloads,'Missing completed upload-validator evidence.')
            selected=dict(candidate | dict(expected_upload_content_sha256=payloads[candidate['staged_file']]['expected_upload_content_sha256']))
        result.append(dict(csv_record=number,name=image['name'],existing_id=image['existing_id'],
            action=action,reason=reason,selected_hosted_image_url=hosted,selected_local_candidate=selected,
            held_candidate=candidate if number in (56,58) else None,
            placeholder='static/img/destination-placeholder.svg',placeholder_render_only=True,
            proposed_database_image_url=hosted,approved_for_upload=False,
            approved_for_assignment=False,publishing_authorized=False))
    require(len(result)==98 and len({row['csv_record'] for row in result})==98,'Image mapping inventory mismatch.')
    return result


def main():
    source=ROOT/'local_catalog/destination-images.review.json'
    payloads=ROOT/'local_catalog/image-upload-payloads.review.json'
    image_review=read_json(source);payload_review=read_json(payloads)
    require(image_review['target_project_ref']=='brnkigrrqdrywahvcbvc','Image review target mismatch.')
    require(payload_review['image_plan_sha256']==hashlib.sha256(source.read_bytes()).hexdigest(),'Image evidence hash mismatch.')
    records=mapping_records(image_review,payload_review)
    result=dict(review_only=True,hosted_changes=0,scanned_or_sanitized_again=False,
        target_project_ref=image_review['target_project_ref'],
        source_image_review_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        uploader_evidence_sha256=hashlib.sha256(payloads.read_bytes()).hexdigest(),records=records,
        preserved_hosted=sum(r['action']=='preserve_existing_hosted_image' for r in records),
        proposed_attachments=sum(r['action']=='proposed_attachment_requires_approval' for r in records),
        placeholders=sum(r['action'].startswith('placeholder_') for r in records),
        missing_photo_records=[r['csv_record'] for r in records if r['action']=='placeholder_no_matching_photo'],
        no_publication_status_changes=True,
        note='All photo assignments remain review-only. Preserve existing covers; no placeholder path is written to Supabase. Verified coordinates and the separate publication/security gates still apply.')
    write_new(ROOT/'local_catalog/destination-images.final-mapping.review.json',result)
    print({key:result[key] for key in ('preserved_hosted','proposed_attachments','placeholders','missing_photo_records')})


if __name__=='__main__':main()
