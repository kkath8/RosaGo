# Production first-65 package — NOT SAFE TO APPLY YET

Target: **brnkigrrqdrywahvcbvc only**. No hosted write, upload, migration,
sign-in or deployment occurred. Remote deployment remains **NO-GO**.

## Fresh evidence: passed

The latest owner-operated destination export contains 50 complete rows:
35 Published / 2 Draft / 13 Archived, with **zero destination drift** including
IDs, slugs, images and row versions. The corrected schema result has the expected
`catalog_schema_preflight_json` wrapper, 23 functions, 20 columns, 20 constraints,
4 policies, 25 direct grants and 8 indexes, with **zero schema drift**. The original
misnamed schema file is retained as received; it contained another destination
inventory and was not accepted as schema evidence.

All accepted exports report owner-selected production project
`brnkigrrqdrywahvcbvc` and a read-only transaction. Identity relies on the owner's
Dashboard selection; the SQL project literal is not independent server proof.

Storage checks passed: existing public `destination-images` bucket, 5 MiB limit,
JPEG/PNG/WebP allowed, five existing objects preserved, all three retained cover
objects present, and no collision with the 51 reserved object names. Storage
RLS is enabled; anon/authenticated have no BYPASSRLS or superuser attribute and
there are no allow policies. Their broad table grants do not bypass that RLS.
The server-only privileged upload credential is required; it was not requested,
exposed or tested live. Current identity checkpoint: **4 Auth users, 4 profiles,
1 Admin membership**. The exports establish the current checkpoint, not an
unsupported comparison with older account counts that were never exported.

[fresh-evidence.json](fresh-evidence.json) binds all four accepted files by SHA-256.
No further inventory/schema/Storage export is needed merely to repeat these
completed checks. Refresh only for real drift or later approved security changes.

## Exact proposed changes

| Change | Count |
| --- | ---: |
| Existing destinations updated, UUID/slug retained | 14 |
| New eligible destinations, database-generated UUID/slug | 51 |
| Existing Published destinations moved to Draft | 21 |
| Archives / deletions | **0 / 0** |
| New Storage uploads / preserved hosted covers | **51 / 3** |
| First-batch placeholders (NULL image_url) | 11 |
| Proposed final DB total | **101** |
| Proposed final Published / Draft / Archived | **65 / 23 / 13** |

The 21 Draft transitions include 14 held CSV matches and seven older Published
records previously proposed for archiving. **Draft instead of archive is the
conservative first-cutover proposal and requires explicit approval.** It does
not approve any ambiguous merge/branch decision. The two original Drafts and
13 original Archived rows stay unchanged. This differs deliberately from the
earlier conditional 20-Archived projection; no archive is silently authorized.

All **16 content-pending and 17 location-pending CSV destinations remain
unpublished**: 14 already exist and become Draft; 19 not-yet-created records
remain preserved local Draft holds. Missing mandatory descriptions are not
replaced with dummy text to insert those pending records.

The first batch is the already reviewed CSV numbers
**1, 4–9, 11, 13–21, 23–41, 45, 52–55, 57, 61–69, 71, 74–86**.
[change-set.review.json](change-set.review.json) includes exact fields, expected
old rows/versions, UUIDs, proposed image URLs and all Draft transitions.
New slugs follow the **existing audited mutation's** `destination-<UUID>` rule;
they are not guessed from preview slugs. The resulting ID/slug mapping is saved
in the private transaction receipt and returned to the authorized operator.

Only **59 taxonomy keys** are needed: seven unchanged legacy interests plus
52 specific categories used by this batch. The three deferred resort records
do not require a category-conflict decision before this first batch.
[category-registry.review.json](category-registry.review.json) remains
`approved=false` until the exact registry/parent mappings are approved.

## Exact SQL and image artifacts

1. Existing [export-bound category/schema extension](../catalog_extension.production-bound-v2.review.sql).
   Preserves the secured audit wrapper, grants and original constraints except
   the specifically replaced category contract; adds operating-day support and
   category/duplicate guards. Fresh definitions still match its baseline.
2. [registry.review.sql](registry.review.sql): the 52 first-batch taxonomy rows
   in a serializable transaction; no destination records or memberships.
3. [prepare-cutover.review.sql](prepare-cutover.review.sql): private verification
   ledger, authenticated verification RPC, fixed-plan apply RPC, private receipt
   and containment RPC. SECURITY DEFINER functions use empty search_path;
   PUBLIC/anon/service-role execution is revoked. Authenticated callers still
   need a current provider session and freshly locked Admin membership.
4. [image-uploads.review.json](image-uploads.review.json): exact staged input,
   expected post-validator upload hash, byte count, MIME, reserved object key
   and production public URL for every one of the 51 uploads. `upsert=false`;
   all existing five objects remain untouched. No placeholder path is written
   into `image_url`. The other 28 of the completed 79 attachment proposals remain
   deferred; full 79/3/16 mapping and originals are unchanged.

**The new installation SQL intentionally raises `UNQUALIFIED_RELEASE`. Do not
run it or remove its guard manually.** It is exact review SQL, not an approved
release. A release must be regenerated after actual security qualification and
final approval, with qualified function/permission fingerprints. No fake claims,
owner DML, new Admin grants or service-role database importer is permitted.

Preparatory installation does **not** hide the existing catalog. Restrictive
visibility policies, the mapped-only CHECK and all data/status changes are
installed together inside the authenticated batch transaction. Only the final
validated state is committed; a failed cutover retains the old visible catalog.

## Backup, application and verification sequence — future approval required

