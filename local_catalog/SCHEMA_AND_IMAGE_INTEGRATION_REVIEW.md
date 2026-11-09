# Schema preflight and image integration: current review

> Local UI integration follow-up: [LOCAL_IMAGE_INTEGRATION_COMPLETION.md](LOCAL_IMAGE_INTEGRATION_COMPLETION.md).
> Shared placeholder/fallback and Admin/User offline coverage are complete;
> image uploads, assignments and publication remain unapproved.

The owner-operated production schema preflight **passed validation**. MCP is not
used or required for this workflow. No hosted schema/data/Storage changes,
sign-ins, deployments, commits or pushes occurred. Remote deployment is **NO-GO**.

## Evidence validated

Target: **brnkigrrqdrywahvcbvc**, attested by the owner-selected Dashboard export.
The file reports the postgres role, a read-only transaction and export time
`2026-11-08T02:40:04.739117+00:00`. Its SHA-256 is
`7294b7da8e64d778bd500f2fe6dc9effed8bd0f142205504166bccd39cbe889e`.

Validated 23 function definitions and body hashes, argument identities,
SECURITY DEFINER/INVOKER modes, owner/search_path/raw execution ACL evidence,
20 destination columns, 20 constraints, 4 scoped RLS policies, 25 direct table
grants and 8 indexes. RLS is enabled on the three inspected tables. Mutation
inner/audit wrapper match the reviewed environment/photo baselines; ordinary
roles lack direct write grants in the supplied table-grant evidence.

Two real findings must not be hidden by assumptions:

- The migration-history relation is reported **absent**. This is not proof of
  an empty migration history and does not authorize creating/repairing one.
- The production snapshot does **not** contain the evaluation provider-session
  helper or restrictive guards. The two projects have different security
  states. Do not copy/rerun evaluation security SQL on production. The new
  location-verification RPC now explicitly fails closed if the caller-bound
  provider authority is unavailable or rejects the caller.

The exported destination schema also lacks the older Published-coordinate CHECK.
This is consistent with earlier Published rows lacking coordinates; the new
mapped-only invariant must be introduced through an approved cutover, not by
pretending the old constraint exists.

The snapshot remains point-in-time. The final operator must check fresh target,
schema and row versions before any separately approved application. This review
does not claim that account/member/destination values were freshly re-exported
by the schema-only query; their existing owner export is preserved separately.

## Migration qualification

`catalog_extension.production-bound-v2.review.sql` pins every exported function
definition, owner and raw execution ACL, plus every exported destination
constraint and inventory count. Unexpected drift aborts the transaction. It
prepares an extensible category registry/FK, operating days, bounded provenance,
guarded mutation changes, category-cycle enforcement and duplicate-name index.
It does not import destinations, change statuses, replace photos or alter
existing authorization/audit wrappers. It remains **review-only, not approved**.

**25 native PostgreSQL checks passed** using an owner-export-derived schema
clone, cached container, networking disabled, no exposed ports and synthetic
rows only. The owned container/volume was removed. Results:
[catalog-production-baseline-local-qualification-v2.json](catalog-production-baseline-local-qualification-v2.json).

Seven CHECK expressions regroup nested AND terms when PostgreSQL reloads their
exported DDL. The qualifier proves the parsed expressions equivalent after
ignoring source offsets and associative AND nesting, then adjusts only those
seven guard fingerprints **in its in-memory local clone variant**. The production
review SQL retains the exact exported hashes; no production drift check was
relaxed. Tests reject weaker/different conditions.

Positive location-verification cases use a clearly labelled **synthetic
provider helper in the disposable clone**. They do not establish a working
production provider authority. The missing-helper rejection is tested against
the actual exported baseline before introducing that fixture. Overall hosted
publication qualification therefore remains **false**.

