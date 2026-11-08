"""Offline catalog initialization and review planning. No network, SQL or apply path."""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'local_catalog'
PROJECT = 'jfaufpfzfhysqkhcdsrs'
STATUSES = ('published', 'draft', 'archived')
FIELDS = frozenset(('id','slug','name','description','category','address','latitude','longitude',
    'image_url','status','created_at','updated_at','tourism_type','tourism_category',
    'tourism_opening_hours_raw','tourism_closing_hours_raw','tourism_hours_status',
    'tourism_source','tourism_source_row','environment'))
IMMUTABLE = frozenset(('id','slug','created_at','updated_at'))
NEW_FIELDS = FIELDS - {'id','created_at','updated_at'}
CSV_COLUMNS = ('Place Name','Type','Category','Environment','Latitude','Longitude',
               'Days of the Week','Opening Hours','Closing Hours','Description','Address','Picture / Photo Link','')


class CatalogError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CatalogError(message)


def normalized_name(value):
    value = unicodedata.normalize('NFKD', unicodedata.normalize('NFKC', value).casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = value.replace('&', ' and ').replace("'", '').replace('\u2019', '')
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in value).split())


def rows_hash(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def timestamp(value):
    require(type(value) is str, 'A timezone-qualified timestamp is required.')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise CatalogError('Invalid timestamp.') from None
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, 'Ambiguous timestamp.')
    return parsed


def validate_row(row, *, new=False):
    require(type(row) is dict and set(row) == (NEW_FIELDS if new else FIELDS),
            'Record fields differ from the destination-only contract.')
    for field, limit in (('name',150),('slug',120),('description',3000),('address',500)):
        value = row[field]
        require(type(value) is str and 0 < len(value) <= limit and value == value.strip(),
                'Invalid required destination text.')
        require(not any(ord(c)<32 and (field!='description' or c not in '\n\r\t') for c in value),
                'Control characters are not allowed.')
    require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',row['slug']) is not None, 'Invalid slug.')
    require(bool(normalized_name(row['name'])), 'Destination name has no identifying characters.')
    require(row['status'] in STATUSES, 'Invalid publication status.')
    require(row['category'] in ('attraction','dining','shopping','accommodation','nature','heritage','industrial'), 'Invalid category.')
    for key, limit in (('latitude',90),('longitude',180)):
        value = row[key]
        require(value is None or (type(value) in (int,float) and math.isfinite(value) and -limit<=value<=limit), 'Invalid coordinate.')
    require((row['latitude'] is None)==(row['longitude'] is None), 'Coordinates must be paired.')
    for key, allowed in (('tourism_type',('Local','Common')),('environment',('Indoor','Outdoor','Mix of Both')),
                         ('tourism_hours_status',('unverified','verify_required','not_supplied'))):
        require(row[key] is None or (type(row[key]) is str and row[key] in allowed), 'Invalid optional classification.')
    for key, limit in (('tourism_category',250),('tourism_opening_hours_raw',250),
                       ('tourism_closing_hours_raw',250),('tourism_source',500)):
        value = row[key]
        require(value is None or (type(value) is str and 0<len(value)<=limit and value.strip()), 'Invalid optional metadata.')
    value = row['tourism_source_row']
    require(value is None or (type(value) is int and 2<=value<=1048576), 'Invalid provenance row.')
    image = row['image_url']
    if image is not None:
        require(type(image) is str and len(image)<=2048, 'Invalid image reference.')
        url = urlsplit(image)
        require(url.scheme in ('https','http') and url.hostname and not url.username and not url.password,
                'Image reference must be a credential-free HTTP(S) URL.')
        forbidden = {'token','access_token','refresh_token','apikey','key','signature','x-amz-signature','x-goog-signature'}
        require(not any(k.casefold() in forbidden for k,_ in parse_qsl(url.query)), 'Signed/credential-bearing image references are not supported.')
    require(not any(re.search(r'sb_(?:secret|publishable)_|Bearer\s+|eyJ[\w-]+\.[\w-]+\.[\w-]+',value)
                    for value in row.values() if isinstance(value,str)), 'Possible credential material in destination data.')
    if new:
        require(row['status']=='draft','New records must be explicitly staged as Draft.')
    else:
        try:
            require(type(row['id']) is str and str(UUID(row['id']))==row['id'],'Invalid canonical UUID.')
        except (ValueError,TypeError,AttributeError):
            raise CatalogError('Invalid canonical UUID.') from None
        timestamp(row['created_at']); timestamp(row['updated_at'])