1. Retain the accepted latest destination/schema/Storage/permission exports and
   hashes as the pre-change backup; retain the old 50-row export too. Preserve
   the existing five Storage objects and their URLs. Freeze destination/schema/
   Storage writers during the approved window. Do not back up/restore Auth as
   part of catalog rollback. Migration-history relation is absent in the
   supplied snapshot; do not invent or repair legacy history.
   Database/metadata exports do not back up Storage object bodies. No old object
   will be overwritten; a separate owner-controlled binary backup of the five
   objects can be retained for disaster recovery without reprocessing images.
2. Qualify independent authority/direct API replay protection first. Review any
   resulting production schema/grant changes against this package before using
   baseline guards. Existing unqualified security SQL must not be copied from
   evaluation and presented as a restore-safe production fix.
3. After separate final approval, apply only the qualified release DDL/registry
   through the owner-operated write mechanism. Then upload the 51 reserved
   objects using the existing Admin-authorized server Storage flow and its
   optional planned object IDs. Reuse the standard photo validator at actual
   upload time and require its output SHA to match the completed payload proof.
   Read back the uploaded objects and verify hashes/MIME/size; save receipts.
   A timeout/409/unknown result must be reconciled, never blindly retried or
   overwritten. The ordinary Admin form still generates fresh random keys.
   The development catalog preview must be disabled before any permitted
   authenticated write. Ordinary development-memory authentication is not a
   substitute for the qualified provider/independent-authority context.
4. Invoke the fixed `rosago_admin_apply_first_catalog_batch()` once through a
   qualified authenticated Admin client, not SQL Editor with fabricated claims.
   The function locks the catalog, checks all 50 prior rows/versions, 59-key
   registry parity and all 51 Storage metadata receipts; performs the 21 Draft
   transitions and 65 audited mutations/verifications/publications; validates
   the CHECK; checks 101/65/23/13; and records the actual new IDs and slugs.
5. Run [postflight.readonly.sql](postflight.readonly.sql) and
   [postflight-anon.readonly.sql](postflight-anon.readonly.sql). Compare exact
   IDs/fields/covers, registry, validated constraints, function ACLs/owners,
   policies, receipt, audit events and account/membership checkpoint. The anon
   query must see 65 mapped Published records. Controlled real User/Admin API
   and logout/replay acceptance needs its own authorized security test stage.
6. Only after schema/security/data postflight, use the approved 59-key runtime
   registry and enable `ROSAGO_FLEXIBLE_CATALOG_ENABLED=true` with its absolute
   `ROSAGO_CATEGORY_REGISTRY_PATH`. Keep the already qualified tourism/environment
   switches appropriate to the installed schema. Restart normal Flask with
   `ROSAGO_CATALOG_PREVIEW=false`. Explore and recommendations must read the
   actual Published table; no simulation service is used in normal mode.
   This is local runtime activation, not authorization to deploy remotely.

Before COMMIT, any failure rolls back rows, policies, evidence and audit changes.
After COMMIT, the prepared `rosago_admin_hold_first_catalog_batch()` provides an
**explicitly approved containment rollback**: it checks every published receipt
version, then atomically makes all 65 Draft through existing audit/auth flows.
IDs, photos and relationships are retained; no rows are deleted and no Auth
state is restored. In the tested first-cutover state this leaves 0 Published,
88 Draft and 13 Archived. It is containment, not an automatic restoration of
unverified legacy publications. Stop on drift; corrected roll-forward or old
field restoration requires a reviewed plan. Never drop RLS/CHECKs, replay old
publish.sql, restore the whole database, or delete uploaded objects to recover.

## Qualification and the remaining stop

**40 native PostgreSQL checks passed**, including the exact 65-record SQL,
295 forward audit events, private-receipt denial, non-Admin/false/NULL rejection,
duplicate prevention, field/Storage drift, User/Admin RLS, atomic failure rollback
and version-guarded containment. The cached owned container had networking
disabled and no exposed ports and was removed. Accounts were synthetic;
destination data came from the supplied public export. Positive provider and
Storage cases were fixtures, **not live Supabase qualification**.

**42 focused offline tests passed**, covering reserved upload paths/no-upsert,
Admin upload authorization, gateway contracts, strict provider transport,
unknown-vs-revoked status, scope and received evidence. No original image
validation, scanning or sanitization was repeated.

Local security fixes now reject unknown provider results without treating them
as confirmed revocation, and the inactive gateway accepts the exact new RPC
contracts. Neither activates production session wiring. The gateway is still
evaluation-bound and does not yet support every existing trip-service write;
do not switch off the Data API or repoint the app to it as a shortcut.

**Auth restore/replay remains unresolved end to end.** The fresh production
schema still has no provider-session helper. The evaluation session-row helper
can accept an old unexpired JWT again after its Auth row is restored. Supabase
documents that access JWT validity is independent of signing out:
[official sessions documentation](https://supabase.com/docs/guides/auth/sessions).
Independent web revocation alone does not stop direct REST/GraphQL/privileged
RPC or managed Auth replay. A backend-only architecture must actually close
direct bypass and preserve all current services; hosted Auth refresh/recovery
also needs explicit restore protection. Shorter JWT expiry or signing-key
rotation alone is not being asserted as a tested solution.

**Next security gate:** finish and qualify a complete direct-path authority
strategy before requesting hosted execution. The existing independent-authority
and gateway candidates do not yet meet that end-to-end requirement. A subsequent
evaluation-only infrastructure/credential setup and controlled synthetic
sign-in/logout/JWT/restore test stage requires a separately reviewed, exact
approval. Those hosted/secret/live operations are not authorized by catalog
preparation. No production SQL approval can substitute for the missing proof.
No paid provisioning or deployment is requested as a workaround.

After that passes, remaining production approval covers this exact 65-record
field set, 21 Draft transitions, 59 categories, 51 new objects, qualified SQL,
backup/containment and runtime activation. The seven archive decisions are
deferred. Until then **production publication is not safe and must not proceed**.
