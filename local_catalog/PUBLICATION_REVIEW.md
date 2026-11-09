# Updated CSV catalog: pre-application review

> Historical/pre-export review, retained for traceability. The owner export is
> now validated; use [PRODUCTION_CATALOG_CHANGE_SET.md](PRODUCTION_CATALOG_CHANGE_SET.md)
> and its linked per-record JSON for current counts and proposals. The older
> 18/16/64 heuristic comparison below is superseded, not an execution plan.

## Target and authorization boundary

The existing owner-run Flask process listening on localhost:5000 was observed
using **production `brnkigrrqdrywahvcbvc`**, with evaluation mode disabled. Both
Admin and User use the same configured Supabase project and `public.places`.
The earlier evaluation configuration check was offline and did not save settings.
No credentials were printed or copied into this report.

The current request authorizes a read-only destination inventory. It does not
authorize production writes. The configured production MCP is project-scoped
and has `read_only=true`; its OAuth refresh failed before a database query could
run. Owner-selected reconnection remains unqualified; see
[connector diagnosis and owner export](MCP_RECONNECT_AND_OWNER_EXPORT.md).
No current database counts,
schema definitions, images or row versions have been verified in this review.
Do not substitute the evaluation project or use application credentials to
bypass the connector failure.

The existing `local_catalog/manifest.json` remains evaluation-pinned. The
production review files below are separate, non-executable evidence. They must
not be passed off as an evaluation snapshot or applied using that manifest.
Reconfirm the running target before any future operation.

## Offline findings

Source: `data/imports/rosago_pois_import_source.csv`, SHA-256
`c55ed7076b59d611bc57eb0d59b0c6c425b301e4999655b01a17a9a8ca87ed2a`.
The source is unchanged: 98 records, 13 columns, 73 category labels.

The per-record report is
[production-publication-review-v2.json](production-publication-review-v2.json).
It compares names against the public-field historical inventory from
2026-11-06, not against the current database. The earlier unversioned report is
preliminary and superseded by v2.

| Historical comparison only | CSV records |
| --- | ---: |
| Exact normalized name; verify existing identity | 18 |
| Possible alias; manual identity review | 16 |
| No candidate; not yet confirmed new | 64 |

Eight historical IDs have candidates from multiple CSV rows. Resolve these
before assigning IDs. Nine historical non-archived records have no heuristic
candidate; they are review candidates, not confirmed current omissions. Thirteen
already-archived historical records are listed separately. No automatic update,
creation, archive or deletion is proposed. **Zero records are approved or ready
for publication by this report.** Confirmed update/new counts remain unknown.

Six records need field corrections:

| CSV record | Place | Issue |
| --- | --- | --- |
| 2 | Nuvali Lakeside / Park | Latitude has an East hemisphere indicator |
| 10 | WalterMart Santa Rosa | Longitude has a North hemisphere indicator |
| 56 | Nuvali Sand Courts | Missing description |
| 58 | Winner Badminton Court | Missing description |
| 59 | Court Zero Pickleball Court | Missing description |
| 60 | Infinite Badminton & Sports Center | Missing description |

Thirteen records lack both coordinates; 63 lack operating days; 24 use complex
hours text that cannot safely be reduced to one interval. Eighty-four photo
links need source/format/rights review; blank or N/A photos must not erase
existing images. One tourism type is absent. The unnamed checkmark column is
not a publication instruction. There are no duplicate normalized CSV names,
which does not establish uniqueness against current destinations.

## Required coordinated changes; not applied

The checked-in schema and application enforce seven category keys. Removing a
form restriction alone would leave database RPCs, User browsing, map markers,
saved interests, insights and recommendations inconsistent.

Prepare an extensible category registry with stable keys, display labels and
reviewed legacy relationships. Retain the seven existing keys for existing
preferences and drafts; do not force the CSV into those seven categories.
The report proposes 73 labels for review, not a new fixed enum. `Resort /
Swimming Pool` and `Resort Swimming Pool` normalize to the same proposed key;
both keys are withheld until the owner resolves the collision. No category
parent relationships have been invented.