def unique(rows):
    seen = {'id':set(), 'slug':set(), 'name':set()}
    for row in rows:
        for field, value in (('id',row['id']),('slug',row['slug']),('name',normalized_name(row['name']))):
            require(value not in seen[field], 'Duplicate '+field+' requires manual identity review.')
            seen[field].add(value)


def validate_snapshot(snapshot, *, now=None):
    require(type(snapshot) is dict and type(snapshot.get('schema_version')) is int and snapshot['schema_version']==1, 'Snapshot envelope is missing.')
    require(set(snapshot)=={'schema_version','project_ref','table','scope','all_statuses_verified',
        'authorization_ref','exported_at','row_count','status_counts','rows_sha256','rows'}, 'Unexpected snapshot metadata; destination-only input is required.')
    require(snapshot.get('project_ref')==PROJECT and snapshot.get('table')=='public.places','Evaluation project/table mismatch.')
    require(snapshot.get('scope')=='all_publication_statuses' and snapshot.get('all_statuses_verified') is True,
            'An authorized all-status snapshot is required; published-only exports are insufficient.')
    reference = snapshot.get('authorization_ref')
    require(type(reference) is str and 0<len(reference.strip())<=200, 'Owner authorization reference is required.')
    current = now or datetime.now(timezone.utc)
    age = current - timestamp(snapshot.get('exported_at'))
    require(-timedelta(minutes=5)<=age<=timedelta(hours=24), 'Snapshot is stale or future-dated; obtain a fresh authorized export.')
    rows = snapshot.get('rows')
    require(type(rows) is list and len(rows)<=2000, 'Snapshot must contain at most 2,000 destination records.')
    require(type(snapshot.get('row_count')) is int and snapshot['row_count']==len(rows),'Snapshot count mismatch.')
    for row in rows:
        validate_row(row)
    unique(rows)
    counts = snapshot.get('status_counts')
    require(type(counts) is dict and set(counts)==set(STATUSES) and
            all(type(counts[s]) is int and counts[s]==sum(r['status']==s for r in rows) for s in STATUSES), 'All-status counts mismatch.')
    require(snapshot.get('rows_sha256')==rows_hash(rows), 'Snapshot hash mismatch.')
    return rows


def initialize(snapshot, *, now=None):
    rows = validate_snapshot(snapshot,now=now)
    return dict(schema_version=1,project_ref=PROJECT,table='public.places',
                snapshot_rows_sha256=snapshot['rows_sha256'],records=json.loads(json.dumps(rows)),new_records=[])


