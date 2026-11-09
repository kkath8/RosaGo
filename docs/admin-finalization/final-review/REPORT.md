# RosaGo final deployment review

> Historical catalog artifacts now live in `data/santa_rosa_places/archive/`. Their bytes are preserved; `weather_metadata.json` remains at its original runtime path.


**CURRENT RESULT: 0012 LIVE ADMIN FUNCTIONAL TEST PASSED — READY FOR 0013 DEPLOYMENT REVIEW.**

The operator clarified that both original-record changes were intentional manual
Admin edits made before the temporary verification lifecycle. Arambulo's hours
were intentionally changed to 10:00 AM/5:00 PM before Save; CIBO's raw-hours
asterisks were intentionally removed before Save. The operator identifies matching
authenticated `rosago_admin_mutate_destination` requests at 12:22:10 and 12:27:23
on 3 November 2026, Asia/Manila, corresponding to the recorded update timestamps.

The initial preservation check detected two real differences; investigation
established the timing, and the operator subsequently supplied request attribution
and intent. The earlier FAILED/STOP and unresolved-drift conclusions are
**SUPERSEDED**. These were not no-op saves, accidental cross-record writes or
an Admin edit round-trip defect. No 0012 RPC defect is indicated.

Correct final accounting: **46 original destinations unchanged; 2 intentionally
edited by the operator; 0 unintended original-destination changes identified**.
The temporary verification record was created later, completed its full lifecycle
including Restore to Draft, and remains **Archived**. No accidental cross-record
mutation was identified. All six Admin pages and authentication passed manually.
0012 functions/security passed; the existing automated result is **85 tests +
74 subtests PASS**.

The existing evidence plus this operator clarification is sufficient for the 0012
functional-test PASS and readiness for **0013 deployment review**, subject to the
previously documented test-coverage limits. **0013 remains UNAPPLIED; deployment
was NOT PERFORMED.** This is not approval or execution of 0013.

