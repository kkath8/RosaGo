# Owner-only catalog 98 — review only, not approved to apply

Target: production `brnkigrrqdrywahvcbvc`. No hosted changes, uploads, live
authentication or deployment are authorized. Original `production-publication/`
and completed images/mappings remain unchanged. This separate package does not
install provider/session/recovery infrastructure or depend on its helper.

## Scope and exact counts

Reconcile all 98 researched CSV entries to **28 existing UUIDs/slugs and 70 new
reserved UUIDs/slugs**. Keep the same first 65 Published and the remaining 33
Draft. Preserve the original 21 Published-to-Draft transitions: 14 are CSV Draft
matches, seven are older destinations outside the CSV. Preserve both original
Drafts and all 13 original Archived rows. No deletions or new archives.

| State | Published | Draft | Archived | Total |
|---|---:|---:|---:|---:|
| Accepted owner snapshot | 35 | 2 | 13 | 50 |
| Full 98-source outcome, conditional on content/mapping approvals | 65 | 42 | 13 | 120 |
| Schema-compatible subset as received, diagnostic ONLY | 65 | 35 | 13 | 113 |
| Containment after full release | 0 | 107 | 13 | 120 |

The 42 Drafts consist of 33 CSV destinations, seven legacy holds and two original
Drafts. The diagnostic subset contains only 91 CSV destinations, not all 98.
**Partial import is not approved and is not an automatic fallback.**

## Seven mandatory-field blockers

Draft is not a relaxed table schema. Name, description, address and category
remain required/nonblank. NULL coordinate PAIRS, photos, tourism metadata,
environment and operating-day text are supported where existing contracts allow.
No empty-string placeholders, dummy descriptions, fake coordinates or fake
unknown category are introduced. Four new rows currently fail description
NOT NULL/nonblank constraints; three new rows have no resolved category key:

| CSV | Destination | Required decision |
|---|---|---|
| 56 | Nuvali Sand Courts | Approve the existing supported description or supply one |
| 58 | Winner Badminton Court | Approve the existing supported description or supply one |
| 59 | Court Zero Pickleball Court | Approve the existing supported description or supply one |
| 60 | Infinite Badminton & Sports Center | Approve the existing supported description or supply one |
| 70 | Terrazas de Teodora Pavilion and Resort | Approve the existing resort category proposal or select a supported key |
| 72 | Summer's Place Resort | Same category decision |
| 73 | Popong Resort | Same category decision |

`required-content-decisions.review.json` preserves the four previously prepared,
source-supported descriptions and the existing proposed `resort-swimming-pool`
category under `attraction`. It asserts no overnight lodging or new opening hours.
All seven proposals remain **approved=false**.

`change-set.review.json` preserves those seven missing values and stops before
any destination changes. `change-set.with-proposed-resolutions.review.json`
shows the exact conditional full-98 outcome if those proposals are approved.
Neither is executable or approved. The corresponding two apply SQL variants
have independent installation and plan gates; never remove those manually.

The 10 alias mappings remain explicit approval items in
`alias-decisions.review.json`. Their existing IDs/slugs are reserved for updates,
never recreated. New UUIDv5 identities are deterministic from CSV hash and row,
not inferred venue facts; insertion rejects ID/slug/name collisions. Final
identity reconciliation still depends on approving the proposed aliases.

## Incomplete Drafts and Admin editing

Unresolved coordinate pairs are stored as **NULL/NULL**, including CSV 2, 10, 44
and 46; original stored and candidate pairs remain in the baseline/source review
for later confirmation. This clearing is an explicit field-change approval item,
not a geographic correction. Sound previously researched coordinates may stay
on Drafts but do not make them Published. No point is estimated or geocoded.

The 79-key registry reuses the existing researched category/parent proposals.
It is not approved automatically. The copied, separately gated category/schema
extension adds operating days and flexible categories while retaining mandatory
description/address/name rules, coordinate checks, existing Admin membership
checks and the audited Admin mutation wrapper. No optional field is made required.

With the approved registry and existing catalog rollout flags enabled, the real
Admin can list, open and edit all schema-valid Drafts, including those with NULL
coordinates, photos or tourism classifications. Description/category blanks
cannot reach `public.places`; they must be resolved first. Existing forms still
require those fields. Completing a Draft never automatically publishes it.

Restrictive visibility policies preserve Admin reads and hide all Draft/Archived
rows from anon/ordinary Users. Only the 65 explicitly evidenced records have
private publication-location evidence. Name/address/coordinate edits invalidate
that evidence; publishing any held Draft requires a separately reviewed future
verification operation. This package adds **no public verification/write RPC**.
It is not a promise that the current Admin Publish button can publish the 33
held entries before that workflow is qualified.

## Restricted owner authorization and truthful auditing

`apply*.review.sql` installs only a private, no-argument, fixed-plan
`rosago_owner_catalog98.apply()` function. It is SECURITY INVOKER, empty
search_path, and requires both session/current database principal `postgres`
and a serializable transaction. Private schema USAGE, table privileges and
apply/contain execution are revoked from PUBLIC, anon, authenticated and
service_role. The read-only location predicate is executable through stored
policy/constraint references; no private schema USAGE or write authority is
granted. No role/account/session changes or fake JWT claims are used.