Replace the fixed category CHECK with validated registry references only after
reviewing current rows and live definitions. Update the category validators,
guarded Admin RPCs, itinerary validation functions, Admin inputs/filters,
insights, User browse/map/preferences and recommendation matching together.
Keep the limit on selected interests separate from the number of supported
categories. Preserve existing provider checks, RLS, Admin authorization,
execution permissions and audit logging. Category creation needs a real
authorized management path, not arbitrary unvalidated client text.

The existing model already has tourism type, environment, coordinates, address,
description and raw opening/closing hours. Add a bounded nullable
`operating_days_raw` field and include it in models, projections, guarded RPC
allowlists, forms and audit details. Preserve raw complex schedules as
unverified text; do not invent opening-time feasibility. Final migration SQL
requires fresh schema/function/grant verification and separate approval.

Category changes also affect curated weather identity metadata. Reconcile
verified identities explicitly; do not weaken identity checks or infer weather
exposure from a category label. The recommendation engine currently accepts
at most 100 candidates. Test complete pagination and deterministic selection
for the final published set, including pre-existing records retained outside
the 98-row CSV; do not assume the final set is at most 98.

## Publication sequence for subsequent approval

1. Reconnect the existing read-only production MCP and verify its returned
   project URL. Obtain a consistent, complete all-status `public.places`
   inventory including IDs, slugs, images and timestamps. Read current relevant
   constraints, indexes, guarded RPC definitions, grants, policies and migration
   history. No Auth accounts or session data are needed for this inventory.
2. Match exact IDs first, then verified slugs and normalized names. Check aliases,
   addresses and branches manually. A candidate name alone cannot authorize an
   update. Resolve every shared candidate ID and check current duplicates.
3. Produce a fresh per-record diff classified Existing/update, New/create,
   Missing/review archive, Ambiguous/manual or Invalid/correct. Preserve matched
   IDs, slugs, created timestamps and existing images. Blank source fields do
   not silently erase existing values. Missing descriptions may reuse verified
   existing text only after identity confirmation. New records need valid data.
4. Review the coordinated local category/operating-days implementation and
   synthetic regression tests. Separately approve any target-specific schema
   changes only after inspecting their exact SQL, security and rollback plan.
5. Approve an explicit list of creates, updates and publication transitions.
   Omitted destinations remain unchanged unless separately approved for
   archiving. Create genuinely new records as drafts through existing guarded
   Admin behavior; preserve audit trails and server-assigned identities. Include
   concurrency-safe duplicate protection after reviewing existing duplicates.
6. Recheck source hashes, target, row identities and update timestamps immediately
   before any approved write. Stop on drift or errors; do not blindly retry.
   Updating an already-published record makes its new content visible at once;
   approve that visibility timing explicitly. A batch requiring all-or-none
   behavior needs a separately reviewed transactional implementation.
7. Verify exact approved changes and audit records read-only. Publish only the
   approved, validated IDs using existing Admin authorization. Never bypass
   that flow with forged auth claims, direct owner updates or service keys.

No write mechanism, executable migration or final production publication batch
has been prepared while the current inventory and schema remain unavailable.

## Acceptance gates

- Published records appear across User browsing, detail, map and itinerary
  recommendations with complete pagination. Draft/archived records remain
  hidden from ordinary User queries and direct API access under existing RLS.
- Every approved category works in Admin add/edit/filter/insights, User browse,
  map and recommendation matching. Legacy preferences and saved drafts remain
  valid. Unknown/inactive keys fail safely; output remains escaped.
- Matched IDs/images remain unchanged unless explicitly approved; missing CSV
  rows are untouched. Duplicate input, ambiguous branches and concurrent
  duplicate creation cannot silently create a second record.
- Operating days and raw hours round-trip without fabrication; invalid
  coordinates and missing required new-record data block publication.
- Guarded Admin create/update/status actions retain role checks, provider
  validation and complete audit information. Pagination and optimistic
  concurrency checks preserve existing behavior.
- Offline candidate/tool tests passed: **23 tests** across
  `test_publication_review.py` and `test_local_destination_catalog.py`. These
  qualify the offline review tooling, not a dynamic-category runtime release
  or hosted publication. No live sign-in has been performed.

Next owner action: follow the documented owner-operated read-only export
fallback while MCP authorization remains unqualified. Then the current inventory can be checked and the
final plan completed. Production schema/data changes and live authentication
still require separate explicit approval. Remote deployment remains **NO-GO**;
the independent Auth restore/replay security blocker is not resolved by this
catalog review.