def plan_changes(snapshot, catalog, *, now=None):
    rows = validate_snapshot(snapshot,now=now)
    require(type(catalog) is dict and type(catalog.get('schema_version')) is int and catalog['schema_version']==1 and catalog.get('project_ref')==PROJECT
            and catalog.get('table')=='public.places','Local catalog project/table mismatch.')
    require(set(catalog)=={'schema_version','project_ref','table','snapshot_rows_sha256','records','new_records'},'Unexpected catalog directives; automatic synchronization is unsupported.')
    require(catalog.get('snapshot_rows_sha256')==snapshot['rows_sha256'],'Catalog baseline hash mismatch.')
    desired, new = catalog.get('records'), catalog.get('new_records')
    require(type(desired) is list and type(new) is list and len(desired)+len(new)<=2000,'Invalid catalog record lists.')
    by_id = {row['id']:row for row in rows}
    for row in desired:
        validate_row(row)
        require(row['id'] in by_id,'Unknown existing UUID: never infer creation from an unmatched ID.')
        require(all(row[key]==by_id[row['id']][key] for key in IMMUTABLE),'Existing identity/version changed; preserve UUID, slug and timestamps.')
    unique(desired)
    desired_by_id = {row['id']:row for row in desired}
    # Omitted records remain part of collision checks, and are never removed.
    effective = [desired_by_id.get(row['id'],row) for row in rows]
    unique(effective)
    slugs = {r['slug'] for r in effective}
    names = {normalized_name(r['name']) for r in effective}
    # Also reserve prior names: renaming an existing record must not enable its accidental recreation.
    names.update(normalized_name(r['name']) for r in rows)
    proposed_new = []
    for row in new:
        validate_row(row,new=True)
        require(row['slug'] not in slugs,'New record slug collides with an existing/staged record.')
        normalized = normalized_name(row['name'])
        require(normalized not in names,'New record name collides with an existing/staged normalized name.')
        slugs.add(row['slug']); names.add(normalized)
        proposed_new.append(dict(proposed_slug=row['slug'],name=row['name'],requires_server_assigned_identity=True))
    updates, unchanged = [], 0
    for row in desired:
        original = by_id[row['id']]
        changes = {key:{'before':original[key],'after':row[key]} for key in sorted(FIELDS-IMMUTABLE) if original[key]!=row[key]}
        if changes:
            updates.append(dict(id=row['id'],slug=row['slug'],expected_updated_at=original['updated_at'],changes=changes))
        else:
            unchanged += 1
    return dict(review_only=True,executable=False,hosted_changes=0,project_ref=PROJECT,table='public.places',
                snapshot_rows_sha256=snapshot['rows_sha256'],updates=updates,proposed_new_drafts=proposed_new,
                unchanged=unchanged,omitted_records_preserved=[r['id'] for r in rows if r['id'] not in desired_by_id],
                automatic_deletes=[],automatic_archives=[],publication_changes_require_separate_review=True,
                live_identity_version_and_duplicate_recheck_required=True)


def csv_coordinate(raw, axis):
    """Parse a proposed decimal/hemisphere value; never swap columns or infer pins."""
    value = raw.strip()
    if not value or value.casefold() in ('n/a','not supplied','unknown'):
        return None
    match = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)\s*\u00b0?\s*([NSEW])?',value,re.I)
    require(match is not None,axis+'_unrecognized_format')
    number=float(match[1]);direction=(match[2] or '').upper()
    require(not direction or direction in ('NS' if axis=='latitude' else 'EW'),axis+'_hemisphere_mismatch')
    require(not (number<0 and direction in ('N','E')),axis+'_sign_conflict')
    if direction in ('S','W'):number=-abs(number)
    limit=90 if axis=='latitude' else 180
    require(math.isfinite(number) and -limit<=number<=limit,axis+'_out_of_range')
    return number


