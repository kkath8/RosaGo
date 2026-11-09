"""Render the offline approval package as Markdown; no network or database access."""
import hashlib
from pathlib import Path

from tools.local_destination_catalog import read_json, require

ROOT = Path(__file__).resolve().parents[1]


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')


def render(plan):
    entries = plan['records']
    updates = [entry for entry in entries if entry['existing_id']]
    creates = [entry for entry in entries if not entry['existing_id']]
    lines = [
        '# Production catalog replacement — proposed change set', '',
        '**Review only. No hosted changes. No executable import or migration. Remote deployment NO-GO.**', '',
        'This supersedes the historical name-only comparison. The supplied owner export validates as a complete '
        'all-status destination inventory. Project identity is owner-attested through the Dashboard procedure, '
        'not independently established by a successful MCP connection.', '',
        f"Target: **{plan['target_project_ref']}**. Exported: `{plan['inventory_exported_at']}`.", '',
        f"Export file SHA-256: `{plan['export_file_sha256']}`.", '',
        f"Canonical exported rows SHA-256: `{plan['inventory_rows_sha256']}`.", '',
        f"Source CSV SHA-256: `{plan['source_csv_sha256']}`.", '',
        'The source files are unchanged. The exact per-record before/after values, preserved originals, '
        'UUIDs, slugs, expected update timestamps and row hashes are in '
        '[production-catalog-change-set.review.json](production-catalog-change-set.review.json). '
        'This JSON is a review artifact, not an input to the evaluation-pinned init/plan tool.', '',
        '## Inventory and proposed outcome', '',
        '| Status | Exported now | Proposed final, after all corrections and approvals |',
        '| --- | ---: | ---: |',
    ]
    for status in ('published', 'draft', 'archived'):
        lines.append(f"| {status.title()} | {plan['existing_status_counts'][status]} | "
                     f"{plan['projected_final_status_counts_if_all_approved_and_resolved'][status]} |")
    lines += ['', 'The 50 exported rows have all 20 expected fields, valid paired coordinates or NULLs, '
              'unique canonical UUIDs, unique slugs, unique normalized names, valid timestamps, and '
              'counts that agree with the complete row list. Transaction read-only is `on`, RLS is '
              'inactive for the export role, and unexpected status count is zero. No Auth or private '
              'session records were exported.', '',
              '**28 proposed updates** (18 exact normalized names and 10 explicit alias proposals), '
              '**70 proposed additions**, **7 proposed archives**, and **15 unchanged rows**. '
              'All aliases remain subject to explicit owner identity approval. No record is ready '
              'for execution while the correction and implementation gates below remain open.', '',
              '## Existing destinations to update', '',
              'All retain their existing UUID, slug, creation timestamp and image URL. '
              'Update timestamps are concurrency preconditions; the database must advance them normally. '
              'These updates keep publication status unchanged. Blank CSV optional fields preserve '
              'existing values. Original complex hours remain raw, with `verify_required` status; '
              'the source does not establish verified hours.', '',
              '| CSV record | CSV destination | Existing destination | Identity basis | Existing UUID |',
              '| ---: | --- | --- | --- | --- |']
    for entry in updates:
        basis = 'Exact normalized name' if entry['identity_basis'] == 'exact_normalized_name' else '**Alias: approve identity**'
        lines.append('| ' + ' | '.join(cell(v) for v in (entry['csv_record'], entry['name'],
                     entry['original_row']['name'], basis, entry['existing_id'])) + ' |')
    lines += ['', '## New destination candidates', '',
              'These have no assigned UUID. Create as Draft only after approval and validation; '
              'publish separately through the guarded Admin flow. Proposed slugs must be rechecked '
              'against a fresh inventory at creation time. New photos stay NULL until separately '
              'reviewed; CSV listing/share links are not silently imported as image URLs.', '',
              '| CSV record | Destination | Proposed slug | Outstanding source issue |',
              '| ---: | --- | --- | --- |']
    for entry in creates:
        issues = list(entry['source_errors'])
        if entry['proposed_values']['category'] is None:
            issues.append('Category key collision')
        if 'coordinates_not_supplied' in entry['warnings']:
            issues.append('No coordinates')
        if 'tourism_type_not_supplied' in entry['warnings']:
            issues.append('Tourism type not recorded')
        lines.append('| ' + ' | '.join(cell(v) for v in (entry['csv_record'], entry['name'],
                     entry['proposed_values']['slug'], '; '.join(issues) or 'Global review gates below')) + ' |')
    lines += ['', '## Previously published records proposed for archiving', '',
              'These are proposals for explicit approval, not automatic omission handling. '
              'Archive changes status only; retain the record, image, relationships and audit trail. '
              'Existing saved trips may reference these IDs and must not be deleted or rewritten. '
              'Review their behavior after archiving during offline acceptance.', '',
              '| Destination | UUID | Review note |', '| --- | --- | --- |']
    for entry in plan['proposed_archives']:
        note = ('Scope overlap with CSV #2: proposed reuse of Nuvali Park UUID and archival of this separate '
                'activity record requires explicit confirmation; no merge or relationship transfer.') if entry['name'] == 'Lakeside Activities (Nuvali)' else 'Not represented in CSV by the proposed mapping.'
        lines.append('| ' + ' | '.join(cell(v) for v in (entry['name'], entry['id'], note)) + ' |')
    lines += ['', 'Leave the two existing Drafts (Centennial Garden and City of Santa Rosa People\'s Park) '
              'and all 13 already-Archived records unchanged. Do not delete or revive archived synthetic records.', '',
              '## Corrections and identity decisions', '',
              '| CSV record | Required correction |', '| ---: | --- |',
              '| 2 | Nuvali Lakeside / Park: latitude incorrectly contains an East value outside latitude range. Supply a verified latitude and review both coordinates; do not swap or infer automatically. |',
              '| 10 | WalterMart Santa Rosa: longitude uses an N hemisphere suffix. Supply a verified longitude; do not silently change the suffix. |',
              '| 56 | Nuvali Sand Courts: supply description. |',
              '| 58 | Winner Badminton Court: supply description. |',
              '| 59 | Court Zero Pickleball Court: supply description. |',
              '| 60 | Infinite Badminton & Sports Center: supply description. |', '',
              'The proposed values retain existing coordinate pairs for #2 and #10, but their source errors '
              'still block execution. They are not marked corrected. Any source correction requires '
              'regenerating and reapproving the package under the new CSV hash.', '',
              '- Approve the ten alias mappings above and resolve the Nuvali Park / Lakeside Activities '
              'scope decision before finalizing the seven-archive list.',
              '- Treat Chowking Bayan (#22) separately from Chowking Balibago (#21). Restaurants inside '
              'malls remain distinct from the mall itself: Pizza Hut (#24), Gerry\'s Grill (#39), '
              'KFC (#88) and Nono\'s (#25) do not reuse mall IDs. McDonald\'s (#16) does not match Monde Nissin. '
              'The JSON preserves other heuristic candidates for review; no fuzzy match assigns an ID.',
              '- Exact CSV names and proposed new slugs have no duplicates or existing-slug collisions. '
              'This does not prove physical-place identity, address accuracy or branch scope. '
              'Shared coordinates do not prove duplicate destinations.',
              '- Exact coordinate groups: CSV #5/#24, #32/#36, #33/#34 and #35/#38. '
              'Arambulo (#44) and Gonzales (#46) also have nearly identical coordinates; confirm locations '
              'without merging the distinct records.',
              '- Thirteen CSV rows have no coordinates. Existing Target Mall (#90) keeps its stored '
              'coordinates; twelve new rows (#22, #87–89, #91–98) would have NULL pairs. '
              'They can remain unlocated records under current semantics, but full map/routing coverage '
              'is not established. Do not fabricate points.',
              '- Lolo Uweng Chapel (#87) lacks tourism type. Supply Local/Common or explicitly accept '
              'Not recorded; no type has been invented. Sixty-three rows lack days and 24 have complex '
              'hours strings; preserve unknown/raw schedule semantics.',
              '- There are 73 category labels. `Resort / Swimming Pool` and `Resort Swimming Pool` '
              'normalize to the same proposed key. Decide whether to merge the labels or give them '
              'distinct stable keys; #70/#72/#73 remain blocked. All category parent/legacy-interest '
              'relationships require review, not an invented taxonomy.',
              '- All three existing image URLs are preserved (Enchanted Kingdom, Chowking Balibago, '
              'Santa Rosa City Auditorium). Eighty-four CSV external photo references remain unverified; '
              'they will not replace images or trigger downloads/uploads. Blank/N/A photos never clear '
              'existing images. The unnamed checkmark column is ignored, not treated as approval.', '',
              '## Required application/schema preparation', '',
              'The current schema/RPC/runtime still enforce seven category keys. This package proposes '
              'extensible registry keys and an `operating_days_raw` field; these are not currently '
              'accepted mutation payloads. No migration is bundled or approved by this report. '
              'Before data application, implement and qualify the reviewed registry, legacy-interest '
              'relationships, Admin inputs/filters/insights, User browse/map/preferences and itinerary '
              'validators/recommendations together. Extend guarded metadata/provenance/operating-day '
              'RPC allowlists and audit details; preserve provider guards, RLS and grants. '
              'Read current target schema/functions/security definitions before preparing exact '
              'target-specific migration SQL for separate approval.', '',
              'Weather identity metadata must be reconciled for changed category/name identities '
              'without weakening its verified-identity checks. Existing metadata is unchanged. '
              'Recommendation eligibility is category-based with Local/NULL/Common ranking; '
              'publication does not imply every destination is selected for every itinerary.', '',
              '## Controlled publication sequence — conditional, not executable yet', '',
              '1. Confirm identities, Nuvali scope, all seven archives, category keys/relationships '
              'and field corrections. Regenerate this per-record package against the corrected CSV. '
              'Approve exact values and separately review any schema/application changes. Obtain '
              'separate approval for authenticated operator testing when the security gates permit it.',
              '2. Immediately before authorized writes, independently verify target, source/export '
              'hashes, complete current inventory and every affected row version/hash. Stop on drift '
              'and prepare a new diff. The old export cannot authorize changes to newer rows.',
              '3. Use the existing guarded, audited Admin mutation/status behavior. Stage 70 new '
              'Drafts with server-assigned UUIDs; verify them before any publication. Apply the 28 '
              'approved updates preserving IDs/slugs/images. Updating Published rows is immediately '
              'visible, so approve that timing explicitly. Do not use direct owner INSERT/UPDATE, '
              'forged request claims or service keys to bypass authorization and logging.',
              '4. The final 98 published records fit the current 100-candidate recommendation bound. '
              'Publishing all 70 additions first would temporarily reach 105 and must be avoided. '
              'Either review an authenticated audited transactional cutover, or explicitly approve '
              'a bounded staged cutover: after all corrections and Draft verification, archive the '
              'seven approved old records (35 to 28 Published), then publish the 70 new Drafts '
              '(28 to 98). The latter has temporary partial availability and requires separate '
              'timing/failure-handling approval; do not silently choose it or blindly retry after errors.',
              '5. Verify final counts (98 Published, 2 Draft, 20 Archived), exact approved IDs/values, '
              'no duplicates, three original image references, and complete mutation audit records. '
              'Verify User browse/detail/map pagination, published-only RLS, hidden Draft/Archived '
              'records, expanded-category recommendations, preserved saved-trip relationships and '
              'Admin edit/filter/status behavior. Geographic tests must retain explicit unknown '
              'coordinates rather than inventing feasibility.', '',
              'No account, permission, Auth, Storage, secret or hosted database change is performed '
              'by this review. The next approval is for the record/identity/archive decisions and '
              'the necessary local preparation; hosted application requires a refreshed, corrected '
              'and separately approved package. Remote deployment remains **NO-GO**.', '',
              '## Focused verification', '',
              '35 offline tests passed across `test_current_catalog_review.py`, '
              '`test_publication_review.py` and `test_local_destination_catalog.py`, with network '
              'connections blocked. Tests cover export scope/counts/role/read-only evidence, wrappers, '
              'duplicate identities, timestamps, alias proposals, blank/image/identity preservation, '
              'explicit archive proposals, draft-first creation, category collisions and shared '
              'coordinates. They do not qualify the unimplemented dynamic-category runtime or '
              'hosted writes. No live sign-in was performed.', '']
    return '\n'.join(lines)


def main():
    plan_path = ROOT / 'local_catalog/production-catalog-change-set.review.json'
    plan = read_json(plan_path)
    require(plan['review_only'] is True and plan['executable'] is False, 'Expected a review-only package.')
    for name, key in [('local_catalog/production-destinations-owner-export.json', 'export_file_sha256'),
                      ('data/imports/rosago_pois_import_source.csv', 'source_csv_sha256')]:
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == plan[key], 'Source evidence changed.')
    output = ROOT / 'local_catalog/PRODUCTION_CATALOG_CHANGE_SET.md'
    with output.open('x', encoding='utf-8') as stream:
        stream.write(render(plan))
    print('Wrote local_catalog/PRODUCTION_CATALOG_CHANGE_SET.md; no hosted operations.')


if __name__ == '__main__':
    main()
