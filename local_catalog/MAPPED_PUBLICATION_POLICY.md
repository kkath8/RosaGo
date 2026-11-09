# Current policy: verified mapped destinations only

> Research provenance update: [OWNER_RESEARCH_REUSE_REVIEW.md](OWNER_RESEARCH_REUSE_REVIEW.md). The owner's confirmation of the original researched dataset is now recorded. Earlier zero-evidence figures below describe the old formal worksheet, not a finding that all 98 destinations lack prior research. Keep missing/malformed or specifically disputed coordinates Draft; no security or hosted-application gate is waived.

> Current operational checklist: [FINAL_PUBLICATION_DECISION_CHECKLIST.md](FINAL_PUBLICATION_DECISION_CHECKLIST.md). The validated schema export and 25 production-baseline clone checks supersede the historical missing-preflight section below. Use the v4 publication review plus the completed final image mapping; neither authorizes execution.

> Latest evidence: [SCHEMA_AND_IMAGE_INTEGRATION_REVIEW.md](SCHEMA_AND_IMAGE_INTEGRATION_REVIEW.md). The owner schema export is now validated, and downloaded images are preserved/staged. Earlier missing-preflight statements below are historical. Overall hosted publication remains unqualified.

This supersedes the earlier goal of publishing all 98 CSV rows. It changes the
**local review plan only**. Hosted records, including the 35 currently Published
destinations, have not changed. Remote deployment remains **NO-GO**.

## Exact current evidence counts

