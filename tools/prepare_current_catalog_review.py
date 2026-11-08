"""Offline production inventory review. No network, SQL, import or apply path."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path

from tools.local_destination_catalog import (
    CatalogError, CSV_COLUMNS, inspect_csv, normalized_name, read_json, require,
    rows_hash, timestamp, unique, validate_row, write_new,
)
from tools.prepare_publication_review import TARGET, alias_score, proposed_categories

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HASH = 'c55ed7076b59d611bc57eb0d59b0c6c425b301e4999655b01a17a9a8ca87ed2a'
# Explicit review proposals, not fuzzy identity assignments or approved aliases.
ALIASES = {
    'Nuvali Lakeside / Park': 'Nuvali Park',
    'Ayala Malls Solenad (Ayala Malls Nuvali)': 'Ayala Malls Solenad',
    'Fort Santo Domingo / Cuartel de Santo Domingo': 'Cuartel de Santo Domingo',
    'Santa Rosa Arch': 'Santa Rosa Arch (Bantayang Bato)',
    'The City of Santa Rosa Museum (Museo de Santa Rosa)': 'Museo ng Santa Rosa',
    'Toyota Santa Rosa (Toyota Motor Philippines)': 'Toyota Santa Rosa',
    'Coca-Cola Santa Rosa (Coca-Cola Beverages Philippines)': 'Coca-Cola Santa Rosa',
    'Monde Nissin Santa Rosa Plant': 'Monde Nissin Santa Rosa',
    'Mitsubishi Motors Philippines Corporation': 'Mitsubishi Motors Santa Rosa',
    'Fun Farm at Sta. Elena': 'The Fun Farm at Sta. Elena',
}


def validate_inventory(document):
    """Accept the documented owner export, including Dashboard's one-cell wrapper."""
    if isinstance(document, list):
        require(len(document) == 1 and isinstance(document[0], dict)
                and set(document[0]) == {'destination_inventory_json'}, 'Unexpected export wrapper.')
        document = document[0]['destination_inventory_json']
    if isinstance(document, str):
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, 'Duplicate JSON object key.')
                result[key] = value
            return result
        document = json.loads(document, object_pairs_hook=pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(CatalogError('Non-finite JSON number.')))
    require(isinstance(document, dict), 'Expected inventory object.')
    require(document.get('export_format') == 'rosago_owner_destination_inventory_v1', 'Unexpected export format.')
    require(document.get('owner_selected_project_ref') == TARGET, 'Owner-selected target mismatch.')
    require(document.get('project_identity_requires_dashboard_confirmation') is True,
            'Project identity attestation boundary missing.')
    require(document.get('table') == 'public.places'
            and document.get('scope') == 'all_publication_statuses', 'Incomplete inventory scope.')
    require(document.get('transaction_read_only') == 'on', 'Read-only transaction not verified.')
    require(document.get('database_role') == 'postgres'
            and document.get('row_security_active_for_export_role') is False, 'Unrestricted export visibility not verified.')
    require(type(document.get('unexpected_status_count')) is int
            and document['unexpected_status_count'] == 0, 'Unexpected publication status.')
    exported = timestamp(document.get('exported_at'))
    rows = document.get('rows')
    require(type(rows) is list and type(document.get('row_count')) is int
            and len(rows) == document['row_count'], 'Export count mismatch.')
    for row in rows:
        validate_row(row)
        require(timestamp(row['created_at']) <= timestamp(row['updated_at']) <= exported,
                'Row timestamp exceeds the export or predates creation.')
    unique(rows)
    counts = {key: sum(row['status'] == key for row in rows) for key in ('published', 'draft', 'archived')}
    supplied = document.get('status_counts')
    require(type(supplied) is dict and set(supplied) == set(counts)
            and all(type(supplied[k]) is int and supplied[k] == counts[k] for k in counts), 'Status counts mismatch.')
    return document


def optional(value):
    stripped = value.strip()
    return None if stripped.casefold() in ('', 'n/a', 'none', 'not supplied') else stripped


