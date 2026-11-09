"""Future owner staging/read-back helper; never uploads or loads credentials.

Both actions require a separately generated approved release manifest. Current
review manifests refuse before opening images, creating files or making HTTP.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import time

import httpx
from werkzeug.datastructures import FileStorage
from admin_photo_service import prepare_photo
from tools.prepare_owner_catalog98 import ROOT, TARGET, OUTPUT, literal

ORIGIN='https://'+TARGET+'.supabase.co'


def validate_images(document):
    if document.get('target_project_ref')!=TARGET or type(document.get('uploads')) is not list or len(document['uploads'])!=51:
        raise ValueError('Fixed production image manifest mismatch.')
    seen=set()
    for image in document['uploads']:
        key=image['object_name']
        if (not re.fullmatch(r'destinations/[0-9a-f]{32}\.(jpg|png|webp)',key) or key in seen
            or image.get('upsert') is not False or image.get('bucket_id')!='destination-images'
            or image['public_url']!=ORIGIN+'/storage/v1/object/public/destination-images/'+key
            or image['mime_type'] not in ('image/jpeg','image/png','image/webp')
            or type(image['bytes']) is not int or not 0<image['bytes']<=5*1024*1024
            or not re.fullmatch('[0-9a-f]{64}',image['expected_upload_sha256'])
            or not re.fullmatch('[0-9a-f]{64}',image['staged_sha256'])):
            raise ValueError('Reserved image scope mismatch.')
        seen.add(key)
    return document['uploads']


def approved_images(folder):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    # Not a CLI bypass flag: this field is absent/false in the review artifact.
    if manifest.get('target_project_ref')!=TARGET or manifest.get('owner_release_approved') is not True:
        raise ValueError('UNAPPROVED_OWNER98_IMAGE_OPERATION: obtain exact release approval first.')
    entry=next(e for e in manifest['files'] if e['file']=='image-uploads.review.json')
    path=folder/entry['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Image manifest hash mismatch.')
    return validate_images(json.loads(path.read_text(encoding='utf-8')))


def stage(images,output,*,root=ROOT,prepare=prepare_photo):
    if output.exists():raise ValueError('Never overwrite a prior upload staging directory.')
    prepared=[]
    for image in images:
        source=(root/Path(image['staged_file'].replace('\\','/'))).resolve()
        if not source.is_relative_to((root/'local_catalog/image-staging').resolve()):
            raise ValueError('Staged source escaped the approved image-staging directory.')
        raw=source.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=image['staged_sha256']:raise ValueError('Staged input changed.')
        photo=prepare(FileStorage(stream=BytesIO(raw),filename=source.name,content_type=image['mime_type']))
        if (hashlib.sha256(photo.content).hexdigest()!=image['expected_upload_sha256']
            or len(photo.content)!=image['bytes'] or photo.content_type!=image['mime_type']):
            raise ValueError('Validated upload payload differs from the existing proof.')
        prepared.append((Path(image['object_name']).name,photo.content))
    output.mkdir(parents=False,exist_ok=False)
    for name,content in prepared:
        with (output/name).open('xb') as handle:handle.write(content)
    return len(prepared)


def verify(images,client):
    receipts=[]
    for image in images:
        started=time.monotonic();sha=hashlib.sha256();size=0
        with client.stream('GET',image['public_url'],headers={'Accept-Encoding':'identity'}) as response:
            if (response.status_code!=200 or response.headers.get('content-encoding','identity')!='identity'
                or response.headers.get('content-type','').split(';')[0].strip().lower()!=image['mime_type']):
                raise ValueError('Public image read-back failed; reconcile this upload, never overwrite or retry blindly.')
            for chunk in response.iter_bytes():
                size+=len(chunk)
                if size>image['bytes'] or time.monotonic()-started>10:raise ValueError('Image read-back exceeded bounds.')
                sha.update(chunk)
        if size!=image['bytes'] or sha.hexdigest()!=image['expected_upload_sha256']:
            raise ValueError('Public image bytes do not match the reviewed payload.')
        receipts.append(dict(object_name=image['object_name'],sha256=sha.hexdigest(),bytes=size,
            mime_type=image['mime_type'],verified_by='postgres'))
    return receipts


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('stage','verify'));args=parser.parse_args()
    images=approved_images(OUTPUT)  # fail before local image work or network
    if args.action=='stage':
        count=stage(images,OUTPUT/'upload-files');print(json.dumps(dict(staged=count,uploaded=0)));return
    target=OUTPUT/'verified-upload-receipts.json';sql_path=OUTPUT/'record-upload-receipts.review.sql'
    if target.exists() or sql_path.exists():raise ValueError('Prior receipts exist; reconcile instead of overwriting.')
    with httpx.Client(timeout=httpx.Timeout(3),follow_redirects=False,trust_env=False) as client:
        try:receipts=verify(images,client)
        except Exception:raise ValueError('Image read-back unconfirmed; no receipts written.') from None
    target.write_text(json.dumps(dict(target_project_ref=TARGET,verified_at=datetime.now(timezone.utc).isoformat(),
        receipts=receipts),indent=2)+'\n',encoding='utf-8')
    statement="""-- ACTUAL PUBLIC READ-BACK RECEIPTS. Still requires exact owner SQL approval.
BEGIN;
DO $receipt_gate$ BEGIN RAISE EXCEPTION 'UNAPPROVED_OWNER98_RECEIPT_IMPORT'; END $receipt_gate$;
DO $owner$ BEGIN IF SESSION_USER<>'postgres' OR CURRENT_USER<>'postgres' THEN
 RAISE EXCEPTION 'Trusted owner connection required'; END IF; END $owner$;
INSERT INTO rosago_owner_catalog98.upload_receipts(object_name,sha256,bytes,mime_type,verified_by)
SELECT object_name,sha256,bytes,mime_type,verified_by FROM jsonb_to_recordset(@RECEIPTS@)
 AS r(object_name text,sha256 text,bytes bigint,mime_type text,verified_by text);
COMMIT;
""".replace('@RECEIPTS@',literal(receipts))
    sql_path.write_text(statement,encoding='utf-8');print(json.dumps(dict(verified=len(receipts),uploads=0,sql_executed=False)))

if __name__=='__main__':main()