def inspect_csv(path, *, snapshot=None, now=None):
    """Inspect user CSV and propose identity-review candidates; never create a catalog."""
    raw=path.read_bytes()
    require(len(raw)<=5_000_000,'CSV exceeds the offline review size limit.')
    try:
        text=raw.decode('utf-8-sig')
        reader=csv.reader(io.StringIO(text,newline=''),strict=True)
        header=next(reader)
    except (UnicodeError,csv.Error,StopIteration):
        raise CatalogError('CSV must have a valid UTF-8 header.') from None
    require(tuple(header)==CSV_COLUMNS,'CSV columns differ from the reviewed import format.')
    baseline=validate_snapshot(snapshot,now=now) if snapshot is not None else None
    source_names=defaultdict(list)
    records=[];categories=Counter();markers=Counter();issues=Counter();types=Counter();environments=Counter()
    blank_fields=Counter();previous_line=reader.line_num
    try:
        for number,cells in enumerate(reader,1):
            require(number<=2000,'CSV exceeds the 2,000-record review limit.')
            entry=dict(record_number=number,csv_line_start=previous_line+1,csv_line_end=reader.line_num,errors=[],warnings=[])
            previous_line=reader.line_num
            if len(cells)!=len(header):
                entry['errors'].append('column_count_mismatch');records.append(entry);continue
            values=dict(zip(header,cells));name=values['Place Name'].strip()
            entry.update(name=name,normalized_name=normalized_name(name),address=values['Address'].strip())
            source_names[entry['normalized_name']].append(number)
            categories[values['Category'].strip()]+=1;markers[values['']]+=1
            types[values['Type'].strip()]+=1;environments[values['Environment'].strip()]+=1
            for field,value in values.items():
                if not value.strip():blank_fields[field]+=1
                if value!=value.strip():entry['warnings'].append('outer_whitespace:'+field)
            for field,limit in (('Place Name',150),('Description',3000),('Address',500),('Category',250)):
                value=values[field].strip()
                if not value:entry['errors'].append('missing_required:'+field)
                elif len(value)>limit:entry['errors'].append('text_too_long:'+field)
            if not entry['normalized_name']:entry['errors'].append('invalid_normalized_name')
            if values['Type'].strip() not in ('Local','Common',''):entry['errors'].append('invalid_tourism_type')
            if not values['Type'].strip():entry['warnings'].append('tourism_type_not_supplied')
            if values['Environment'].strip() not in ('Indoor','Outdoor','Mix of Both'):entry['errors'].append('invalid_environment')
            coordinates={}
            for field,axis in (('Latitude','latitude'),('Longitude','longitude')):
                try:coordinates[axis]=csv_coordinate(values[field],axis)
                except CatalogError as error:entry['errors'].append(str(error))
            if len(coordinates)==2:
                if (coordinates['latitude'] is None)!=(coordinates['longitude'] is None):entry['errors'].append('unpaired_coordinates')
                elif coordinates['latitude'] is None:entry['warnings'].append('coordinates_not_supplied')
            entry['proposed_coordinates']=coordinates
            photo=values['Picture / Photo Link'].strip()
            entry['photo_review']='not_supplied'
            if photo.casefold() in ('n/a','none','not supplied'):
                entry['warnings'].append('photo_placeholder_not_supplied')
                photo=''
            if photo:
                try:
                    url=urlsplit(photo)
                    require(url.scheme in ('http','https') and url.hostname and not url.username and not url.password,'invalid_photo_link')
                    require(not any(k.casefold() in {'token','access_token','refresh_token','key','apikey','signature','x-amz-signature','x-goog-signature'} for k,_ in parse_qsl(url.query)),'credential_bearing_photo_link')
                    entry['photo_review']='external_link_requires_review'
                    entry['warnings'].append('photo_link_not_verified_as_an_importable_image')
                except (CatalogError,ValueError):entry['errors'].append('invalid_or_credential_bearing_photo_link')
            if any('\n' in values[field] or '24 hour' in values[field].casefold() for field in ('Opening Hours','Closing Hours')):
                entry['warnings'].append('complex_hours_preserve_raw_and_review')
            if not values['Days of the Week'].strip():entry['warnings'].append('schedule_days_not_supplied')
            entry['identity_review']={'state':'pending_authorized_all_status_snapshot','candidates':[]}
            if baseline is not None:
                exact=[r for r in baseline if normalized_name(r['name'])==entry['normalized_name']]
                entry['identity_review']={'state':'candidate_update_requires_confirmation' if exact else 'unmatched_requires_alias_and_identity_review',
                    'candidates':[{'id':r['id'],'slug':r['slug'],'expected_updated_at':r['updated_at']} for r in exact]}
            records.append(entry)
    except csv.Error:
        raise CatalogError('Malformed quoted CSV record; no import plan was prepared.') from None
    duplicates=[{'normalized_name':name,'record_numbers':numbers} for name,numbers in source_names.items() if len(numbers)>1]
    for entry in records:
        if len(source_names.get(entry.get('normalized_name'),[]))>1:
            entry['errors'].append('duplicate_normalized_name_in_csv')
            entry['identity_review']['state']='blocked_duplicate_source_name'
        issues.update(entry['errors']);issues.update(entry['warnings'])
    return dict(review_only=True,import_ready=False,hosted_changes=0,source_file=path.name,source_sha256=hashlib.sha256(raw).hexdigest(),
        source_bytes=len(raw),encoding='UTF-8 (optional BOM)',columns=header,record_count=len(records),
        records_with_errors=sum(bool(r['errors']) for r in records),issue_counts=dict(issues),blank_field_counts=dict(blank_fields),
        tourism_types=dict(types),source_categories=dict(categories),environments=dict(environments),unnamed_column_values=dict(markers),
        duplicate_normalized_names=duplicates,live_matching_performed=False,authorized_snapshot_available=baseline is not None,
        blocking_decisions=['Review source Category labels for an extensible category registry; current runtime/schema need coordinated changes before import. Retain original labels as tourism_category.',
            'Review the unnamed marker column; it is not publication status or import authorization.',
            'Days of the Week has no dedicated places field; preserve the source and agree a supported representation.',
            'Review photo references separately; no link is fetched or promoted to image_url.',
            'Confirm IDs/slugs/row versions from an authorized all-status snapshot; unmatched names are not automatically new.'],records=records)