This is owner-authorized maintenance using the database owner's existing
authority, not a public importer or a shortcut around normal Admin checks.
Normal Admin operations retain their membership checks, audit wrapper and ACLs.
No new public Admin mutation API is created. Existing Admin audit history is
unchanged. A separate private append-only-to-API operator ledger records all
105 changed/created destination rows (98 CSV rows plus seven legacy holds),
before/after values, actual database operator, batch hash and timestamps. It does
not falsely attribute owner SQL to a Supabase Auth user. These maintenance events
are not automatically displayed in the existing Admin Activity History UI.

The package does NOT fix stale Admin JWT or provider restore/replay risk. Existing
Admin writes remain subject to their current controls; they are not declared
revocation-safe by this maintenance route. Separate explicit acknowledgement
of that limited catalog-only scope is a release gate. All complete-application
deployment/security requirements remain outstanding and remote deployment NO-GO.

## Images, backup and atomic application

Reuse the exact 51 reserved uploads, three hosted covers and 11 first-batch
placeholders. Do not upload the additional 28 local Draft photo proposals in this
release. Drafts retain any hosted cover, otherwise NULL and the existing UI
placeholder. The completed 79/3/16 mapping, downloaded originals and image proofs
are preserved, including the unassigned wrong Nuvali Sand Courts photo.

The owner must upload through supported Storage API/dashboard operations in a
separately approved procedure, with no overwrites/upserts and no public write
policy. The standard photo validator must run at actual upload preparation and
its bytes/MIME/hash must match the already recorded payload proof; some staged
input hashes differ from validated upload hashes. Do not upload original bytes
blindly. No image scanning, matching or sanitization was rerun here.

After actual upload and read-back verification, the trusted owner records only
object name, SHA-256, byte count, MIME and operator in the private upload receipt
table. It is intentionally EMPTY on installation. The apply transaction requires
all 51 metadata rows AND private read-back hash receipts; expected-plan values
alone are not evidence of an upload. The production write/upload helper and
receipt-import commands require separate review after content approval; this
package contains no executable network uploader or secret loader.

Keep the accepted 50-row inventory, schema and Storage metadata snapshots and
hashes as baseline backups. Preserve all five original Storage objects; metadata
is not a backup of their binary contents. Retain owner-controlled binary backups
before any future approved operation. The batch also saves the complete 50-row
database baseline privately. No Auth/database-wide restoration is part of rollback.

Application locks destination/taxonomy writers, checks every baseline row and
reserved ID, checks the exact registry and upload receipts, applies all 98 rows
and seven holds, validates mapped-publication constraints, verifies 120/65/42/13,
and commits audit/receipt/policies/data together. Any error aborts everything in
that transaction; uploaded Storage objects are a separate system and may remain
unreferenced. Unknown outcomes require receipt inspection, never blind retry.

`rollback.review.sql` prepares a separately gated owner-only containment action.
It checks all 105 recorded row versions/values and makes the 65 Published rows
Draft atomically, retaining all 120 rows and all images: 0/107/13. It stops on
drift, does not delete new destinations, restore old Published data, remove RLS
or constraints, alter accounts/memberships, or restore Auth sessions.

## Approval sequence — do not run these hosted operations yet

1. Approve the seven content resolutions (or provide supported replacements),
   the 10 exact aliases, 79 category keys/parents, unresolved Draft NULL-pair
   handling, all 21 status transitions and the limited existing-Auth-risk scope.
2. Regenerate a NEW exact release from those decisions and repeat offline
   qualification. Do not silently mark existing review files approved. Both
   supplied variants are review-only and cannot be applied as delivered.
3. Review role-denial, full-98, mandatory-field, duplicate, audit, public-visibility,
   Admin edit, recommendation and containment evidence. Local conditional tests
   using the seven proposals are not actual approval or live qualification.
4. Before the approved window, confirm the Dashboard production project, run the
   small `preflight.readonly.sql`, and verify the previously accepted full snapshot
   against actual row/schema drift. Do not repeat exports merely for paperwork;
   any new drift requires fresh evidence and review. Preserve binary backups.
5. Separately approve the exact schema, private owner functions, 51 uploads and
   read-back receipt procedure, fixed 98-row transaction, non-auth catalog runtime
   configuration and containment SQL. No Cloudflare/Render/Auth changes are needed
   merely to execute this owner-maintenance route.
6. During an approved maintenance window, stop concurrent catalog writers, apply
   the qualified schema/private preparation (which does not publish data), upload
   and verify immutable images, record receipts, then invoke the qualified owner
   transaction once. Run read-only postflight and ordinary-role visibility checks.
7. Use a NEW approved 79-key registry mirror, enable the existing
   `ROSAGO_FLEXIBLE_CATALOG_ENABLED=true` and `ROSAGO_CATEGORY_REGISTRY_PATH`
   settings, preserve appropriate tourism/environment flags, disable catalog
   preview and restart normal Flask. Coordinate activation with the transaction
   so running readers never parse new categories with the legacy seven-key list.
   Verify actual Explore/details/Planner and Admin read/edit behavior only within
   a separately approved testing scope. This is not Render deployment approval.

No hosted step or live sign-in has been performed. Original publication files
remain unchanged and their hashes are recorded in `manifest.json`.
