"""Offline historical candidate comparison, not a live inventory or apply plan."""
from collections import Counter,defaultdict
import argparse
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re

if __package__:
    from .local_destination_catalog import normalized_name, require, write_new
else:
    from local_destination_catalog import normalized_name, require, write_new

ROOT=Path(__file__).resolve().parents[1]
TARGET='brnkigrrqdrywahvcbvc'


def historical_rows(text):
    require(TARGET in text,'Historical index target is not the confirmed project.')
    result=[]
    for line in text.splitlines():
        cells=[cell.strip() for cell in line.split('|')[1:-1]]
        if len(cells)==5 and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',cells[0]):
            result.append(dict(zip(('id','name','slug','status','category'),cells)))
    require(len(result)==len({row['id'] for row in result}) and bool(result),'Historical index identities are incomplete or duplicated.')
    return result


def alias_score(source, existing):
    """Heuristics propose manual candidates only; never establish identity."""
    left=normalized_name(source);right=normalized_name(existing['name'])
    core=normalized_name(re.sub(r'\([^)]*\)','',source))
    if core and core==right:return 0.98
    score=max(SequenceMatcher(None,left,right).ratio(),SequenceMatcher(None,left,normalized_name(existing['slug'])).ratio())
    generic={'the','of','city','santa','rosa','sta','laguna','and','in','at','philippines'}
    a=set(left.split())-generic;b=set(right.split())-generic
    if len(a&b)>=2 and (a<=b or b<=a):score=max(score,0.90)
    return score


def compare_candidates(csv_review, rows):
    require(csv_review.get('review_only') is True and csv_review.get('record_count')==len(csv_review['records']), 'Invalid CSV review.')
    results=[];claimed=set();counts=Counter()
    for record in csv_review['records']:
        name=record.get('name','');key=normalized_name(name)
        exact=[row for row in rows if normalized_name(row['name'])==key]
        candidates=[dict(row,match='exact_normalized_name',score=1.0) for row in exact]
        if exact:state='exact_name_historical_update_candidate'
        else:
            scores=[(alias_score(name,row),row) for row in rows]
            candidates=[dict(row,match='heuristic_manual_review_only',score=round(score,3))
                        for score,row in sorted(scores,key=lambda value:(-value[0],value[1]['id'])) if score>=0.72][:4]
            state='historical_alias_review' if candidates else 'unmatched_not_confirmed_new'
        counts[state]+=1
        claimed.update(row['id'] for row in candidates)
        results.append(dict(record_number=record['record_number'],csv_line_start=record['csv_line_start'],name=name,
            current_classification='Invalid - correction required' if record['errors'] else 'Ambiguous - manual review',
            field_errors=record['errors'],historical_comparison=state,candidates=candidates,
            live_identity_verified=False,ready_for_publication=False))
    missing=[row for row in rows if row['id'] not in claimed]
    references=defaultdict(list)
    for record in results:
        for candidate in record['candidates']:references[candidate['id']].append(record['record_number'])
    return dict(review_only=True,executable=False,current_inventory_available=False,
        confirmed_update_count=None,confirmed_new_count=None,ready_for_publication_count=0,
        source_records=len(results),csv_records_with_field_errors=sum(bool(r['field_errors']) for r in results),
        historical_candidate_counts=dict(counts),records=results,
        historical_missing_from_csv_review=[r for r in missing if r['status']!='archived'],
        historical_already_archived_without_candidate=[r for r in missing if r['status']=='archived'],
        candidate_id_conflicts=[dict(id=key,csv_records=values) for key,values in references.items() if len(values)>1],
        automatic_updates=[],automatic_creates=[],automatic_archives=[],automatic_deletes=[],
        existing_images_must_be_preserved=True,
        warning='Historical name-only candidates cannot authorize changes or establish current identity, images, row versions or publication readiness.')


def proposed_categories(csv_review):
    """Extensible label proposals, not a replacement fixed enum or approved taxonomy."""
    categories=[];groups=defaultdict(list)
    for label in csv_review['source_categories']:groups[normalized_name(label).replace(' ','-')].append(label)
    for label in sorted(csv_review['source_categories']):
        key=normalized_name(label).replace(' ','-')
        require(key and len(key)<=120,'Category key length requires manual review.')
        collision=len(groups[key])>1
        categories.append(dict(proposed_key=None if collision else key,label=label,parent_key=None,
            collision_candidate_key=key if collision else None,owner_review_required=True))
    return categories


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='local_catalog/production-publication-review.json')
    args=parser.parse_args()
    source=ROOT/'data/imports/rosago_pois_import_source.csv'
    report=ROOT/'local_catalog/csv-review-c55ed7076b59-v2.json'
    index=ROOT/'docs/admin-finalization/explore-real-edit-readiness/INVENTORY-current.md'
    review=json.loads(report.read_text(encoding='utf-8'))
    require(hashlib.sha256(source.read_bytes()).hexdigest()==review['source_sha256'],'CSV changed; repeat validation first.')
    text=index.read_text(encoding='utf-8');rows=historical_rows(text)
    result=compare_candidates(review,rows)
    result.update(prepared_at=datetime.now(timezone.utc).isoformat(),target_project_ref=TARGET,
        target_evidence='Separately observed owner-run localhost:5000 Flask process environment; evaluation flag false.',
        current_inventory_blocker='Supabase MCP OAuth token refresh failed before a database query.',
        historical_index=str(index.relative_to(ROOT)),historical_index_sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
        historical_observed_at='2026-11-06T14:51:34.545198+00:00',historical_record_count=len(rows),
        source_csv_sha256=review['source_sha256'],evaluation_catalog_manifest_changed=False,
        target_verified_by_this_offline_helper=False,
        target_reconfirmation_required_before_any_future_operation=True,
        proposed_extensible_categories=proposed_categories(review))
    output=Path(args.output).resolve()
    require(output.parent==(ROOT/'local_catalog').resolve() and output.suffix=='.json'
            and output.name not in ('manifest.json','snapshot.json','catalog.json'),'Output must be a new local review JSON, not a catalog input.')
    write_new(output,result)
    print(json.dumps({k:result[k] for k in ('target_project_ref','current_inventory_available','source_records',
        'csv_records_with_field_errors','historical_candidate_counts','ready_for_publication_count')},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