def desired_values(source, review, old, category):
    """Preserve blanks on updates, image references and immutable identities."""
    values = {} if old is None else dict(old)
    mapping = {'name': 'Place Name', 'description': 'Description', 'address': 'Address',
               'tourism_type': 'Type', 'environment': 'Environment', 'tourism_category': 'Category',
               'tourism_opening_hours_raw': 'Opening Hours', 'tourism_closing_hours_raw': 'Closing Hours',
               'operating_days_raw': 'Days of the Week'}
    for field, column in mapping.items():
        value = optional(source[column])
        if value is not None or old is None:
            values[field] = value
    # Preserve original multiline source text; no schedule interpretation.
    for field, column in (('tourism_opening_hours_raw', 'Opening Hours'),
                          ('tourism_closing_hours_raw', 'Closing Hours')):
        if optional(source[column]) is not None:
            values[field] = source[column]
    if set(review['proposed_coordinates']) == {'latitude', 'longitude'}:
        coords = review['proposed_coordinates']
        if coords['latitude'] is not None or old is None:
            values.update(coords)
    elif old is None:
        values.update(latitude=None, longitude=None)
    values['category'] = category['proposed_key']
    values['tourism_source'] = 'rosago_pois_import_source.csv'
    values['tourism_source_row'] = review['csv_line_start']
    if any(optional(source[column]) is not None for column in ('Opening Hours', 'Closing Hours')):
        values['tourism_hours_status'] = 'verify_required'
    elif old is None:
        values['tourism_hours_status'] = 'not_supplied'
    if old is None:
        values.update(slug=normalized_name(source['Place Name']).replace(' ', '-'), image_url=None, status='draft')
    return values