def read_json(path):
    def pairs(items):
        result = {}
        for key,value in items:
            require(key not in result,'Duplicate JSON object key.')
            result[key] = value
        return result
    def reject_constant(_):
        raise CatalogError('Non-finite JSON number.')
    return json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=reject_constant)


def write_new(path, document):
    payload = json.dumps(document,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    with path.open('x',encoding='utf-8') as output:
        output.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('init','plan','inspect-csv'))
    parser.add_argument('--source',help='CSV under data/imports (inspect-csv only).')
    parser.add_argument('--output',help='New review JSON path inside local_catalog (plan or inspect-csv).')
    args = parser.parse_args()
    try:
        manifest = read_json(DIRECTORY/'manifest.json')
        require(manifest.get('project_ref')==PROJECT and manifest.get('hosted_writes_enabled') is False,'Local manifest target/safety mismatch.')
        if args.action=='inspect-csv':
            require(args.source is not None,'Specify --source data/imports/your-file.csv.')
            source=Path(args.source).resolve()
            require(source.is_relative_to((ROOT/'data/imports').resolve()) and source.suffix.casefold()=='.csv','CSV source must be inside data/imports.')
            snapshot_path=DIRECTORY/'snapshot.json'
            result=inspect_csv(source,snapshot=read_json(snapshot_path) if snapshot_path.exists() else None)
            if args.output:
                output=Path(args.output).resolve()
                require(output.parent==DIRECTORY.resolve() and output.suffix=='.json' and output.name not in ('snapshot.json','catalog.json','manifest.json'),'CSV review output must be a new JSON inside local_catalog.')
                write_new(output,result)
            else:print(json.dumps(result,ensure_ascii=True,indent=2))
            return 0
        require(args.source is None,'--source is only supported by inspect-csv.')
        snapshot = read_json(DIRECTORY/'snapshot.json')
        if args.action=='init':
            require(args.output is None,'Init uses only local_catalog/catalog.json.')
            write_new(DIRECTORY/'catalog.json',initialize(snapshot))
            print('Initialized local catalog from the validated snapshot. Hosted changes: 0.')
        else:
            plan = plan_changes(snapshot,read_json(DIRECTORY/'catalog.json'))
            if args.output:
                output = Path(args.output).resolve()
                require(output.parent==DIRECTORY.resolve() and output.suffix=='.json'
                        and output.name not in ('snapshot.json','catalog.json','manifest.json'),'Plan output must be a new review JSON inside local_catalog.')
                write_new(output,plan)
            else:
                print(json.dumps(plan,ensure_ascii=True,indent=2))
    except (CatalogError,OSError,ValueError,TypeError) as error:
        print('STOP: '+(str(error) if isinstance(error,CatalogError) else 'Local input/output could not be validated; no hosted action occurred.'),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