| Review classification | CSV destinations |
| --- | ---: |
| Valid numeric coordinate pairs in CSV; geographic verification not established | 83 |
| Invalid/missing CSV pair with proposed stored reuse (#2, #10, #90) | 3 |
| No valid CSV pair and no matching stored pair | 12 |
| Approved record-bound coordinate verification evidence supplied | 0 |
| Record-ready for publication under the new policy | **0** |
| Held as Draft in this review plan | **98** |

Numeric syntax, plausible ranges, a stored point and previous publication are
not independent geographic verification. It would be incorrect to mark 83 or
86 destinations publication-ready without the required evidence and decisions.

The regenerated package is
[production-mapped-publication-v3.review.json](production-mapped-publication-v3.review.json).
It retains IDs/images/original values and update-time/hash preconditions. It
replaces unconditional Published proposals with Draft holds and explicitly
lists 28 **proposed**, approval-required Published-to-Draft transitions for
matched existing records that remain unverified. The seven archives also remain
unapproved. No transition is applied automatically. Existing unmatched Drafts
and Archived records remain unchanged; the original CSV, export and earlier
JSON candidate package are preserved byte-for-byte.

## Record decisions

`location-verification.review.json` provides one pending entry for each source
record, bound to source/export hashes, name and existing UUID. Candidate points
are separate from verified points. Review the physical identity and complete
point, then record the real source/reference, reviewer and timestamp. Never
mark a row verified just because its numbers parse.

For #2 Nuvali Lakeside / Park and #10 WalterMart Santa Rosa, first approve the
matching identity and then check the complete stored pair. #90 Target Mall also
has a stored pair. None is approved for reuse yet. The twelve with no matching
stored point are #22, #87–89 and #91–98. Accepting NULL is now a **Draft-only**
decision, not a path to publication.

Missing descriptions #56/#58/#59/#60 still require owner/source text. #87 needs
a tourism-type decision; explicitly accepting NULL does not bypass location
verification. No coordinates, descriptions or hours were invented. The ten
aliases and seven archives in
[CATALOG_DECISIONS_AND_CORRECTIONS.md](CATALOG_DECISIONS_AND_CORRECTIONS.md)
remain pending, especially the Nuvali scope and WalterMart branch questions.

`category-parent-mapping.proposed.review.json` proposes legacy-interest parents
for 71 of the 73 category labels. Specific categories remain distinct, not
collapsed into seven values. Two resort/pool labels remain ambiguous between
lodging and recreation and also have a key collision. All proposals remain
unapproved; neither a runtime registry nor destination data was changed.

After approving evidence/corrections, regenerate to a new file:

```powershell
.\.venv\Scripts\python.exe -m tools.prepare_mapped_publication --output local_catalog/production-mapped-publication-next.review.json
```

If the CSV itself changes, first regenerate/review its baseline diff and hashes.
Stale evidence is rejected. Do not relabel data or modify the evaluation-pinned
catalog manifest to bypass target checks.

## Prepared database enforcement

`mapped_publication_guard.review.sql` proposes a private evidence ledger,
tuple-bound predicate, publication CHECK and separate restrictive public/User
visibility policies. Evidence binds ID, name, address and complete coordinates;
moving a Published point cannot reuse stale evidence. Schema usage and ledger
access remain denied to ordinary roles. The predicate is not a public RPC.

The new verification RPC delegates first to the **current secured, audited
Admin mutation wrapper** for provider/Admin/row-version checks. It verifies a
Draft and logs confirmation in existing audit history. It accepts no supplied
actor or verification timestamp. Any validation or audit failure rolls back
the entire transaction. No owner evidence insertion or auto-verification is
approved; live authentication remains separately gated. The local audit reader
recognizes this real event without changing existing authorization.

Existing published-only and provider policies still apply. Drafts and
unverified destinations are hidden from ordinary readers, while Admin catalog
visibility is retained. Browsing, maps and recommendations retain published-only
reads. The final validated invariant and privileged itinerary-RPC acceptance
are required before runtime release. Verified coordinates establish point
coverage, not a guarantee that an external provider can route every venue.

Cutover effects require separate approval:

- The restrictive policy hides legacy unverified Published rows immediately;
  do not install it casually on the existing production catalog.
- NOT VALID is staging only. Verify or explicitly move all legacy unverified
  Published rows to Draft/Archived, then validate the CHECK. The final package
  needs an atomic/maintenance-gated cutover, with no exposed partial staging
  interval. Do not treat the staging draft as a qualified release.
- Both SQL files deliberately abort without reviewed current-schema evidence.
  No hosted execution or baseline-hash substitution is authorized.

## Completed local qualification

**23 real PostgreSQL checks passed** in an owned cached container with networking
disabled and no exposed ports. Only synthetic roles, Auth fixture rows and
destinations were used. Owned containers/volumes were removed after each run.
Results: [catalog-local-postgres-qualification-v4.json](catalog-local-postgres-qualification-v4.json).

Coverage includes actual SQL execution, retained provider checks, private-ledger
denial, User/Admin RLS, verified Draft hiding, verified Published visibility,
stale-evidence rejection, ordinary-User denial, audit rollback, two-process
duplicate races, serializable category-cycle races and final constraint
validation after a synthetic legacy cutover. The SQL collision guard supplements
full offline Unicode/alias review; SQL lower() and Python casefold() are not
equivalent for every Unicode character.

**42 focused offline Python tests passed**, with network blocked, for evidence
binding, planning, audit and flexible-category paths. Earlier 258 Python/15
map-JS results remain preserved; they are not claimed as rerun in this stage.
Local success does not qualify the unknown production function baseline.

## Production preflight remains blocked

The production MCP attempt returned **authentication required** before any
schema query. No current schema export file is available. No alternate
credential path was used to bypass that failure.

Next operator action:

1. Independently confirm Dashboard project **brnkigrrqdrywahvcbvc**.
2. Open `local_catalog/catalog_extension.preflight.readonly.sql` in VS Code.
   Copy the entire file to that project's SQL Editor using its existing
   postgres role. Run the complete read-only transaction once.
3. Stop on warnings/errors. Save the complete `catalog_schema_preflight_json`
   cell as UTF-8 JSON at `local_catalog/production-catalog-schema-preflight.json`.
4. Tell Codex the file is ready and confirm the Dashboard project reference.

The query reads schema definitions/grants/policies/indexes, not accounts or
session data, and ends with ROLLBACK. Its target literal is owner attestation,
not server-derived identity proof. Migration-history relation availability is
reported without assuming it exists; any further history read can be scoped
afterward. Current function bodies/ACLs, private/RLS interactions, schema parity
and cutover must be reviewed before final SQL approval.

Remaining approvals cover identity/location evidence, corrections/categories,
archive/status changes and ultimately the refreshed exact change set and
target-qualified migration/cutover. Session/recovery/revocation safeguards and
Linux build evidence remain preserved. Auth restore/replay remains a separate,
unresolved remote-deployment blocker.
