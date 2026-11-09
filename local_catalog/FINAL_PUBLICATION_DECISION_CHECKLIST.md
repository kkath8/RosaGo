# Final production publication decisions — 2026-11-08

> Latest first-batch package: [FIRST_PUBLICATION_BATCH_APPROVAL.md](FIRST_PUBLICATION_BATCH_APPROVAL.md). The 81 researched locations are now explicitly accepted for planning; remaining content/cutover decisions and security gates are listed there. Earlier count/status projections below are historical.

> Current research evidence correction: [OWNER_RESEARCH_REUSE_REVIEW.md](OWNER_RESEARCH_REUSE_REVIEW.md). The owner has reaffirmed the original research. Earlier zero-evidence/blanket re-verification wording below is historical: 83 numeric CSV pairs retain owner-confirmed research; review the targeted exceptions only. Security and hosted-write approvals remain pending.

> Editable owner worksheets: [owner-review/README.md](owner-review/README.md), with all 98 destinations and separate alias/archive/category tables. Editing them records proposed decisions only; no importer or hosted execution is enabled.

**Review only. Database update/publication and remote deployment remain NO-GO.**
Target for this catalog proposal: `brnkigrrqdrywahvcbvc`, from the owner-attested
export. Do not substitute the evaluation project or its security state.

This is the current checklist. Older missing-schema-preflight statements in
earlier reports are historical: the owner schema export was validated and
25 native PostgreSQL clone checks passed. The overall hosted migration is
still unqualified. No completed CSV matching or image processing was repeated.

## Current disposition

| Item | Count |
| --- | ---: |
| Existing records in owner export | 50: 35 Published, 2 Draft, 13 Archived |
| CSV records | 98 |
| Proposed updates preserving existing IDs/slugs | 28 |
| Proposed additions, initially Draft | 70 |
| Proposed archives needing individual approval | 7 |
| Existing records otherwise untouched | 15 |
| Numerically valid CSV coordinate pairs, not geographically approved | 83 |
| Conditional stored-pair reuse proposals | 3 |
| No usable pair available | 12 |
| Approved geographic evidence | 0 |
| Ready Published / held Draft in the review plan | **0 / 98** |

The last line is a proposed-plan status, not a hosted change. The 35 exported
Published records have not been changed. Unapproved Draft transitions must not
be applied simply to make the migration pass.

The generated [decision inventory](publication-decision-checklist.review.json)
lists every record, its candidate pair, unresolved gates and image disposition,
with input hashes. It checks consistency with the current location and image
reviews; it cannot approve or execute anything.

## Owner decision checklist

- [ ] Confirm each physical destination identity and location. For each verified
  pair, provide CSV record number, exact name/address, complete latitude and
  longitude, source/reference, reviewer and review time. Syntax, filenames,
  previous Published status and a map pin without identity confirmation are
  insufficient. Leave unverified destinations Draft. Do not mix coordinates
  from different sources or estimate missing points.
- [ ] Approve or correct the following 10 aliases. Approval means retain the
  existing UUID and slug; it does not automatically verify its coordinates.

| Existing name | CSV name | Recommendation |
| --- | --- | --- |
| Nuvali Park | #2 Nuvali Lakeside / Park | Reuse after confirming park/lakeside scope; review separate activities record |
| Ayala Malls Solenad | #3 Ayala Malls Solenad (Ayala Malls Nuvali) | Reuse existing identity |
| Cuartel de Santo Domingo | #12 Fort Santo Domingo / Cuartel de Santo Domingo | Reuse existing identity |
| Santa Rosa Arch (Bantayang Bato) | #42 Santa Rosa Arch | Reuse existing identity |
| Museo ng Santa Rosa | #43 The City of Santa Rosa Museum (Museo de Santa Rosa) | Reuse existing identity |
| Toyota Santa Rosa | #47 Toyota Santa Rosa (Toyota Motor Philippines) | Reuse after confirming site scope |
| Coca-Cola Santa Rosa | #48 Coca-Cola Santa Rosa (Coca-Cola Beverages Philippines) | Reuse after confirming site scope |
| Monde Nissin Santa Rosa | #49 Monde Nissin Santa Rosa Plant | Reuse existing identity |
| Mitsubishi Motors Santa Rosa | #50 Mitsubishi Motors Philippines Corporation | Reuse existing identity |
| The Fun Farm at Sta. Elena | #51 Fun Farm at Sta. Elena | Reuse existing identity |

