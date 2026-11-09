# Local destination catalog — offline review only

> Current actual-production publication package: [production-publication/README.md](production-publication/README.md). Fresh destination/schema/Storage evidence passes without drift; the exact 65-record atomic cutover/containment is locally tested. Publication remains blocked by end-to-end provider/Auth restore protection and final approval.

> Current same-application preview: [INTEGRATED_CATALOG_PREVIEW.md](INTEGRATED_CATALOG_PREVIEW.md). Run normal `--app app` with `ROSAGO_CATALOG_PREVIEW=true` to inspect all 98 on `/places`; simulation is `/preview/planner`. The separate preview server is no longer required.

> To visually inspect all 98 destinations and local images in the User UI, use [LOCAL_CATALOG_PREVIEW.md](LOCAL_CATALOG_PREVIEW.md). The separate loopback preview does not change the normal Supabase-backed catalog or authorize publication.

> Current accepted-location first batch and content approval tables: [FIRST_PUBLICATION_BATCH_APPROVAL.md](FIRST_PUBLICATION_BATCH_APPROVAL.md). 81 locations accepted; 65 initial content candidates, 16 held for content decisions, 17 unresolved-location Draft holds. Hosted publication remains unapproved.

> Current owner research evidence and exception-only work: [OWNER_RESEARCH_REUSE_REVIEW.md](OWNER_RESEARCH_REUSE_REVIEW.md). Original research is recognized; blank older approval worksheets do not require re-researching all 98 destinations.

> Current publication gates and owner decisions: [FINAL_PUBLICATION_DECISION_CHECKLIST.md](FINAL_PUBLICATION_DECISION_CHECKLIST.md). This supersedes older missing-preflight/all-98-Published statements. No hosted operation is approved by these review documents.

> Latest local image UI work: [LOCAL_IMAGE_INTEGRATION_COMPLETION.md](LOCAL_IMAGE_INTEGRATION_COMPLETION.md), including the 14 missing photos and final 98-row image disposition. No hosted image changes occurred.

> Latest evidence: [SCHEMA_AND_IMAGE_INTEGRATION_REVIEW.md](SCHEMA_AND_IMAGE_INTEGRATION_REVIEW.md). The owner schema export is now validated, and downloaded images are preserved/staged. Earlier missing-preflight statements below are historical. Overall hosted publication remains unqualified.

> Current mapped-only policy and package: [MAPPED_PUBLICATION_POLICY.md](MAPPED_PUBLICATION_POLICY.md). Earlier all-98-Published projections are superseded.

> Current mapping/correction decisions:
> [CATALOG_DECISIONS_AND_CORRECTIONS.md](CATALOG_DECISIONS_AND_CORRECTIONS.md).
> Local gated implementation and unqualified migration preparation:
> [CATALOG_EXTENSION_READINESS.md](CATALOG_EXTENSION_READINESS.md).

> Latest owner-export comparison and proposed record changes:
> [PRODUCTION_CATALOG_CHANGE_SET.md](PRODUCTION_CATALOG_CHANGE_SET.md).
> The complete 50-row production export has been validated offline. Its target
> is owner-attested; MCP authentication remains unqualified. Prior target and
> historical findings are preserved in [PUBLICATION_REVIEW.md](PUBLICATION_REVIEW.md).
> The running app was observed using the original production project. This
> folder's init/plan manifest remains evaluation-pinned; do not relabel production
> data as evaluation data or bypass that pin. Production review artifacts are
> proposals requiring corrections, identity/archive approval and schema/runtime
> qualification before any hosted application.

This directory is separate from historical publication inputs. The live source
remains the **same Supabase `public.places` table used by Admin and User**.
Neither application reads this directory. No synchronization or hosted write
mechanism is installed here. Remote deployment remains **NO-GO**.

There is intentionally no `snapshot.json` or `catalog.json` yet. No authorized
current snapshot has been obtained. Do not fill this directory from the archived
28-place list, an old backup or a published-only export.

For the user-supplied CSV, see [CSV_IMPORT_REVIEW.md](CSV_IMPORT_REVIEW.md).
The `inspect-csv --source data/imports/rosago_pois_import_source.csv` command
performs offline field checks and prepares identity-review candidates only when
an authorized all-status snapshot is available locally. Its report is not a
replacement snapshot or a catalog import; unmatched names are never auto-created.

## First obtain separate authorization

Before any hosted read, the owner must authorize a destination-only export from
evaluation project `jfaufpfzfhysqkhcdsrs`, with independent project verification,
all-status visibility and complete pagination or a consistent read-only snapshot.
Include Draft, Published and Archived rows; a status may legitimately have zero
rows. Record the actual total and each status count. Do not export Auth accounts,
memberships, sessions, secrets, private relationship tables or image bytes.

