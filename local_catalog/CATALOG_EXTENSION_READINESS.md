# Local flexible-catalog preparation

> Current operational checklist: [FINAL_PUBLICATION_DECISION_CHECKLIST.md](FINAL_PUBLICATION_DECISION_CHECKLIST.md). The schema preflight is complete; provider authority, final content decisions and the exact atomic/maintenance cutover remain unqualified. Earlier all-98-Published and missing-preflight statements below are historical.

> Latest evidence: [SCHEMA_AND_IMAGE_INTEGRATION_REVIEW.md](SCHEMA_AND_IMAGE_INTEGRATION_REVIEW.md). The owner schema export is now validated, and downloaded images are preserved/staged. Earlier missing-preflight statements below are historical. Overall hosted publication remains unqualified.

> Updated [mapped-only policy and qualification](MAPPED_PUBLICATION_POLICY.md): 23 real local PostgreSQL checks now passed; the earlier untested-SQL and all-98-Published status below is historical. Production preflight remains blocked.

Remote deployment and hosted catalog replacement remain **NO-GO**. No hosted
SQL, account operation, sign-in, import or publication ran during this work.

## Implemented locally

- `destination_categories.py` supplies a project-bound, approved-file registry.
  Keys and labels are extensible; the seven legacy keys remain for saved
  interests/drafts. It rejects unapproved/wrong-project registries, duplicate or
  malformed keys, missing parents, cycles and altered legacy definitions.
  Approved parent relationships allow a specific category to match its legacy
  broad interest. No relationships have been inferred for the real CSV.
- A shared read-only category collection now reaches Place parsing, Admin
  validation/counts/insights, itinerary preferences/previews and recommendation
  eligibility. The policy's existing interest-count bound stays unchanged;
  the User quiz/DB contract still limits selections to six. Local/NULL/Common
  ranking, selection policy and unknown-feasibility semantics stay intact.
- User browsing/details, itinerary labels, account interests, client map labels,
  personal-state persistence, search labels and local cards use the registry.
  Dynamic category cards use existing generic artwork until a real photo is
  supplied, rather than requesting nonexistent category assets.
- `operating_days_raw` is a bounded nullable source-text field in the local
  Place and Admin detail models. After rollout, public/Admin reads select it,
  Admin forms validate/save it through the guarded mutation flow, and detail
  views display it as unverified text. No schedule inference is implemented.
- Guarded local mutation validation accepts paired source provenance fields
  only when the rollout is enabled; invalid/bool/out-of-range row numbers and
  incomplete source pairs are rejected. The source fields are for the reviewed
  catalog operation; no editable provenance controls were added to the UI.
  Audit parsing recognizes the added fields; no logging behavior is disabled.

No environment file was changed. The new capability is **off by default**:

```text
ROSAGO_FLEXIBLE_CATALOG_ENABLED=false
```

The future operator configuration, only after schema/RPC/security postflight,
registry approval and exact DB/file parity checks, is:

```text
ROSAGO_FLEXIBLE_CATALOG_ENABLED=true
ROSAGO_CATEGORY_REGISTRY_PATH=<absolute path to the approved project-bound registry JSON>
```

Keep the existing tourism/environment rollout capabilities enabled only when
their installed schemas are qualified. Restart after changing the approved
registry/configuration; registry contents are immutable within the process
cache. A requested rollout with missing/unapproved/wrong-project configuration
fails at startup instead of reverting silently. Do not enable this mode on the
current database: the required new column/RPC contract is not installed.

`category-registry.review.json` is explicitly **unapproved**, with unresolved
keys and no invented parent relationships. It is not usable runtime config.
The database registry will be owner-managed through approved registry packages;
this work does not add an unsupported inline category-creation control. Any
number of reviewed categories within the validated resource bound can be added
without changing a seven-value Python/JavaScript enum. Synchronizing a future
registry version requires DB/file parity verification and an application restart.

## Migration preparation and deliberate blockers

`catalog_extension.review.sql` prepares:

1. A `public.destination_categories` registry with stable keys/labels, optional
   parent references, RLS and public taxonomy SELECT only. No ordinary User,
   Admin or service-role registry DML is granted. Only the seven existing
   legacy category definitions are staged; no destination records are seeded.
2. Nullable `public.places.operating_days_raw` (maximum 2000 characters).
3. A category FK before replacement of the existing seven-value category CHECK.
   Dropping that specific CHECK is necessary to support new registered keys;
   it must be verified against the current definition before approval.
4. Surgical changes to the **current** inner Admin mutation definition for
   registry validation, operating days and paired source provenance. Caller
   checks, provider checks, member/row locks, image validation, lifecycle rules,
   SECURITY DEFINER/search_path and existing ACLs remain in place. The audited
   wrapper is not replaced, and its definition is checked unchanged.
5. A registry-backed interests validator marked STABLE, retaining INVOKER,
   existing ACL/owner/search_path, count bounds, uniqueness and NULL rejection.
   Using a table lookup from an IMMUTABLE function would be incorrect.

**Do not run this draft.** Its first guard raises an exception while the
function/constraint baseline hashes are unqualified. No partial application
should be attempted. It has not been executed against PostgreSQL and is not a
final migration package. Registry parent-cycle enforcement in the database,
duplicate-create concurrency protection and full schema postflight remain to
be finalized and tested before hosted approval. Local cycle/duplicate detection
does not replace those database acceptance gates.

The owner export supplied destinations, not live function/constraint bodies.
An old migration body must not be substituted for a live secured RPC. The next
safe schema evidence step is the prepared
`catalog_extension.preflight.readonly.sql`: independently confirm Dashboard
project **brnkigrrqdrywahvcbvc**, use the existing postgres role, run the whole
read-only transaction, and save the complete `catalog_schema_preflight_json`
cell as `local_catalog/production-catalog-schema-preflight.json`. Stop on any
warning/error. The query reads public schema definitions/grants/policies, not
Auth accounts, sessions, credentials or destination contents, and ends in
ROLLBACK. Its project literal is an owner attestation, not server identity proof.

Do not fill the draft's baseline hashes manually merely to make it run. After
reviewing that export, finalize the exact surgical transformation, registry
package, function permissions/guards, DB cycle/duplicate handling, postflight
queries and isolated PostgreSQL tests. Request separate approval for the
resulting hashed SQL package before any hosted application.

## Testing

- **258 Python tests passed** (204 catalog/Admin/itinerary tests plus 54 public
  API/account/itinerary rendering tests), with network connections blocked, covering the
  new registry and schedule/provenance contracts plus affected Admin/User,
  authorization/audit, maps, itinerary and recommendation regressions.
- **15 map JavaScript tests passed**, including dynamic labels, 98 markers,
  unknown-category rejection and safe text rendering.
- Personal-state JavaScript assertions passed, including persistence of a
  dynamic interest and existing storage/scope/backup safeguards.
- A synthetic 98-candidate ranking test and User browsing/detail rendering
  test passed with reviewed labels and escaped unverified operating-day text.
  This proves local contracts, not correctness of unresolved real CSV fields.
- The Node multi-file test runner hit a sandbox child-process restriction;
  running each existing test file directly succeeded. No dependency install
  or browser/network access was needed.
- The original CSV, owner export, Linux build evidence and weather metadata
  hashes remain preserved. The evaluation manifest stays evaluation-pinned.

## Publication package status

The [decision tables](CATALOG_DECISIONS_AND_CORRECTIONS.md) and
`corrections.proposed.review.json` provide exact reuse proposals, not approvals.
The original CSV and the 28-update/70-addition/7-archive candidate package remain
unchanged. No final corrected package has been generated because the owner has
not approved the identity/correction/archive decisions and four descriptions
remain missing. After those decisions and schema qualification, regenerate the
complete diff with new hashes and request explicit hosted-write approval.

The final planned published count is 98. Stage additions as Drafts, validate,
then use the separately approved bounded/transactional cutover. Publishing all
70 additions before archiving seven would temporarily reach 105 and exceed the
current 100-candidate bound. Never auto-delete missing records, transfer saved
relationships or weaken RLS/provider guards to complete the replacement.