- [ ] Decide on the three complete stored-pair reuse proposals below, after
  matching identity AND verifying location. These are trusted export values,
  not independently verified geographic corrections.

| CSV destination | Problem | Conditional exported pair |
| --- | --- | --- |
| #2 Nuvali Lakeside / Park | Latitude contains an east/longitude value | `14.239906, 121.059477` from Nuvali Park |
| #10 WalterMart Santa Rosa | Longitude repeats latitude/north value | `14.28803, 121.09437` from Waltermart Santa Rosa; distinguish Bel-Air branch |
| #90 Target Mall | Missing pair | `14.29443, 121.10346` from Target Mall |

- [ ] Supply verified pairs or explicitly retain Draft for these 12 records:
  #22 Chowking Sta. Rosa Bayan; #87 Lolo Uweng Chapel; #88 KFC Paseo de Sta. Rosa;
  #89 Victory Central Mall; #91 Cafe Maestro; #92 Cafe Royal; #93 Cafe de Rosa;
  #94 Cafe Amelia; #95 Kafé Lando; #96 Island Foodpark; #97 Grill Yard; #98 Mary Grace.
- [ ] Supply source-backed descriptions for #56 Nuvali Sand Courts, #58 Winner
  Badminton Court, #59 Court Zero Pickleball Court and #60 Infinite Badminton &
  Sports Center. No existing matching descriptions are available. Do not invent them.
- [ ] Decide #87 Lolo Uweng Chapel tourism type: owner/source-backed Local or
  Common, or explicitly accept NULL/Not recorded. This never bypasses its Draft hold.