The final mapped-only migration still needs the provider-authority prerequisite,
registry/correction approvals and an atomic/maintenance-gated cutover. Installing
the restrictive visibility guard hides legacy unverified Published records;
that impact requires explicit approval. Validate the final publication CHECK
after every legacy Published row is verified or explicitly moved to Draft or
Archived. Do not release a partially qualified staging state. Auth restore/replay
remains a separate unresolved deployment blocker.

## Downloaded images preserved

All **84 original files** remain byte-for-byte in
`static/images/destinations/`. None was moved, renamed, deleted or rewritten.
They decode as 72 JPEG and 12 PNG files. Separately generated sanitized inputs
are in `local_catalog/image-staging/`, with correct extensions, stripped metadata
and existing dimension/upload-size bounds. Visible image content/watermarks
were not cropped or replaced; no photos were generated or downloaded.

There are **83 unique staged files**, because two source names contain identical
bytes. Every staged input passes the existing `admin_photo_service.prepare_photo`
validator; the 5 MiB upload rule and strict Storage URL contract were unchanged.
`image-upload-payloads.review.json` records the expected post-validator bytes,
since staged JPEG input and final re-encoded upload hashes may differ.

Important review cases:

| CSV record | Finding | Handling |
| --- | --- | --- |
| 3 Solenad | `.png` original contains JPEG data | Original preserved; correctly typed JPEG copy staged |
| 21 Chowking Balibago | Original 6,157,639 bytes exceeds upload limit | Separate 2,196,475-byte input staged; existing hosted image remains unchanged |
| 22 Chowking Bayan | Original 6,355,567 bytes exceeds upload limit | Separate 2,255,735-byte input staged |
| 56 Nuvali Sand Courts | Image depicts indoor badminton and duplicates #58 | Do not assign to outdoor sand-court destination |
| 58 Winner Badminton Court | Same bytes as #56; venue identity unconfirmed | Hold assignment pending owner confirmation |
| 10 WalterMart | Filename says Walmart; visible photo says WalterMart/Sta. Rosa | Brand is visible, but confirm branch; not coordinate evidence |

No local image matches CSV #65, #66, #67, #70–78, #80 or #81: **14 records**.
Keep image NULL/existing neutral placeholder unless a matching image is supplied
and approved. Missing photos alone do not determine publication; verified
coordinates and the other required data/authorization gates do.

The three existing hosted covers (Enchanted Kingdom, Chowking Balibago, Santa
Rosa City Auditorium) remain preserved. No new image URL is invented or written.
All uploads and audited image assignments require separate explicit approval
and the existing guarded Admin flow; no owner DML or weaker static-path/URL
allowlist is introduced. See the full
[98-record image review](DESTINATION_IMAGE_REVIEW.md) and
[image manifest](destination-images.review.json).

## Updated publication package

Use [production-mapped-publication-v4.review.json](production-mapped-publication-v4.review.json).
It binds the existing per-record UUIDs/row versions, schema evidence and image
review without changing any image_url or status in Supabase. No completed CSV
validation or destination matching was repeated. The original source/export
and earlier review JSON remain preserved.

| Current plan status | Count |
| --- | ---: |
| CSV pairs that pass numeric syntax/range checks | 83 |
| Proposed stored-pair reuse requiring confirmation | 3 |
| No matching pair available | 12 |
| Approved record-bound geographic verification evidence | 0 |
| Ready for publication | **0** |
| Held Draft in the review plan | **98** |

The 35 currently hosted Published records were not changed. The plan's 28
matched Published-to-Draft proposals and seven archives are explicit,
approval-required transitions, not automatic actions. No photo, filename,
numeric range or prior publication status establishes geographic verification.

Remaining owner decisions: identity/location evidence, the ten aliases and
seven archives, four missing descriptions (#56/#58/#59/#60), tourism type #87,
category key/parent decisions and proposed image assignments. No descriptions,
hours or coordinates were invented to resolve them. Existing security, IDs,
images and successful Linux build evidence remain preserved.