See [corrected conclusion and preserved investigation](../database-preflight/REPORT.md#corrected-final-functional-test-conclusion--operator-clarification).
Browser testing was performed manually by the operator; Codex received no credentials.
Only existing reports were updated in this correction: no production connection,
query, SQL, test rerun, database comparison, application/migration edit, staging,
commit or push occurred.

**ROSAGO 0012 LIVE ADMIN FUNCTIONAL TEST: PASSED — READY FOR 0013 DEPLOYMENT REVIEW**

## Historical FAILED/STOP conclusion — superseded by operator clarification above

**HISTORICAL, 3 November 2026 (SUPERSEDED): MANUAL UI TEST PASSED; FINAL VERIFICATION FAILED — STOP BEFORE 0013.**

The operator manually completed normal Admin authentication, all six Admin pages,
and Create/Edit/Publish/Draft/Archive/Restore-to-Draft/final-Archive successfully.
Codex received no credentials and made no production writes or RPC calls.
The temporary verification destination exists exactly once and remains Archived
with the expected edit phrase, Accommodation category, unclassified Tourism fields,
no coordinates and a test-only address. Counts match: 49 total, 34 Published,
2 Draft, 13 Archived; original classifications 9 Local / 11 Common / 28 Unclassified,
plus the unclassified temporary record.

**Original-record preservation FAILED:** 46/48 originals match all 19 backup fields.
Arambulo Ancestral House changed raw hours from NULL/NULL to 10:00 AM/5:00 PM.
CIBO, Solenad changed 11:00 AM*/9:00 PM* to 11:00 AM/9:00 PM.
Both updated_at values changed. Other fields and all remaining originals match.
These differences are outside the approved temporary-only test scope; attribution
and cause are unproven. No restoration was performed.

0012 functions/security and inspected schema metadata remain correct. 0013 is
completely unapplied. The offline Admin suite passed again: **85 tests and
74 subtests**. Successful operator Users/Trips page testing corroborates the normal
operational-overview RPC path; search/pagination and live non-Admin negative tests
were not separately reported.

See [final post-test verification and exact drift evidence](../database-preflight/REPORT.md#final-post-test-verification--3-november-2026).
Reconcile the two real-record edits before 0013 review. No production code or
migration changes, staging, commit or push occurred.

**ROSAGO 0012 LIVE ADMIN FUNCTIONAL TEST: FAILED — STOP BEFORE 0013**

## Historical blocked attempt (superseded by operator completion and final findings above)

**3 November 2026 live Admin functional test: BLOCKED — resolve before 0013.**
The configured app starts and serves the normal Admin login page. All six protected
Admin pages redirect unsigned visitors to login; invalid login Origin/CSRF checks
return 403. No browser-control tool or configured existing-account sign-in mechanism
was available, so authenticated pages, operational RPC behavior, non-Admin session
checks and the temporary-record lifecycle were not executed. No test destination
was created and no production write occurred.

The focused offline Admin suite passed **85 tests and 74 subtests**. Fresh read-only
inspection confirms all original 48 destinations and all 19 fields remain unchanged,
inspected schema/security metadata matches the verified deployment, and 0013 remains
unapplied. No application defect was established or production code changed.
See [functional-test evidence and remaining checks](../database-preflight/REPORT.md#controlled-live-admin-functional-testing--3-november-2026).
Migration files and the existing dirty worktree were preserved. No staging, commit
or push occurred. The historical 0012 deployment PASS below is retained; live
functional testing remains incomplete.

**ROSAGO 0012 LIVE ADMIN FUNCTIONAL TEST: BLOCKED — RESOLVE BEFORE 0013**

**3 November 2026 current production status: 0012 DEPLOYED AND VERIFIED; 0013 UNAPPLIED.**
The operator's corrected-file psql execution completed through COMMIT. Immediate
read-only Supabase verification confirmed production project `brnkigrrqdrywahvcbvc`,
both exact functions, trusted ownership/security/search paths and intended ACLs.
All 48 destinations match all 19 pre-deployment backup fields; historical
0010/0011/Tourism effects and existing security protections remain intact.
The only observed application-schema additions are the two authorized functions.
No mutation RPC or other database write was performed during verification.

See the [post-deployment verification and evidence](../database-preflight/REPORT.md#immediate-post-0012-production-verification--3-november-2026)
for the 46 passing offline comparisons, snapshot, permission findings and limits.
0012 SHA-256 remains `D98C2E724DDC87908B891EA54EF4EB4EC40EBDF12ABB75265C8874FAE73BD45E`.
Live functional testing remains unperformed. 0013 auditing remains unavailable.
No staging, commit or push occurred.

**ROSAGO 0012 DEPLOYMENT: VERIFIED — READY FOR LIVE ADMIN 0012 FUNCTIONAL TESTING**

## Historical correction and implementation review (superseded for current deployment status)

**3 November 2026 correction: 0012 NEEDS RE-REVIEW; RETRY NOT AUTHORIZED.**
The first authorized production execution failed before COMMIT; the transaction
did not commit and 0012 remains unapplied. The line 55 IF/CASE delimiter defect
was minimally corrected and the entire file passed disposable PostgreSQL 17.11
execution and local security/behavior checks. Earlier SAFE conclusions below are
historical and superseded for 0012. A NEW review of the corrected checksum is
required before any retry. 0013 remains unapplied and was not executed.
See [failed execution, correction and validation evidence](../database-preflight/REPORT.md#0012-failed-execution-and-isolated-correction--3-november-2026).
No production connection or SQL, staging, commit or push occurred in this correction.

Review date: 3 November 2026, Asia/Manila. Scope: migration/source inspection,
offline regression reproduction, and dirty-worktree review. No production code,
tests, migration SQL or existing catalog files were edited. No SQL was executed,
no live records were changed, and no Git write operation was performed.

## 1. Executive summary

**Overall: GO WITH REQUIRED FIXES. Admin deployment: NOT READY today.**

Both migrations are **SAFE on static review, conditional on the deployment
prerequisites below**. No mandatory SQL source correction was identified. This is
not a claim that their PostgreSQL execution, actual Supabase ownership/grants/RLS,
or deployed schema has been verified. Those checks remain approval-gated.

The fresh full Python run executed **1,003 tests: 994 passed, 7 failed, 2 errors**.
All nine unsuccessful test IDs match the previous final-admin evidence. The extra
test since that 1,002-test checkpoint is the successful Admin forecast test. Each
of the nine issues also reproduces in its own subprocess: no evidence of suite-order
flakiness or an external-provider failure was found.

Classification: **0 demonstrated production regressions, 7 stale/historical tests,
2 fixture/context problems, 0 unclassified test issues**. This does not replace
live smoke testing. The existing Admin integration/browser evidence remains offline.

One prior-report diagnosis needs correction: the login-dashboard error occurs in
`trip_service._context`, not the profile service. The fixture lacks a callable
client RPC method and uses a non-UUID user ID. See issue E1 below.

Evidence generated for this review:

- [Full Python output](full-python-suite.txt).
- [Nine isolated reproductions](isolated-failures.json).
- [Read-only diagnostics](diagnostics.json).
- [Worktree inventory](worktree-inventory.csv) and [category counts](worktree-summary.json).
- [Initial status](git-status-before.txt), [diff statistics](git-diff-stat.txt),
  [whitespace check](git-diff-check.txt), and final preservation evidence.

No source/test changes recommended in this report were applied.

## 2. Migration 0012 review

Exact file: `migrations/0012_admin_management.sql`.

Purpose: introduce narrowly authorized destination mutations on the existing
catalog and a privacy-restricted operational projection for Users/Trips/Dashboard.

| Review item | Finding |
| --- | --- |
| Functions created | `public.rosago_admin_mutate_destination(text,text,timestamptz,jsonb)` and `public.rosago_admin_operational_overview(text,integer)`, returning scalar JSONB. |
| Existing relations referenced | Mutation reads/locks `public.admin_memberships`, reads/locks/inserts/updates `public.places`. Overview reads/locks membership and reads `auth.users`, `public.profiles`, `public.trips`, `public.trip_places`, `public.places`. |
| Tables/columns created or altered | None. |
| Policies/indexes/triggers created or altered | None. Existing places constraints and its update-timestamp trigger remain active when future RPC writes occur. |
| Other schema effects | Yes: CREATE FUNCTION and function EXECUTE ACL changes are schema changes, even without new tables. |
| Existing data modified during deployment | None. INSERT/UPDATE statements are inside the stored mutation function, not executed by the migration itself. |
| Destructive operations | No DROP, DELETE, TRUNCATE or catalog backfill. EXECUTE revocations intentionally restrict access to the new functions. Future archive is a status update, not deletion. |
| Idempotent? | **No.** CREATE FUNCTION without replacement fails if the exact function already exists. Treat as a one-time transactional migration; do not rerun blindly. |
| 0010 dependency | No direct reference to itinerary-preview adjustment schema/functions. Existing User itinerary behavior may independently need 0010. |
| 0011 dependency | Yes for the supported Tourism write contract: the mutation function references the five editable Tourism columns from 0011. Verify those columns/constraints already exist; do not rerun 0011. A disabled application feature flag is not proof that the full RPC contract is deployable without them. |
| Other prerequisites | Existing places/profiles/trip schemas, membership foundation 0008 and the Admin SELECT policy from 0009 for UI reads; `auth.uid()` and UUID generation supported by the target. Verify current `industrial` category support and publication-coordinate rules. |
| RLS compatibility | No existing policy/grant on User tables is weakened or replaced. The SECURITY DEFINER functions intentionally use trusted-owner privileges beyond ordinary RLS, but first check/lock the caller's membership. The security boundary is the function body plus ownership and EXECUTE ACL, not RLS inside the function. |
| Privileged access | A trusted migration executor/owner with the necessary privileges is required. The intended owner is Supabase `postgres`. The runtime Flask client remains request-owned and authenticated; no application service-role key or browser-side privileged database credential is needed. |
| User-side effects | Applying the function definitions alone changes no destination results. Later explicit Admin writes affect the same places rows used by Explore, Details, maps, Planner and recommendations. Status filtering remains in the public PlacesService. |
| Verdict | **SAFE, static review only**, subject to target verification and the approval/maintenance sequence in sections 10–11. |

Security details: each function uses an empty search path and qualified relations;
membership is determined by `auth.uid()`, never a submitted actor ID. `FOR SHARE`
holds membership against concurrent deletion; destination edits additionally use
`FOR UPDATE` and compare the submitted `updated_at`. Accepted action and field
allowlists exclude identity, source provenance, images and arbitrary status edits.
Create generates a fresh UUID-backed Draft with a new slug. Existing UUIDs/slugs
are resolved and preserved; updates target the existing UUID.

Operational results allow only account ID/email/name/creation time and aggregate
saved-trip usage. User pages are bounded to 25 rows, popularity to ten destinations,
and categories to the existing category domain. Search uses literal `strpos`, not
dynamic SQL or interpolated PostgREST expressions. Account disable/impersonation and
private trip/conversation access are absent.

Rollback considerations: withdraw Admin write access/traffic first. If 0013 has
been applied, undo its wrapper change before removing the 0012 capabilities, using
an operator-reviewed rollback. Removing functions does not reverse valid destination
edits; use the approved backup/checkpoint and specific reviewed recovery decisions.
Do not bulk restore catalog values, statuses, identities or Tourism fields merely
to roll back application capabilities. The BEGIN/COMMIT block is transactional,
but migration failure/recovery must still be checked on the actual target.

## 3. Migration 0013 review

### Production deployment and audit verification — 3 November 2026

**0013 APPLIED AND VERIFIED.** The verified production evidence supplied by the
operator is recorded below. This deployment result supersedes earlier statements
in this report that 0013 is unapplied or awaiting deployment. Earlier reviews are
retained as historical evidence.

This update is documentation only. No production connection, production query,
SQL execution, test run, application-code change, migration change, staging,
commit or push occurred during this documentation work.

**Pre-deployment evidence.** Fresh backups were verified before deployment:

| Backup | Size (bytes) | SHA256 |
| --- | ---: | --- |
| Schema: `backups/rosago_pre_0013_2026-11-03.sql` | 301810 | `594978CDD1A290E64A503AA69B4CA08F782D1789B4DEA6F85C3BF660524D9331` |
| Data: `backups/rosago_pre_0013_2026-11-03_data.sql` | 155979 | `2F5FF099C9EE276EEF5F01E84937360F9BBCBD3E2FFCD9EDCBD321324DF46766` |

Before deployment, `public.admin_destination_audit` was absent,
`rosago_admin_mutate_destination` was present, and
`rosago_admin_mutate_destination_unlogged` was absent. The deployed migration
SHA256 was
`38951C705B6370210CBD935BDFFAFF272CE4D5C2F88418DF877ADCD3EEA082AF`,
exactly matching the locally reviewed 0013 migration.

**Deployment.** `migrations/0013_admin_destination_audit.sql` was executed once
using psql with `ON_ERROR_STOP=1`. Observed output:

```text
BEGIN
CREATE TABLE
ALTER TABLE
REVOKE
GRANT
CREATE POLICY
CREATE INDEX
ALTER FUNCTION
REVOKE
CREATE FUNCTION
REVOKE
GRANT
COMMIT
```

No ERROR occurred during migration execution. The transaction committed
successfully. The migration was NOT rerun.

**Post-deployment structural verification.** `public.admin_destination_audit`,
`rosago_admin_mutate_destination` and
`rosago_admin_mutate_destination_unlogged` all exist. The audit table initially
contained exactly **0 rows**; no historical backfill occurred.

**Audit table security.** RLS is enabled (`true`). Verified table privileges:

| Role | SELECT | INSERT | UPDATE | DELETE |
| --- | --- | --- | --- | --- |
| anon | false | — | — | — |
| authenticated | true | false | false | false |

The dashes indicate privileges not separately reported in this evidence.
Policy `admin_destination_audit_select` has command `SELECT`, role
`authenticated`, and condition `rosago_is_admin()`. The authenticated SELECT
table privilege remains subject to this Admin membership policy.

**RPC execution privileges.** Verified EXECUTE privileges:

| Function | anon | authenticated | service_role |
| --- | --- | --- | --- |
| `rosago_admin_mutate_destination` | false | true | false |
| `rosago_admin_mutate_destination_unlogged` | false | false | false |

**Controlled functional test.** The existing temporary destination
"RosaGo Admin 0012 Verification Test" was edited once through the normal Admin UI.
Only its description was intentionally changed to:

> Temporary destination created for RosaGo Admin production verification. 0013 audit test passed.

Its status remained **Archived**. Immediately before this test the audit table
contained **0 rows**. Immediately after, exactly **1 audit row** existed with:

- action = `edit`;
- destination = `RosaGo Admin 0012 Verification Test`;
- resulting_status = `archived`;
- summary recording the submitted field names.

No historical events were backfilled.

**Final catalog sanity check.** Counts match the expected pre-test checkpoint:

| Total | Published | Draft | Archived |
| ---: | ---: | ---: | ---: |
| 49 | 34 | 2 | 13 |

**Verification query note.** Two verification SELECT attempts used incorrect
column names (`change_summary` and `publication_status`) and returned SQL errors.
These were failed read-only SELECT statements and made no production changes.
Corrected queries subsequently passed. These verification errors were separate
from the successful migration execution above.

**Final conclusion.** 0013 deployment succeeded, and the audit wrapper works
through the normal Admin UI. The successful Admin edit generated exactly one
correctly associated audit event. No direct authenticated bypass to the unlogged
mutation function was found. Under the verified privileges, ordinary
authenticated callers cannot directly insert, update or delete audit history.
This does not establish tamper-proof protection against database owners or
superusers. No unintended destination count/status change was identified.
No additional production write test is required.

```text
0013 LIVE STATE: APPLIED AND VERIFIED
0013 PRODUCTION DEPLOYMENT: PASS
0013 AUDIT FUNCTIONAL TEST: PASS
UNINTENDED DESTINATION CHANGES IDENTIFIED: 0
PRODUCTION CHANGES DURING DOCUMENTATION: NONE
GIT STAGED/COMMITTED/PUSHED: NO

ROSAGO 0013 PRODUCTION DEPLOYMENT AND AUDIT VERIFICATION: PASSED
```

### Historical final local pre-deployment review — 3 November 2026

**0013 REVIEW RESULT: PASS, local source review only. DO NOT DEPLOY YET.**
Reviewed exact SHA-256
`38951C705B6370210CBD935BDFFAFF272CE4D5C2F88418DF877ADCD3EEA082AF`.
0012 has passed the operator functional test; the two intentional original-record
edits are explained by the operator clarification above. 0013 remains unapplied
according to the established state; no production connection or refresh occurred.

**Objects and deployment effects.** Creates `public.admin_destination_audit` with
six required columns: UUID primary-key `id` defaulted by `pg_catalog.gen_random_uuid()`,
UUID `actor_id`, text `action`, UUID `destination_id`, timestamptz `occurred_at`
defaulted by `pg_catalog.clock_timestamp()`, and JSONB `summary`. Adds the ID primary
key/index, six-action CHECK and destination FK to `public.places(id)` with
ON DELETE RESTRICT. The FK creates PostgreSQL internal referential-integrity
triggers on the referencing/referenced tables; there is no user-defined audit
trigger or change to the existing places updated_at trigger. Creates time index
`admin_destination_audit_time_idx(occurred_at DESC,id)`, enables audit-table RLS,
and creates authenticated Admin-only SELECT policy `admin_destination_audit_select`.
The table also has PostgreSQL's automatic composite/array types. No sequence,
view, extension, schema or other application relation is explicitly created.

Renames the exact 0012 mutation function to
`rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)` without
altering its body, signature/result, security settings or owner. Revokes all
PUBLIC/anon/authenticated/service_role EXECUTE from this inner function. Creates
a new SECURITY DEFINER wrapper under the original public name, same named
arguments and JSONB result, with empty search_path. Revokes those same roles
before granting authenticated EXECUTE only. Audit-table privileges are revoked
from the same four roles, then authenticated receives SELECT only. Existing
operational overview and other Admin functions/policies are unchanged.

**Existing destination data mutation: NO at deployment.** No catalog INSERT,
UPDATE, DELETE, backfill or historical audit insertion executes in the migration.
Catalog values, publication, IDs/slugs and timestamps remain untouched. Future
explicit RPC mutations retain their 0012 effects and gain an audit INSERT.
Past intentional edits and the existing archived temporary record are not audited
retroactively. The new FK affects future hard deletion of referenced destinations.

**Transaction safety: PASS by source review.** One BEGIN/COMMIT encloses all DDL
and ACL operations; there is no concurrent-index or other transaction-prohibited
statement. A statement error aborts the transaction, so its changes cannot commit;
rollback/disconnect restores the prior state. An interrupted connection with an
open transaction may retain locks until rollback/disconnect. Use a fail-fast
trusted execution path, and do not split the file or resume at an interior line.
Rename, grants and wrapper installation have no committed intermediate exposure.
DDL locks may block concurrent work; pause Admin writes during deployment.

**Re-execution: UNSAFE / non-idempotent.** First execution on the verified clean
prerequisite state installs the objects atomically. A genuinely rolled-back first
attempt leaves them absent and can be retried only after checking the failure and
state. After successful commit, a second full execution fails at CREATE TABLE;
its transaction is aborted rather than installing another wrapper/audit layer.
If commit acknowledgment is lost, inspect actual objects before any retry.

**Dependencies and ownership.** Requires the exact verified 0012 mutation function,
its caller-membership validation/locks and returned slug/status contract; existing
unique places slug and UUID PK; `rosago_is_admin()`, `auth.uid()`, and the existing
client roles. The migration does not explicitly assign owners. Execute as the
trusted postgres owner with the required table/function/schema rights; review
does not authorize execution. No direct dependency on operational overview or
0010 is added. The inner function keeps its OID, so preexisting database objects
bound to that OID retain the inner identity; this wrapper is not a universal
trigger for every trusted/database write. The inspected Flask path calls the
public RPC name through PostgREST, not an OID-bound database caller.

**Audit integrity and security: PASS within these boundaries.** The inner function
first authorizes `auth.uid()` against locked Admin membership and validates the
action, fields, target and expected timestamp. The wrapper obtains the destination
ID using the returned unique slug, then inserts exactly one event per successful
wrapper call. Actor is the caller's Auth UUID, not supplied actor data; it has no
Auth FK so attribution survives account removal. Summary contains submitted field
names and resulting status only. It stores no old values, new field values, prior
status, email, credentials, request identifier or failure details. Event time is
database clock time at audit insertion. All six create/edit/publication actions
are logged, including restore; no failure/security-event feed is created.

An inner validation/authorization/stale-write failure prevents insertion; a target
lookup or audit failure propagates and rolls back the mutation. A later outer
transaction rollback removes both. Exactly one event means per committed wrapper
invocation, not deduplication of repeated client requests. The application disables
automatic mutation retries and retains the same RPC argument/response contract.

No dynamic SQL, interpolated identifier or caller-selected actor exists. Referenced
application/auth objects are schema-qualified; built-ins resolve through pg_catalog
with empty search_path. Wrapper ownership by postgres permits audit insertion
despite RLS; ordinary callers cannot bypass the inner membership guard. Table
SELECT is membership-policy gated; ordinary non-Admins cannot read history.
There are no client INSERT/UPDATE/DELETE/TRUNCATE grants or write policies.
service_role's BYPASSRLS does not replace the revoked object privileges. History
is append-only for ordinary authenticated/Admin application callers, who also
cannot execute the inner function directly. Owners/superusers can still change
history or write outside the wrapper: this is not a tamper-proof ledger, nor does
it audit arbitrary direct SQL. No audit-viewing UI is added automatically.

**Regression risk: LOW.** The core mutation body and public contract are preserved.
New intentional failure modes are strict result lookup and audit persistence/FK
failure, which now fail the whole mutation. RLS/ACL misconfiguration, an untrusted
executor, or stale API metadata must be excluded by deployment verification.

**Syntax: PASS, static review.** Complete wrapper/DDL delimiters, RETURN/INTO STRICT,
ARRAY subquery and transaction boundaries were inspected; no analogue of 0012's
IF/CASE parenthesis defect was found. The single existing focused static test
`tests/test_admin_management.py::ManagementMigrationTests::test_sql_authorization_privacy_lifecycle_and_audit_contract`
passed in 1.20 seconds. It checks SQL strings only, not database syntax compilation,
authorization execution or rollback. No full suite was run. The optional local
Docker availability check could not access the daemon; no accessible disposable
PostgreSQL instance was established and no database SQL was executed.

**Backup: CREATE NEW PRE-0013 BACKUP/checkpoint before deployment.** The verified
pre-0012 backups remain historical recovery material but omit the deployed 0012
objects, subsequent intentional edits, temporary verification record and any later
application changes. Capture and verify the current schema/data/security state,
exact migration checksum and restore procedure with writes paused. Do not rely
on the older checkpoint alone for immediate 0013 recovery. No backup was created
during this review, and no automatic down migration is supplied.

**Minimum verification after separately authorized deployment:**
1. Confirm exact target and committed objects: table columns/defaults/constraints,
   FK/internal triggers, indexes, owner, RLS/policy and effective table/column ACLs.
   Audit starts empty before any first authorized mutation; there is no backfill.
2. Compare inner body/settings to verified 0012; confirm wrapper signature/body,
   postgres owner, SECURITY DEFINER and empty search_path. Verify no ordinary
   client EXECUTE on inner, authenticated-only public wrapper EXECUTE, unchanged
   operational function, and intended PostgREST RPC resolution/cache state.
3. Compare catalog and application schema against the new immediate checkpoint;
   no deployment-time catalog differences are expected. Retain the intentional
   edits and archived temporary destination in that baseline.
4. Before reopening ordinary writes, verify one authorized isolated test action
   yields exactly one correctly attributed event and unchanged response contract;
   verify non-Admin denial and inability to forge/edit/delete audit history.
   Use a disposable local/isolated database for induced audit-failure rollback,
   not deliberate production constraint failure. If live test writes are used,
   they require separate authorization; preserve their audit events and archive
   the test destination. No such testing is performed or authorized here.

**Source-review blockers: None.** A fresh verified checkpoint and deployment
authorization remain required next steps, not completed by this review.
Only this existing 0013 review section was updated; no code, migration, production
data, staging, commit or push was changed/performed.

**ROSAGO 0013 PRE-DEPLOYMENT REVIEW: PASSED — DO NOT DEPLOY YET; CREATE/VERIFY PRE-0013 CHECKPOINT FIRST**

### Retained earlier 0013 source review

Exact file: `migrations/0013_admin_destination_audit.sql`.

Purpose: persist one minimal audit event with each successful administrative
destination RPC, atomically with the destination mutation.

| Review item | Finding |
| --- | --- |
| Table created | `public.admin_destination_audit`: UUID ID, actor UUID, action enum CHECK, destination UUID, timestamp, JSONB summary. |
| Constraints | Primary key on ID; destination FK to `public.places(id)` with `ON DELETE RESTRICT`; required columns; six-action CHECK. No Auth FK on actor, preserving historical UUID attribution if an account is removed. |
| Policy/ACL | Enables RLS on the new table; revokes client table privileges then grants authenticated SELECT with `admin_destination_audit_select`, using `rosago_is_admin()`. No direct client INSERT/UPDATE/DELETE. |
| Index | `admin_destination_audit_time_idx(occurred_at DESC,id)` plus the primary-key index. |
| Functions changed | Renames the 0012 mutation function to `rosago_admin_mutate_destination_unlogged`; revokes its client EXECUTE; creates a SECURITY DEFINER wrapper under the original public RPC name/signature. |
| Triggers | No user-defined audit trigger. The destination FK creates PostgreSQL internal referential-integrity triggers; audit is a wrapper insertion. |
| Schema/data effects | Creates new schema objects and changes function naming/ACLs. No existing catalog rows or history are backfilled/changed during deployment. |
| Destructive operations | No deletion/truncation/drop/backfill. Function rename and revocations deliberately change access. The new FK prevents future hard deletion of destinations with audit history, including trusted-operator deletes unless separately resolved. |
| Idempotent? | **No.** Existing audit table/index/policy or the prior rename will cause conflicts on rerun. |
| Dependencies | Requires reviewed 0012 with its exact signature, existing places UUIDs, `auth.uid()`, membership and `rosago_is_admin()` support. Inherits the full 0012 operational prerequisites. No direct 0010 dependency. |
| RLS compatibility | Adds only audit-table RLS; leaves existing User table policies unchanged. The wrapper relies on the independently authorizing inner function and trusted-owner execution rights. |
| Service role | No service-role application key required. Trusted database executor/owner and verified ACLs required. |
| User effects | No immediate catalog change. Future writes also require successful audit insertion and can therefore fail/roll back if audit persistence fails; public catalog reads remain unchanged. |
| Verdict | **SAFE, static review only**, after verified 0012 and with privileges/atomic rollback tested before live traffic. |

Only **durable destination audit logging** depends on 0013. CRUD, Users and Trips
do not technically require it; 0012 alone permits unaudited destination writes.
If logging must start with the first write, keep writes unavailable until both
migrations have been approved, applied and verified. No application Audit Logs page
is implemented. The System & Weather notice is static text about pending audit
verification; deploying 0013 does not automatically add a feed or make that notice
a reliable live capability indicator.

Rollback: stop writes first. Preserve/export audit history before any schema rollback.
An operator must restore the original mutation RPC naming/ACL contract, not simply
drop the new audit table while leaving its wrapper active. Removing the wrapper
would remove automatic logging, so that is a deliberate operational decision. Do
not delete audit rows to bypass the destination FK. The migration supplies no
automatic down migration; this review does not execute or generate one.

## 4. Admin feature → migration dependency matrix

“Before deployment” assumes existing Admin authorization/read schema and the
current Tourism rollout configuration are already working. It does not assume
0012 or 0013 has been applied. Opening a form is not a successful mutation.

| Feature | 0012 required | 0013 required | Works before deployment | Code evidence |
| --- | --- | --- | --- | --- |
| Destination list/detail | No | No | Yes, existing read prerequisites | `admin_routes.places`, `_destination_page`; `catalog_page`, `get_destination` |
| Destination Create | Yes | No | Form renders; saving unavailable | `_destination_form` → `mutate_destination` → `rosago_admin_mutate_destination` |
| Destination Edit | Yes | No | Form renders; saving unavailable | Same mutation chain, action `edit` |
| Publish | Yes | No | Confirmation renders; mutation unavailable | `publication` → action `publish` |
| Move to Draft | Yes | No | Confirmation renders; mutation unavailable | `publication` → action `draft` |
| Archive | Yes | No | Confirmation renders; mutation unavailable | `publication` → action `archive` |
| Restore | Yes | No | Confirmation renders; mutation unavailable | `publication` → action `restore`, SQL targets Draft |
| Users oversight | Yes | No | Unavailable state / HTTP 503 | `users` → `operational_overview` RPC |
| Trips oversight | Yes | No | Unavailable state / HTTP 503 | `trips` → same overview, directory removed from template values |
| Audit logging | Yes | Yes | No persisted logging from this implementation | 0013 wrapper calls renamed 0012 function, then inserts audit |
| Audit Logs page | No page | No page | Not implemented, even after deployment | No route/feed; do not equate table support with a UI |
| Catalog Insights | No | No | Yes, existing bounded reads | `insights` → `catalog_insights` → `read_catalog` |
| System & Weather | No | No | Yes, forecast or safe unavailable state and catalog review | `system` uses existing weather extension and `catalog_insights` |
| Dashboard | Partial | No | Publication/health/attention work; user/trip counts unavailable | `index` uses existing reads and optional `_overview_or_none` |
| Account/Settings/Help/About/Logout | No | No | Yes, existing auth/profile/theme capabilities | Existing utility/logout routes |

After 0013, the **same public mutation RPC name/signature** gains audit behavior;
Flask does not select a separate logged/unlogged endpoint.

## 5. Catalog and data safety

Inspection confirms no deployment-time catalog UPDATE/INSERT/DELETE, imports,
Tourism transition execution or metadata-file write. The stored function bodies
must not be confused with statements executed merely by defining those functions.

| Concern | Actual behavior |
| --- | --- |
| NULL Tourism Type → Common | No COALESCE/default to Common. Explicit JSON NULL stays NULL. |
| Invented coordinates | None. Coordinates come only from a future explicit validated Admin submission. |
| Tourism metadata modifications | None on deployment. Future explicit create/edit can write the five allowed Tourism fields as required by management; source/source-row are not editable. It would be inaccurate to say the RPC can never modify Tourism metadata. |
| Draft republishing | None automatic. Only explicit `publish` from Draft is accepted. |
| Archived restoration | None automatic. Only explicit `restore` from Archived, targeting Draft. |
| Historical deletion | No hard-delete path. Archive retains records, existing memberships and IDs. |
| Tourism transition | Not invoked; neither historical transition SQL nor 0010/0011 is rerun. |
| UUID/slug overwrites | Existing values are unchanged; new records receive new identities. |
| Recommendation classifications/logic | No ranking/selection code or bulk classification operation in either migration. A future explicit destination Tourism edit intentionally changes that record's shared metadata. |
| Weather sidecar | Neither SQL file nor write service writes `weather_metadata.json`. Identity edits can cause an old curated match to become Unknown until separately reviewed. |

The user-described Tourism-backed/RosaGo-only/published/draft/archived catalog and
nullable metadata/coordinates are compatible with the intended contract. No live
catalog snapshot was queried in this review, so the current deployed schema and
row counts remain unverified. The original 0002 publication-coordinate CHECK and
six-category CHECK differ from the later current catalog contract: verify actual
target constraints rather than rerunning the Tourism scripts to “repair” them.

Historical checksum diagnostics independently confirmed 0011 is unchanged and the
weather file matches its documented pre-reconciliation baseline when the existing
identity-only reconciliation normalization is applied. The ranking/selection hashes
are different, as expected from the later Local/NULL/Common/geographic policy;
see F6 and F7. Review-start hashes cover 330 non-documentation files and provide
separate byte-for-byte evidence that this review changed none of them.

## 6. Security review

| Requirement | Evidence / result |
| --- | --- |
| Server-side Admin authorization | `admin_required` wraps every management/operational route with normal authentication and a fresh Boolean `rosago_is_admin()` result. Both 0012 RPCs independently check `auth.uid()` membership under a lock. |
| Unauthenticated/nonmember mutations | Denied before mutation work; integration tests cover every mutation family. No hidden role field or browser role flag supplies authority. |
| CSRF | `_valid_mutation_form` requires the existing server-session coordinator token before destination read/write work. |
| Origin | `_strict_form` requires exact Origin == request origin, no files, exact fields and one value per field. Missing/null/foreign Origin and duplicated fields are rejected. |
| Action/publication validation | Python action allowlist and SQL action/transition allowlists. Edit cannot submit arbitrary status; Create hardcodes Draft; Restore targets Draft. |
| Coordinates | Python numeric/finite/range/pair checks; SQL numeric/null JSON types, ranges/pair checks, and existing DB constraints. |
| Tourism Type/hours | Server-side exact Local/Common/NULL and existing hours-status enum validation, with optional text bounds; SQL validates the same domain. |
| Concurrency | Destination lock plus expected timestamp; original submitted version retained on failed/stale edit. Membership row locked until transaction completion. |
| Browser secrets | Admin forms/templates receive display projections and CSRF, not service-role keys, privileged DB credentials, password hashes, OTP/recovery grants or full Auth objects. Request authority is removed during Jinja rendering. Admin JS handles disclosures; it does not call a privileged client API. |
| Authentication token handling | Existing authenticated Supabase bearer stays on the request-owned server client; opaque app session reference remains the browser session boundary. No new unnecessary access-token exposure was found. |
| Public/User isolation | Public PlacesService still explicitly filters Published. Operational RPC returns an allowlist; no broad cross-user SELECT policy on Auth/profiles/trips is added. |

Cookie-authenticated Flask mutations require CSRF/Origin. A direct Supabase RPC
authenticated with its own bearer is a different boundary: it enforces database
membership and validation, not Flask CSRF. The SQL does not pretend to validate a
browser CSRF token. Post-deployment anonymous/nonmember RPC checks remain required.

No new security defect requiring a production fix was established in this review.
Transport doubles/static SQL assertions do not verify real database ownership,
privilege inheritance, PostgREST cache/exposure or transaction behavior. No live
configuration secrets were opened, printed or captured to fill these gaps.

## 7. Audit-log review

The wrapper records **successful mutation RPCs only**, including a successful
no-op edit. Authorization, validation, stale-write, database or logging failures
leave no audit row in this table. There is no failed-attempt/security-event feed.

Stored fields: actor UUID from `auth.uid()`, action, existing destination UUID,
clock timestamp, and a JSONB summary containing **submitted field names** and
resulting publication status. Submitted names are not a computed diff: unchanged
fields may be listed. There are no previous/new field values, passwords, tokens,
OTP, recovery grants, full Auth objects, prompts, notes, budgets or secrets.

The inner mutation completes before the log INSERT within the same RPC transaction.
A failed audit INSERT rolls back the destination change. Client execution of the
renamed unlogged inner function is revoked; wrapper execution remains authenticated
and inner membership authorization still runs. This must be confirmed using direct
RPC negative tests after approval. No persisted data is assumed merely because a
migration file exists; 0013 remains unapplied.

## 8. Triage of all seven failures and two errors

All IDs below reproduced both in the full suite and independently. Area and Admin
relationship refer to the actual failing code path, not just the test filename.
History categories: A production regression, B stale expectation, C environment,
D flaky/external, E fixture/context problem, F unknown.

### E1 — Login dashboard error

- **Test:** `tests/test_login_dashboard_redirect.py:16`,
  `DashboardLoginRedirectTests.test_normal_login_lands_on_existing_authenticated_dashboard_and_profile_remains`.
- **Area:** User/auth/dashboard. **Failure:** `TypeError: An active AuthenticatedContext is required.`, at test line 24 → `app.py:427` → `list_dashboard_upcoming_trips` → `trip_service.py:102`.
- **Expected:** login 303 to `/`, followed by Dashboard 200 and retained Profile access.
- **Actual:** login does return 303 `/`; following it reaches the new dashboard upcoming-trip reader and fails the trip-service calling contract before rendering.
- **History/classification:** **E, stale fixture**, not a demonstrated auth regression. `LoginTests` uses synthetic `user-123` and inherits a client with only `table`/`close`. Diagnostics show AuthenticatedContext type is correct, table callable is true, RPC callable false, UUID validity false. The test mocks `list_user_trips`, while Dashboard now calls `list_dashboard_upcoming_trips`. The trip contract requires table/RPC and a UUID. Earlier login documentation claims a passing focused run, but its older fixture coverage does not establish that today's reader is mocked correctly.
- **Related to Admin changes:** **NO** direct failing path; it is normal User Dashboard/trip code and a User fixture. The previous final report's “profile service” diagnosis was incorrect.
- **Recommended action:** **fix test isolation/fixture** with a valid trip-capable authenticated fixture or the exact dashboard reader double; preserve redirect/Profile assertions. Do not weaken the production contract or catch TypeError to hide it.

### E2 — Direct Map template context error

- **Test:** `tests/test_map_routes.py:202`,
  `MapRouteTests.test_shared_template_autoescaping_remains_enabled`.
- **Area:** shared User shell/Map. **Failure:** `jinja2.exceptions.UndefinedError: 'website_settings' is undefined` at test line 208.
- **Expected:** directly render a child of `map.html`, then assert escaped hostile title text and shared scripts.
- **Actual:** `template.render(...)` does not run Flask's template context processors; `base.html` reads `website_settings.personalized` and `.location_enabled`. Normal Flask rendering receives this value from `app.py:133–135`.
- **History/classification:** **E, incomplete rendering fixture**. This is exactly the same named exception/context omission documented in Phase 2 lines 243–250, confirmed against today's source and fresh isolated trace.
- **Related to Admin changes:** **NO**; Admin has its own shell and this path renders User `map.html`/`base.html` directly.
- **Recommended action:** **fix test isolation/context**, exercising the normal render pipeline or supplying required shared context while retaining the autoescaping assertions. No production fallback is justified by this direct-render fixture.

### F1 — Alerts wording

- **Test:** `tests/test_final_ui.py:51`,
  `FinalUiTests.test_planning_modes_use_existing_actions_and_unsupported_controls_are_removed`.
- **Area:** User Planner/Alerts. **Failure:** line 63 expects `Weather is temporarily unavailable` in Alerts HTML.
- **Expected:** that exact older phrase, then the old saved-trip reminder-window phrase.
- **Actual:** with weather mocked unavailable, current `templates/user/alerts.html` renders `Weather information is temporarily unavailable.` and its notification-based empty state, not the old trip-window copy. Diagnostic checks confirm both old strings are absent; the current weather fallback is present. Planning forms and manual-trip assertions preceding this check pass.
- **History/classification:** **B, stale presentation expectation**. The current Alerts template, not a provider request, explains the deterministic mismatch. No external dependency or Admin page participates. Earlier Final Admin recorded this failure, but its cause is now independently checked.
- **Related to Admin changes:** **NO**.
- **Recommended action:** **update test** to current semantic weather/notification states, retaining failure-safe and privacy assertions. Review the later reminder assertion too; changing only the first string would expose a second stale expectation.

### F2 — Legacy Planner selection step

- **Test:** `tests/test_functional_completion.py:145`,
  `PlannerSelectionFlowTests.test_review_reaches_recommendations_selection_and_persisted_preview`.
- **Area:** User itinerary UI/flow. **Failure:** line 154, `AssertionError: [] is not true`, expecting a recommendation-page form targeting `/selection`.
- **Expected:** Review → Recommendations → separate Selection page → Preview submission.
- **Actual:** recommendation GET is 200; current `personalized-recommendations` form posts directly to `/preview` via `itinerary_preview_build`. This is explicitly asserted by the passing `test_personalized_recommendations_ui.PersonalizedRecommendationsUiTests.test_default_selected_order_reasons_and_direct_preview_contract`. The existing legacy selection route was not removed, but the current UI does not require it.
- **History/classification:** **B, stale UI flow expectation**. Actual parsed form actions are saved in diagnostics. Current targeted tests and the direct-preview template agree; a missing obsolete form is not evidence that Preview persistence broke.
- **Related to Admin changes:** **NO**.
- **Recommended action:** **update test** to drive the actual direct-preview flow and retain persisted-state/revision/auth assertions. Do not restore a UI step just to satisfy the old selector.

### F3 — Map hostile-marker script count

- **Test:** `tests/test_map_routes.py:212`,
  `MapRouteTests.test_hostile_marker_text_cannot_break_json_or_create_markup`.
- **Area:** shared User shell/Map. **Failure:** line 219, `AssertionError: 7 != 5`.
- **Expected:** exactly five scripts around the hostile-marker case.
- **Actual:** the shared shell also loads `theme.js` and `account-management.js`, giving seven scripts. The test fails on count before its later security checks can complete; this count failure itself does not demonstrate an escaping defect.
- **History/classification:** **B, stale asset-list expectation**. Phase 2 names the same test, five-versus-seven mismatch and unchanged User-shell cause. Current `theme_head.html`/`base.html` and isolated output confirm it.
- **Related to Admin changes:** **NO**; the assets are loaded by the User shell, not the separate Admin shell.
- **Recommended action:** **update test** to current approved assets or meaningful script identities; retain all hostile payload, JSON escaping and no-injection checks.

### F4 — Map layout asset expectations

- **Test:** `tests/test_map_routes.py:78`,
  `MapRouteTests.test_shared_layout_conditional_local_assets_and_active_map`.
- **Area:** shared User shell/Map. **Failure:** line 93 compares actual `['/static/css/theme.css','/static/css/site.css']` with expected `['/static/css/site.css']`.
- **Expected:** pre-theme stylesheet list; the later populated branch also assumes old script counts/order.
- **Actual:** the shared pre-paint theme include intentionally adds theme.css/theme.js; other current shared scripts remain present.
- **History/classification:** **B, stale asset-list expectation**. Same test and missing-theme mismatch documented in Phase 2 and independently reproduced now. Fixing only the first stylesheet assertion will not modernize the later populated-Map branch.
- **Related to Admin changes:** **NO**.
- **Recommended action:** **update test** for current shared assets while retaining conditional Leaflet loading, active navigation, empty-map and referrer-policy checks.

### F5 — Profile source-string assertion

- **Test:** `tests/test_trip_routes.py:117`,
  `TripRouteTests.test_reads_forms_account_link_and_unavailable_place`.
- **Area:** User Trips/Profile/navigation. **Failure:** line 137, literal `My Trips` absent from the source of `templates/user/index.html`.
- **Expected:** the string occurs directly in that child template source.
- **Actual:** Profile inherits `base.html`; the shared `partials/navigation.html` supplies the working My Trips navigation link. The source-string check does not inspect the rendered inherited navigation.
- **History/classification:** **B, stale source-location expectation**. Phase 1 lines 188–193 documents this exact test, literal and template. Today's template inheritance/shared navigation and isolated trace match that evidence.
- **Related to Admin changes:** **NO**.
- **Recommended action:** **update test** to assert the rendered working navigation target, preserving the rest of the trip/read/unavailable-place behavior.

### F6 — Historical protected-file hashes

- **Test:** `tests/test_tourism_transition.py:180`,
  `TourismTransitionTests.test_protected_weather_ranking_selection_and_0011_files_unchanged`.
- **Area:** Tourism/catalog and recommendation policy. **Failure:** line 188, first mismatch is `recommendation_engine.py`: actual `ad5622f1…` versus historical `48b3f8c3…`.
- **Expected:** all files still match `tourism_transition_plan.json`'s pre-policy-change protected hashes (with the test's weather identity reconciliation exception).
- **Actual:** 0011 still matches; weather still matches after the existing documented reconciliation normalization. Ranking and selection hashes differ. Full exact hashes are in diagnostics. Current ranking version is `category-interest-tourism-v2`; selection is `pace-count-category-tourism-cluster-v3`, reflecting later intended changes already described by the Admin audit.
- **History/classification:** **B, stale historical phase boundary**, not proof of unauthorized edits during Admin work. The hash assertion is valid evidence of byte differences from its old baseline, but its “forever unchanged” expectation conflicts with the later approved policy. The assertion stops at ranking; separate diagnostics also checked selection rather than assuming only one file differs.
- **Related to Admin changes:** **NO** direct dependency; migrations do not alter these files and current expected policies predate Final Admin. Exact chronology of every dirty-worktree edit cannot be reconstructed from an uncommitted tree alone.
- **Recommended action:** **update test scope** to distinguish immutable transition evidence from current policy contracts. Preserve the original historical plan/hashes; do not blindly replace them with current digests to turn the suite green.

### F7 — Tourism Type ranking neutrality

- **Test:** `tests/test_tourism_transition.py:190`,
  `TourismTransitionTests.test_recommendation_scores_and_selection_do_not_read_tourism_type`.
- **Area:** User recommendation/Tourism policy. **Failure:** line 197, recommendation objects differ before/after Tourism metadata.
- **Expected:** entire ranking result and selection are unchanged by Tourism Type.
- **Actual:** `TOURISM_PRIORITY = {'Local':0, None:1, 'Common':2}` changes candidate priority/order among category matches; the deterministic category score remains separate. Current recommendation tests explicitly require Local → unclassified → Common and geographic selection among comparable candidates.
- **History/classification:** **B, superseded policy expectation**. The current code, current policy tests, recommendation template explanation and pre-Final-Admin audit all agree on Tourism priority. The old assertion predates that behavior.
- **Related to Admin changes:** **NO**; implementing Admin writes did not introduce or rewrite this policy.
- **Recommended action:** **update test** for the current documented policy while preserving category eligibility, score semantics, NULL handling and geographic behavior. Do not make production ranking ignore Tourism Type to satisfy it.

Historical comparison summary: **three Map issues and the Profile-source issue are
specifically corroborated by earlier phase reports and today's matching traces**.
The Alerts/Planner/policy findings are supported by current independent diagnostics
and later intended contracts; their first introduction date is not proven by the
available uncommitted history. All nine were already in the saved Final Admin full
run, and none is newly introduced between that run and this review. The login
error is a fixture-contract issue with a corrected root-cause diagnosis.

## 9. Dirty-worktree review

Commands inspected: `git status --short --untracked-files=all`, `git diff --stat`,
`git diff --check`. No index writes or stage/commit/push/reset/restore/clean occurred.

At the inventory checkpoint: **75 modified status paths, 924 untracked paths,
0 staged paths**, including this review's evidence. `git diff --stat` reports
**74 files, 3,573 insertions, 2,249 deletions**; it omits all untracked content.
`tests/test_itinerary_preview.py` is marked modified in status but has no diff in
`git diff --name-only`; this stat/content discrepancy was left untouched. Counts
increase as report/evidence files are added; final status is saved separately.
`git diff --check` exits **0**. Existing CRLF notices and unreadable `.pytest_cache`
warnings are recorded, not silently “fixed.”

Categories below are organizational tags, **not exclusive ownership or proof of
which phase authored each line**. Shared Admin files span phases. The CSV assigns
every changed/untracked path to a category, with overlaps explicitly retained.

| Requested area | Representative files / boundaries |
| --- | --- |
| Auth/legal | `auth_helpers.py`, `password_policy.py`, `email_verification.py`, Auth templates, auth/reset/verification JS, legal/privacy/terms partials. |
| AI explanations | `gemini_service.py`, `assistant_context.py`, `assistant_store.py`, AI integration documentation and assistant UI. |
| Itinerary conversation | `itinerary_adjustment.py`; assistant/chat and preview UI also overlap this flow. |
| Weather | `weather_service.py`, `itinerary_weather.py`, `weather_proposal.py`, `destination_weather_metadata.py`, alerts service/UI and forecast partials. |
| Tourism/catalog | `place_model.py`, `places_service.py`, `place_search.py`, `tourism_catalog_transition.py`, `data/santa_rosa_places/`, Tourism UI. |
| User UI/UX | Shared base/navigation/footer, User dashboard/Profile, Explore/Map, trip and itinerary templates, shared tokens/theme/button assets; root `app.py` spans many areas. |
| Recommendation/geographic logic | `recommendation_engine.py`, `itinerary_selection_policy.py`, `itinerary_geography.py`; corresponding current behavior tests. |
| Admin Phase 1 | `admin_dashboard_service.py`, dashboard/header/CSS/theme integration, Phase 1 evidence; shared `admin_routes.py`. |
| Admin Phase 2 | `admin_places_service.py`, destination list/detail/form/lifecycle/error templates and catalog filters; Phase 2 evidence. |
| Admin Phase 3 | `admin_insights_service.py`, Insights template and distributions/attention; Phase 3 evidence. |
| Admin Phase 4 | Account/Settings/Help/About templates, utility routes/account menu and Phase 4 evidence. |
| Final Admin | `admin_management_service.py`, publication/Users/Trips/System templates, writable forms/routes, 0012/0013, `test_admin_management.py`, final-admin evidence. |
| Migrations | Untracked 0010, 0011, 0012, 0013 and the 0012 design note; they are not proof of deployment. |
| Tests | 78 changed/untracked test paths at inventory time, spanning current features and historical expectations; no test was edited during review. |
| Documentation/evidence | Hundreds of reports, test outputs, browser scripts/results/screenshots under `docs/`, plus integration/operational documents. Phase-tag counts overlap these paths. |

Items requiring intent/privacy review before a future commit, without deleting them:

- Root `rosago.html` is a standalone prototype HTML artifact, outside Flask's
  template directory, with different fonts. Confirm its intended retention; it
  should not be mistaken for the runtime Admin implementation.
- Large untracked `docs/` and screenshot trees include past live verification
  captures with allowed account identity. Review intended distribution and privacy
  before publishing; this was not a complete visual/secret audit of all evidence.
- Multiple untracked migration stages must not be deployed by filename order or
  “apply all”; 0010/0011/transition SQL explicitly must not be rerun.
- The status-only modified test path above is an anomaly to inspect later; no
  reset/restore was used to hide it.
- Filename inspection found no new `.tmp`, `.har`, private-key or database bundle
  in the changed/untracked inventory. This is not a claim of a complete secret scan.

No suspicious artifact was removed. Review-start hashes of all 330 selected
non-documentation tracked/untracked files remain identical after review.

## 10. Deployment prerequisites

1. Approve the nine classifications and correct the stale tests/fixtures in a
   separately authorized task. Preserve security coverage and historical evidence.
2. Rerun the full suite until there are no unexplained failures; investigate any
   genuine application issue uncovered by corrected tests rather than suppress it.
3. Review the actual target's existing schemas, constraints, triggers, memberships,
   ownership, grants, RLS and deployed migration history. Source comments and a
   prior browser run are not an authoritative migration ledger.
4. Confirm 0011's existing Tourism contract and current category/publication rules;
   do not rerun old migrations or imports. Independently confirm 0010 if required
   by existing User preview functionality, not because 0012 directly depends on it.
5. Establish a trusted database executor/owner and a reviewed rollback/checkpoint
   plan. No service-role key needs to enter Flask or the browser.
6. Decide whether audit must cover the first live destination write. For the final
   system, deploy 0012 and 0013 as an approved pair with writes stopped between them.
7. Obtain explicit migration approval and a verified database backup/checkpoint.
8. Arrange an approved isolated database verification environment and a clearly
   named Draft live smoke-test record, if needed; preserve real Tourism records.

## 11. Recommended deployment order — proposal only

1. In a separate authorized change, fix the seven obsolete assertions and two
   fixtures; rerun full Python/Admin/User/JS tests and inspect the resulting diff.
2. Complete target-schema, privilege, ownership and data-preservation preflight;
   approve both migration files and the rollback plan. Take/check the backup.
3. With separate permission, execute the reviewed pair in an isolated target first.
   Validate SQL/runtime behavior, rollback and all direct RPC negative tests there.
4. Freeze/stop production Admin write traffic for the live migration window. The
   current application already has mutation routes; 0012 can enable them before
   an application restart. Do not leave an unaudited active gap before 0013.
5. Apply **0012 once** using the trusted migration executor; verify signatures,
   owners/ACLs and target constraints before proceeding. No 0010/0011/transition rerun.
6. Apply **0013 once** before restoring write traffic. Verify audit table RLS/ACLs,
   wrapper resolution and denial of client calls to the renamed unlogged function.
7. Verify/refresh the Supabase API schema exposure/cache through the approved
   operator process; verify scalar JSON RPC responses and no extra projected fields.
8. Verify successful mutation+audit atomicity and forced audit-failure rollback;
   anonymous/nonmember denial, revoked membership, stale versions, enums, coordinate
   pairs, and each allowed/disallowed status transition. Do not use real Tourism
   records for destructive or exploratory probes.
9. Restart/reload the application after verified backend readiness. Expect fresh
   login if process-local session state is lost; do not migrate credentials manually.
10. Run Admin live smoke tests with a clearly isolated Draft record: Create, Edit,
    Publish if appropriate, Draft, Archive, Restore-to-Draft, then Archive the test
    artifact. Confirm exactly appropriate persisted audit records and no secrets.
11. Run User live regression checks on the same catalog: Explore, Details, Map,
    Planner/recommendations/preview, saved trips, weather proposal, AI explanation/
    adjustment, Alerts, Profile/Settings and Login. Confirm Local/NULL/Common ranking,
    geographic ordering and unpublished exclusion; avoid real-record alterations.
12. Rerun the corrected full offline suite and inspect final Git/data/whitespace
    evidence. Reconcile any observed live/backend difference before release.
13. Only after a separate decision approving the final reviewed changes, select
    intended source/migrations/tests/docs for staging and commit. Review evidence
    privacy/size; do not indiscriminately stage the entire intentional worktree.
14. Push/deploy application changes only with the user's separate authorization
    and the project's release process. Neither commit nor push is authorized here.

Steps involving SQL, staging, commit, push or deployment above are recommendations
only. None was performed during this review.

## 12. Go / No-Go assessment

**MIGRATION 0012: SAFE — static review, conditional on target verification.**

**MIGRATION 0013: SAFE — static review, conditional on verified 0012 and atomicity/ACL checks.**

**ADMIN DEPLOYMENT: NOT READY.** Both migrations are still unapplied, database
execution/ownership/grants/RLS/atomicity remain unverified, and the current full
suite is red. The planned audited rollout must avoid exposing 0012 writes before
0013 is ready. Existing read-only catalog functions can continue under their
already-working prerequisites; that is not complete management deployment.

**OVERALL: GO WITH REQUIRED FIXES.** There is a supported path forward with no
demonstrated production regression among the nine test issues. Correct the tests
and fixtures in a separate task, obtain migration approval, verify the isolated
backend and live dependencies, then make the release decision. SAFE here is not
unconditional production execution approval. If any required target/negative/
rollback check fails, deployment remains stopped pending investigation.

ROSAGO FINAL REVIEW: READY FOR DEPLOYMENT DECISION