- [ ] Approve the 73 specific category labels and legacy-interest parent
  relationships. 71 parent proposals are prepared, not approved. Resolve
  `Resort / Swimming Pool` versus `Resort Swimming Pool` (records #70, #72, #73):
  merge labels through an explicit mapping or assign distinct stable keys;
  decide lodging versus recreation parent. Preserve seven legacy interest keys.
- [ ] Preserve unknown operating days (63 records); opening/closing text remains
  unverified. No automatic hours/schedule feasibility inference.
- [ ] Review shared/near-identical points, including malls versus tenants and
  Arambulo versus Gonzales houses; coordinates alone never establish duplicates.
- [ ] Approve/reject each archive below. Missing from CSV is a review reason,
  never automatic permission to archive or delete. No relationship transfers.

| Proposed archive | Reason and overlap to resolve |
| --- | --- |
| Mama Lou's Italian Kitchen | Missing from CSV; other Italian restaurants are separate identities |
| Lakeside Activities (Nuvali) | Possible overlap with #2; confirm scope before retaining park ID and archiving activities |
| CIBO – Solenad | Missing restaurant; #3 is the mall, not the same record |
| Perlas Ancestral House | Missing; #44–46 name different houses; do not merge |
| Tiongco Ancestral House | Missing; #44–46 name different houses; do not merge |
| Kanin Club | Missing; no same-name CSV destination |
| Waltermart Bel-Air | Confirm separate outlet from #10 WalterMart Santa Rosa before archive |

## Images: preserve completed review

Keep [destination-images.final-mapping.review.json](destination-images.final-mapping.review.json)
unchanged: **79 proposed attachments, 3 preserved hosted covers, 16 placeholders**.
Nuvali Sand Courts is unassigned; Winner Badminton Court remains held pending
identity confirmation. Placeholders are render-only, never database image URLs.
Photos do not verify geography. No upload approval is implied by catalog approval.

## Exact requirements before production application

1. **Security prerequisite:** qualify provider session authority for the actual
   target, including direct API/privileged RPC replay after Auth restore, not
   only Flask routes. Production's supplied schema lacks the evaluation helper.
   Do not copy that helper as a claimed restore-safe solution. See
   [PUBLICATION_SECURITY_REQUIREMENTS.md](PUBLICATION_SECURITY_REQUIREMENTS.md).
2. **Resolve content decisions:** record explicit identity, correction, category,
   coordinate and archive approvals in source-bound review evidence. Regenerate
   the full field-level package with fresh hashes; never manually flip a flag
   to make a gate pass. Verify approved registry JSON/database parity.
3. **Fresh owner read-only preflight:** independently confirm Dashboard project,
   repeat `catalog_extension.preflight.readonly.sql` and the all-status export
   `export_production_places.readonly.sql` immediately before the final approved
   operation; save as NEW dated files for drift review. Stop on schema, owner,
   ACL, constraint, policy, UUID, slug, image or row-version differences. Preserve
   current exports. The SQL project literal is owner attestation, not server proof.
4. **Qualify exact SQL:** `catalog_extension.production-bound-v2.review.sql`
   is an export-bound review candidate, not approved SQL. Rebind/requalify against
   any approved security changes. Preserve audit wrapper, Admin/provider entry
   checks, locked mutations and grants. Verify category FK/cycle/concurrent
   duplicate guards and operating-days/provenance contracts. Resolve migration
   tracking deliberately: the exported history relation is absent, not empty.
5. **Qualify mapped-only cutover:** `mapped_publication_guard.review.sql` still
   unconditionally aborts; it is NOT executable release SQL. Prepare a new
   reviewed replacement only after authority qualification. Its restrictive RLS
   hides legacy unverified Published rows immediately. A private evidence ledger,
   authenticated audited verification and final validated CHECK are required;
   never backfill owner-approved flags directly into the ledger. The operation
   must be atomic or maintenance-gated with no publicly exposed partial state.
6. **Preserve the audited workflow:** schema/registry DDL is owner-operated only
   after approval; record creation/update/verification/status changes use the
   existing authenticated Admin authorization and audit flow. No owner DML,
   forged JWT claims or service-role importer bypass. The bounded bulk execution
   and failure/reconciliation procedure is not yet a qualified release tool.
7. **Stage and reconcile:** create new records Draft, update matched UUIDs,
   detect ID/slug/normalized-name collisions, preserve covers, validate field
   diffs and expected row versions. Archive only individually approved rows.
   No delete or missing-file cleanup. Keep the Published candidate set within
   the existing 100-record recommendation bound; an all-ready non-atomic sequence
   could briefly reach 105. Do not increase the bound to bypass safe cutover.
8. **Protect rollback:** record a reviewed pre-change snapshot and restore plan
   for catalog/configuration, preserve all IDs/relationships/audit events and
   stop/reconcile uncertain mutation results. Never blindly retry or restore the
   whole Auth/session database to undo a catalog operation.
9. **Postflight before enabling runtime:** verify columns, constraints VALID,
   indexes, registry parity, roles/grants/RLS, function definitions/search_path/
   EXECUTE, actual audit events, unchanged unrelated tables and exact status/ID/
   image sets. Test ordinary User and Admin visibility, privileged RPC denial,
   replay, browsing/maps/recommendations, category interest matching and absent
   coordinate exclusions. Live acceptance needs separate explicit approval.
10. **Coordinated runtime activation:** leave flexible catalog disabled until
    schema/security/registry postflight passes. Then, only under separate
    approval, configure `ROSAGO_FLEXIBLE_CATALOG_ENABLED=true` and
    `ROSAGO_CATEGORY_REGISTRY_PATH=<approved project-bound JSON absolute path>`
    and restart the approved runtime. Enabling early breaks the old DB contract.
    No environment or deployment settings were changed in this stage.
11. **Final approval boundary:** present immutable SQL, registry, record diffs,
    status transitions, expected counts, hashes, operator procedure and rollback
    evidence for explicit production approval. Image uploads/assignments and
    deployment remain separately approved operations.

If all proposed identities and seven archives are approved and there is no
drift, the final table would contain 120 rows (50 retained + 70 additions), not
98: the 98 CSV destinations plus 22 other preserved records. With N CSV records
qualified/published, expected totals would be N Published, (100−N) Draft and
20 Archived, assuming the original 15 untouched records retain their states.
This is a conditional reconciliation formula, not permission to transition rows.

## Local work and evidence

Added a review-only cross-artifact decision checklist generator and focused
tests for wrong targets, source/identity drift, missing/duplicate inventory,
hosted cover preservation, held court assignments, stale coordinate evidence
and the separation of record readiness from execution approval.

**43 focused offline tests passed**, with socket connection attempts blocked:
decision checklist (5), mapped-only policy (10), flexible catalog (5), provider
admission (7), mocked provider transport (7), schema/synthetic image contracts (9).
The latter uses generated pixels only; no destination images were rescanned,
sanitized or validated. Initial Windows temporary-file/import-path errors were
resolved by running with the test directory on the import path and permission
to use Windows temp files. No application security changes were needed.

Prior 25 native PostgreSQL clone checks and 100 Python/8 JavaScript image-stage
tests are preserved, not claimed as rerun. No SQL changed in this stage.

**Next owner action:** review the identity/location/correction/category/archive
decisions above; provide real evidence or choose Draft for unresolved records.
This is content review, not hosted-write approval. Security work can continue
locally in parallel; no hosted execution request is ready yet.