def build_plan(inventory, review, source_rows, *, aliases=ALIASES):
    require(len(source_rows) == len(review['records']), 'CSV/report count mismatch.')
    rows = inventory['rows']
    by_name = {normalized_name(row['name']): row for row in rows}
    by_slug = {row['slug']: row for row in rows}
    categories = proposed_categories(review)
    by_category = {category['label']: category for category in categories}
    entries = []
    claimed = set()
    proposals = []
    for source, record in zip(source_rows, review['records']):
        name = source['Place Name'].strip()
        require(name == record['name'], 'CSV/report row alignment mismatch.')
        old = by_name.get(normalized_name(name))
        identity = 'exact_normalized_name' if old else 'new_candidate'
        if old is None and name in aliases:
            old = by_name.get(normalized_name(aliases[name]))
            require(old is not None, 'Reviewed alias target missing from current inventory.')
            identity = 'proposed_alias_requires_owner_confirmation'
        if old:
            require(old['id'] not in claimed, 'Two CSV records propose the same destination ID.')
            claimed.add(old['id'])
        category = by_category[source['Category'].strip()]
        desired = desired_values(source, record, old, category)
        blockers = list(record['errors'])
        if identity == 'proposed_alias_requires_owner_confirmation':
            blockers.append('owner_confirmation_of_alias_identity')
        if category['proposed_key'] is None:
            blockers.append('category_key_collision_requires_owner_decision')
        slug_collision = old is None and desired['slug'] in by_slug
        if slug_collision:
            blockers.append('existing_slug_collision_requires_identity_review')
        if old is None:
            proposals.append(desired['slug'])
        ignored = [dict(id=row['id'], name=row['name'], status=row['status'], score=round(alias_score(name, row), 3),
                        disposition='manual_review_only_not_an_identity_assignment')
                   for row in rows if (old is None or row['id'] != old['id']) and alias_score(name, row) >= 0.72]
        changes = {key: dict(before=old.get(key) if old else None, after=value)
                   for key, value in desired.items() if old is None or value != old.get(key)}
        if old:
            require(not set(changes).intersection({'id', 'slug', 'created_at', 'updated_at', 'image_url', 'status'}),
                    'Update changes protected identity, image or status.')
        entries.append(dict(
            csv_record=record['record_number'], csv_line_start=record['csv_line_start'], name=name,
            classification='Existing - update' if old else 'New - proposed create',
            proposed_action='update' if old else 'create_draft_then_publish_after_validation',
            identity_basis=identity, owner_identity_approval_required=True,
            existing_id=old['id'] if old else None, existing_slug=old['slug'] if old else None,
            expected_updated_at=old['updated_at'] if old else None,
            expected_status=old['status'] if old else None,
            expected_row_sha256=rows_hash([old]) if old else None,
            original_row=old, proposed_values=desired, field_changes=changes,
            category_label=source['Category'].strip(), source_errors=record['errors'],
            unresolved_record_blockers=blockers, warnings=record['warnings'],
            other_name_candidates=ignored,
            proposed_slug_collision_id=by_slug[desired['slug']]['id'] if slug_collision else None,
            image_policy='preserve_existing_exactly' if old else 'null_until_separately_reviewed_photo',
            source_photo_reference=source['Picture / Photo Link'].strip(),
            final_status_proposal='published', ready_to_execute=False))
    require(len(proposals) == len(set(proposals)), 'Duplicate proposed new slugs.')
    require(not review['duplicate_normalized_names'], 'Duplicate CSV names.')
    archives = []
    for old in rows:
        if old['id'] not in claimed and old['status'] == 'published':
            archives.append(dict(id=old['id'], name=old['name'], slug=old['slug'],
                expected_updated_at=old['updated_at'], expected_status='published',
                expected_row_sha256=rows_hash([old]), original_row=old,
                proposed_status='archived', reason='Previously published record omitted from CSV by proposed identity mapping.',
                owner_explicit_approval_required=True, ready_to_execute=False))
    unchanged = [old for old in rows if old['id'] not in claimed and old['status'] != 'published']
    updates = [entry for entry in entries if entry['existing_id']]
    creates = [entry for entry in entries if not entry['existing_id']]
    final_counts = dict(inventory['status_counts'])
    final_counts['published'] -= len(archives)
    final_counts['archived'] += len(archives)
    for entry in entries:
        if entry['expected_status'] is not None:
            final_counts[entry['expected_status']] -= 1
        final_counts['published'] += 1
    coordinate_groups = defaultdict(list)
    for record in review['records']:
        coords = record['proposed_coordinates']
        if set(coords) == {'latitude', 'longitude'} and coords['latitude'] is not None:
            coordinate_groups[(coords['latitude'], coords['longitude'])].append(record['record_number'])
    return dict(
        review_only=True, executable=False, hosted_writes=0, target_project_ref=TARGET,
        inventory_validation='passed_owner_attested_project_not_independently_mcp_verified',
        project_identity_basis='Owner supplied export after Dashboard confirmation procedure; SQL literal is not identity proof.',
        inventory_exported_at=inventory['exported_at'], inventory_rows_sha256=rows_hash(rows),
        existing_total=len(rows), existing_status_counts=inventory['status_counts'],
        csv_total=len(entries), proposed_update_count=len(updates), proposed_new_count=len(creates),
        exact_name_update_count=sum(e['identity_basis'] == 'exact_normalized_name' for e in updates),
        alias_update_count=sum(e['identity_basis'] != 'exact_normalized_name' for e in updates),
        proposed_archive_count=len(archives), unchanged_count=len(unchanged),
        projected_final_status_counts_if_all_approved_and_resolved=final_counts,
        csv_records_requiring_corrections=[e['csv_record'] for e in entries if e['source_errors']],
        ready_to_execute_count=0,
        global_blockers=[
            'Separate explicit owner approval of exact record mapping, field diffs and every archive.',
            'Correct the invalid CSV records; regenerate and approve the package against the new CSV hash.',
            'Review category registry keys, collision and legacy-interest relationships; coordinated schema/RPC/runtime changes not installed.',
            'Operating-days field and metadata/audit RPC allowlists require reviewed implementation and separate schema approval.',
            'Fresh target/schema/row-version preflight immediately before any approved operation; owner export is a point-in-time snapshot.',
            'Use authorized guarded Admin mutation and status flows with audit logging; no direct owner DML or forged auth claims.',
            'Live authentication and hosted writes remain separately gated; remote deployment remains NO-GO.'
        ],
        records=entries, proposed_archives=archives, unchanged_records=unchanged,
        proposed_category_registry=categories,
        exact_shared_coordinate_groups=[dict(latitude=coord[0], longitude=coord[1], csv_records=ids,
            disposition='Colocation review only; never merge identities based on coordinates.')
            for coord, ids in coordinate_groups.items() if len(ids) > 1],
        automatic_deletes=[], evaluation_manifest_changed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='local_catalog/production-catalog-change-set.review.json')
    args = parser.parse_args()
    export_path = ROOT / 'local_catalog/production-destinations-owner-export.json'
    source_path = ROOT / 'data/imports/rosago_pois_import_source.csv'
    require(hashlib.sha256(source_path.read_bytes()).hexdigest() == SOURCE_HASH, 'CSV changed: review source before regenerating.')
    inventory = validate_inventory(read_json(export_path))
    review = inspect_csv(source_path)
    require(review['record_count'] == 98 and tuple(review['columns']) == CSV_COLUMNS, 'Reviewed CSV inventory changed.')
    reader = csv.DictReader(io.StringIO(source_path.read_text(encoding='utf-8-sig'), newline=''))
    result = build_plan(inventory, review, list(reader))
    result.update(prepared_at=datetime.now(timezone.utc).isoformat(),
                  source_csv_sha256=SOURCE_HASH, export_file_sha256=hashlib.sha256(export_path.read_bytes()).hexdigest())
    output = Path(args.output).resolve()
    require(output.parent == (ROOT / 'local_catalog').resolve() and output.name.endswith('.review.json'),
            'Output must be a new .review.json inside local_catalog.')
    write_new(output, result)
    print(json.dumps({k: result[k] for k in ('existing_total', 'existing_status_counts', 'proposed_update_count',
          'proposed_new_count', 'proposed_archive_count', 'unchanged_count', 'csv_records_requiring_corrections', 'ready_to_execute_count')}, indent=2))


if __name__ == '__main__':
    main()
