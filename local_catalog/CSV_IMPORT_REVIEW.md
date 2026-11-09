# CSV intake — offline validation and matching plan

> The later [publication review](PUBLICATION_REVIEW.md) supersedes this document's
> fixed-seven-category mapping proposal. The new design uses an extensible
> registry. CSV field findings still apply; current production inventory is blocked
> by MCP authentication and must not be replaced with historical or evaluation data.

Source verified: `data/imports/rosago_pois_import_source.csv`.
It is accessible, 38,653 bytes, valid UTF-8 without BOM, with 98 logical records.
SHA-256: `c55ed7076b59d611bc57eb0d59b0c6c425b301e4999655b01a17a9a8ca87ed2a`.
The source has not been edited. Quoted multiline fields are parsed as single
records; the report includes logical record numbers and physical line ranges.

**Current report:** `csv-review-c55ed7076b59-v2.json` in this directory.
The earlier `csv-review-c55ed7076b59.json` is a preliminary report superseded by
v2: the three literal `N/A` photo placeholders are missing optional values, not
invalid URLs. Both reports are local evidence, not editable catalogs or imports.

No current authorized `snapshot.json` or initialized `catalog.json` is present.
**No live matching has been performed. No record is classified as a confirmed
new destination. Import remains blocked.** Remote deployment remains NO-GO.

## Columns and proposed mapping

| CSV column | Proposed treatment, subject to review |
| --- | --- |
| Place Name | `name`; normalized only for matching, not silently renamed |
| Type | `tourism_type`: Local/Common; missing values do not erase existing values |
| Category | Preserve as `tourism_category`; separately map 73 distinct trimmed labels to RosaGo's seven supported categories |
| Environment | `environment`: Indoor/Outdoor/Mix of Both |
| Latitude / Longitude | Propose decimal coordinates only for valid numeric/hemisphere pairs; no swaps, guessed pins or automatic corrections |
| Days of the Week | Preserve source text; `public.places` has no dedicated day-of-week column, so agree a representation before any application |
| Opening Hours / Closing Hours | Preserve original text in the raw Tourism hour fields; no inferred schedule or verified-hours claim |
| Description / Address | Validate required text and limits; blank source values must not overwrite existing content |
| Picture / Photo Link | Reference for separate photo review; do not automatically place listing/share URLs in `image_url` or upload anything |
| Unnamed 13th column | 81 checkmarks and 17 blanks. Meaning requires confirmation; never treat it as publication status or execution approval |

The CSV supplies **no UUID, slug, current row version or publication status**.
Do not derive publication from Local/Common, an Environment value or a checkmark.

## Validation findings

- All 98 rows have 13 columns. No duplicate normalized names were found **within
  this CSV**; that does not establish uniqueness against Supabase or aliases.
- Six rows have blocking field errors:

| Logical record | CSV starting line | Destination | Required review |
| --- | --- | --- | --- |
| 2 | 3 | Nuvali Lakeside / Park | Latitude contains an east-longitude hemisphere value |
| 10 | 11 | WalterMart Santa Rosa | Longitude has a north-latitude hemisphere suffix |
| 56 | 76 | Nuvali Sand Courts | Missing description |
| 58 | 78 | Winner Badminton Court | Missing description |
| 59 | 79 | Court Zero Pickleball Court | Missing description |
| 60 | 80 | Infinite Badminton & Sports Center | Missing description |

- 13 rows have no coordinate pair; the existing catalog permits null pairs, but
  they cannot supply map pins. Missing CSV coordinates must not clear existing pins.
- 63 rows lack Days of the Week. 24 rows have multiline or 24-hour hour strings;
  preserve them as raw evidence rather than flattening them to one interval.
- 84 external photo links require review. Eleven fields are blank and three are
  `N/A`; missing optional photos must not remove existing images.
- One Type is missing. Three Type values and several other cells have outer
  whitespace; trimming proposals do not modify the original CSV.
- The 73 category labels and the unnamed marker column still need explicit
  decisions. No category inference or schema change was performed.

Detailed per-record findings, counts and proposed coordinate parses are in v2.
Even rows without field errors are not ready for import while these decisions
and identity checks remain outstanding.

## Duplicate-matching plan

1. Obtain separate approval for a destination-only, current, all-publication-status
   snapshot from evaluation project `jfaufpfzfhysqkhcdsrs`. Confirm actual target,
   complete counts/pagination, authorization evidence, original export integrity
   and the existing local snapshot contract. Do not use a public-only export or
   historical archived JSON as an authoritative baseline.
2. Use the existing `init` command only after that snapshot passes validation.
   This copies complete current records, including Draft and Archived records.
3. Since this CSV has no identities, compare normalized names across the full
   baseline first. Exact matches produce **review candidates** carrying the
   existing UUID, slug and `expected_updated_at`, never automatic writes.
4. Review aliases, parenthetical/branch names, addresses and provenance manually.
   For example, alternate Nuvali/Solenad labels cannot safely be classified as
   new records just because their normalized text differs. No links were opened.
5. Confirm a one-to-one source-to-UUID mapping. Conflicting/repeated candidates
   stop for resolution; do not merge records or allocate replacement UUIDs.
   The inspector automatically lists exact normalized-name candidates only
   when a validated authorized snapshot is locally available. Alias/address
   reconciliation remains manual, not fuzzy auto-matching.
6. Overlay only explicitly approved field changes onto those existing records.
   Preserve IDs, slugs, timestamps and any existing data absent from this CSV.
   Preserve current publication status unless a separate publication change is
   specifically approved. Unknown identity is not permission to create a record.
7. Stage only genuinely new, separately confirmed venues in `new_records` as
   Drafts, following the existing tool's server-assigned-identity contract.
8. Run the existing JSON `plan` command. It checks IDs, slugs and normalized names,
   preserves omitted baseline records, and produces no delete/archive operations
   from missing CSV rows. Live versions and duplicate candidates must be rechecked
   before any separately approved hosted application.

## Repeat offline inspection

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe .\tools\local_destination_catalog.py inspect-csv --source .\data\imports\rosago_pois_import_source.csv
```

Use `--output .\local_catalog\csv-review-next.json` for a new UTF-8 JSON report;
the helper refuses to overwrite existing files or snapshot/catalog/manifest files.
No snapshot is required for CSV-only validation. If a local snapshot is present,
it must pass the existing authorization-metadata, all-status, count/hash, target
and freshness checks before identity candidates are listed. These local checks
do not themselves prove the export's authorization or current hosted state.

## Changes and tests

- Extended `tools/local_destination_catalog.py` with `inspect-csv`, reusing the
  existing name normalization and snapshot validation. Existing init/plan paths
  remain. No apply, SQL, network, link-fetch, credential or sign-in path was added.
- Updated `tests/test_local_destination_catalog.py`: **15 tests passed**, including
  malformed columns, wrong-hemisphere coordinates, unchanged source bytes/hash,
  quoted multiline input, source duplicates, exact-match candidates, unmatched
  aliases, optional N/A photos and unsafe links. Tests block network access and
  use synthetic input; no SQL is executed.
- Added this review document, the two local JSON reports and the README entry.
  The source CSV is user-supplied and unchanged. No catalog or snapshot was created.

No hosted project was contacted or modified. No SQL, live sign-in, deployment,
commit or push occurred. Existing application/runtime and archived files are unchanged.