The existing anonymous/public exporter is published-only and follows `.env`;
it is not sufficient for this workflow. Historical full backups are not current
or evaluation-target proof. Do not contact production for this local catalog.

## Snapshot contract

After authorization and export verification, save `snapshot.json` as an object:

| Field | Required value |
| --- | --- |
| `schema_version` | `1` |
| `project_ref` | `jfaufpfzfhysqkhcdsrs` |
| `table` | `public.places` |
| `scope` | `all_publication_statuses` |
| `all_statuses_verified` | `true`, only after the export's scope is verified |
| `authorization_ref` | Actual owner approval/evidence reference; no credentials |
| `exported_at` | Actual timezone-qualified export timestamp |
| `row_count` | Exact number of destination rows |
| `status_counts` | Exact integer counts for `published`, `draft`, `archived` |
| `rows_sha256` | SHA-256 of canonical `rows` JSON |
| `rows` | Complete records, with the 20 fields below |

Fields: `id`, `slug`, `name`, `description`, `category`, `address`, `latitude`,
`longitude`, `image_url`, `status`, `created_at`, `updated_at`, `tourism_type`,
`tourism_category`, `tourism_opening_hours_raw`, `tourism_closing_hours_raw`,
`tourism_hours_status`, `tourism_source`, `tourism_source_row`, `environment`.

Canonical hashing uses UTF-8 JSON, sorted object keys, separators `(',', ':')`,
`ensure_ascii=False`, `allow_nan=False`, preserving row order. The offline helper's
`rows_hash` implements this format. Record a separate original export-file hash
in the approval evidence; do not change snapshot bytes after review.

Metadata and hashes check local integrity; **they cannot prove actual owner
authorization, project identity, completeness or current hosted state**. Verify
these against trusted export evidence before accepting the file. Do not fabricate
`all_statuses_verified` or an approval reference to satisfy validation.

## Local commands after the snapshot is approved

From the repository root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe .\tools\local_destination_catalog.py init
```

This validates the snapshot and creates `catalog.json` exclusively from its full
records. It refuses to overwrite an existing catalog. The snapshot must be no
older than 24 hours and no more than five minutes future-dated. Keep snapshots
immutable; obtain and separately review a fresh export when the baseline is stale.

Edit `catalog.json` in VS Code. Its `records` list contains existing records.
Keep each record's UUID, slug, `created_at` and `updated_at` unchanged. Alter the
intended data fields only. An unknown existing UUID is an error, never an insert.

Stage genuinely new records in the separate `new_records` list. Each has the
same destination fields **except** `id`, `created_at`, `updated_at`, which are
server-assigned later. New records must explicitly have `status: "draft"`.
Their slug is a proposal, checked for collisions, not an assigned hosted identity.
The existing create RPC generates its own identity/slug; any future approved
creation must reconcile the actual returned identity using a fresh snapshot.

Generate a review-only plan:

```powershell
.\.venv\Scripts\python.exe .\tools\local_destination_catalog.py plan
# Optional new local evidence file; existing files are never overwritten:
.\.venv\Scripts\python.exe .\tools\local_destination_catalog.py plan --output .\local_catalog\plan.json
```

The tool has **no apply, network, SQL, login or credential-loading path**.
Only explicit `init`/`--output` commands write local files. Snapshots, editable
catalogs and generated JSON plans are ignored by Git by default.

## Identity and omission safeguards

- Compare IDs, slugs and normalized names against the entire snapshot, including
  existing records omitted from the editable file and other staged records.
- Normalize names using Unicode compatibility/case/accent normalization,
  punctuation/whitespace handling and apostrophe/ampersand normalization.
  Collisions stop planning for manual identity review; records are never merged.
- Matching UUIDs produce updates with original `expected_updated_at`, never new
  records. UUID/slug/version drift and duplicate IDs/slugs/names are rejected.
- Existing snapshot name collisions also stop initialization. Distinct venues
  with similar names need human review, not automatic deletion or renaming.
- Missing records are reported as **preserved**. No delete/archive operations are
  generated from omission, even if `records` is empty.
- Status edits are explicit proposed updates requiring separate publication
  review; they never automatically execute a publish/archive/restore action.
- Name normalization is not fuzzy matching or proof that two venues are distinct.
  Aliases, spelling changes and real-world identity still need human review.

Before any future application, separately authorize the exact evaluation changes,
recheck live identities/versions and duplicate candidates, preserve stable IDs,
and retain existing Admin validation, audit logging and publication safeguards.
The offline plan is not a current-state guarantee or execution approval.
