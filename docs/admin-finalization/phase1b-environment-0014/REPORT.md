# Phase 1B — migration 0014 verification

**Current result:** The operator reports 0014 deployed, and the full post-deployment export now passes all 15 gates. See [final post-deployment verification](POSTDEPLOYMENT-VERIFICATION.md): **GO for enabling Environment after user approval; flag not changed during verification**. The preparation decision below and the [pre-deployment review](PRODUCTION-CSV-REVIEW.md) are historical. The production review also corrected the generic published-coordinate constraint expectation against the deployed publication transition.

Review date: 2026-11-05, Asia/Manila.

**Decision: NOT YET READY for controlled manual deployment.** Offline review passed, but current production schema, functions, permissions and data have not been inspected. Obtain and review the read-only SQL Editor export below before authorizing deployment. This is an evidence blocker, not a finding that production is incompatible.

No production SQL was executed. Migration 0014, application files, existing contracts and feature-flag settings were left unchanged. No staging, commits or pushes occurred.

## Prepared artifacts and execution instructions

- [predeploy_readonly.sql](predeploy_readonly.sql): exact read-only SQL for Supabase SQL Editor; run this now if collecting verification evidence.
- [postdeploy_readonly.sql](postdeploy_readonly.sql): exact read-only SQL for use only after a separately authorized deployment, before enabling Environment or reopening writes.
- [rollback_keep_environment.sql](rollback_keep_environment.sql): prepared, mutating recovery script; do not execute during Phase 1B.
- [local-fingerprints.json](local-fingerprints.json): hashes of the reviewed source files.
- [offline-validation.json](offline-validation.json): local parsing and contract-test results.

Confirm the production project in the Supabase dashboard is `brnkigrrqdrywahvcbvc`, matching the photo URL contract. Use a fresh SQL Editor session with the trusted `postgres` role. Paste the entire pre-deployment script, run it, and export its single result set as JSON, preserving every row and complete function definitions. Do not run selected sections. No password, service key or Auth token is needed in chat.

The script uses `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`, a single SELECT statement, and COMMIT. It reads catalogs, all-status destination fingerprints, audit fingerprints and destination-images Storage metadata. It does not invoke destination functions or read Auth rows or object bytes. Missing prerequisite tables safely cause an error; stop and report it. After any transaction error, issue ROLLBACK in that session before further work.

An initial export can be collected during normal operation. For evidence of preservation across a later deployment, pause destination submissions, uploads and all other catalog/audit/Storage writers, rerun preflight, and maintain that pause through postflight. Also exclude concurrent database function/schema deployments. Different snapshots during ongoing writes cannot establish migration-caused data changes.

## Access and evidence limits

The available tools expose no Supabase SQL/database connector. Neither process configuration nor the local `.env` supplies a direct database connection URL/password or management access token. A Python database driver alone does not provide a connection. Public REST reads cannot establish function bodies, private audit history, all-status totals or effective privileges, so they were not substituted for catalog verification. Historical repository exports are not evidence of the currently deployed state.

The Environment flag is unset in both the current process and local `.env`; application initialization treats an unset value as disabled. The deployed hosting configuration is unavailable and must be checked independently. Nothing enabled the flag.

## Offline findings

| Requirement | Finding | Production evidence still required |
| --- | --- | --- |
| Existing table and column | Migration adds nullable `text`, no default or backfill, and a validated CHECK allowing only `Indoor`, `Outdoor`, `Mix of Both` plus SQL NULL. It rejects a preexisting column or named constraint. | Actual columns, defaults, constraints, dependencies, triggers, indexes, RLS and policies from sections 09–15, 18 and 23. |
| Exact mutation contracts | Both exact `(text,text,timestamptz,jsonb)` identities are resolved with `to_regprocedure`; bodies are guarded by CR-normalized `prosrc` MD5. | Exact signatures, names, scalar JSONB return, PL/pgSQL, postgres owner, SECURITY DEFINER, only empty search_path, default call properties, complete definitions and ACLs from sections 01–08 and 16. Review full catalog backup for auxiliary property drift, including cost/support settings. |
| Audit wrapper | Only the inner function is replaced. Wrapper body is guarded before and after replacement. Local wrapper inserts actor from `auth.uid()`, submitted field names and resulting status; an audit failure rolls back its mutation. | Current wrapper must match the expected hash, ownership, configuration and EXECUTE contract. Audit schema, RLS and read policy must match 0013. |
| Photo compatibility | Removing only the Environment allowlist entry, validation block and optional update yields the exact reviewed photo-function body. Image omission preserves the photo, JSON null clears it, and supplied URLs retain the same project/bucket/path/type restriction. | Photo hash must already be deployed; bucket must exist and be public. Review bucket configuration, Storage policies, grants, photos and object fingerprints. No uploads or runtime mutation probes were performed. |
| Data preservation | Top-level statements contain no destination/audit DML, Storage operation, backfill or function invocation. Existing rows acquire NULL; stored function DML runs only on a later RPC. Old photos, UUIDs, slugs, statuses, timestamps, Tourism metadata and audit rows are not rewritten by this file. | Exact pre/post comparisons of sections 19–22 under the paused-writer window, and event-trigger review. |
| Atomicity | One BEGIN/COMMIT encloses both guards, ALTER TABLE, comment, function replacement and postflight. A failure aborts the transaction. | Run the entire reviewed file in one session only during a separately approved deployment. Do not continue selected statements after an error. |
| Reapplication | A complete second application fails the old-body guard and/or existing-column/constraint guard. Concurrent complete attempts cannot both add the column successfully; the failing transaction aborts. | Confirm the preflight absence gate. This protection does not prevent an operator from selecting and executing only the replacement-function statement. |

`CREATE OR REPLACE FUNCTION` preserves existing function ownership and permissions under [PostgreSQL's documented behavior](https://www.postgresql.org/docs/16/sql-createfunction.html). It can reset auxiliary function properties; this is why baseline configuration and call properties must be reviewed rather than relying solely on the body hash. Enabled DDL event triggers can introduce additional behavior; their definitions are exported for assessment, not invoked by the verification SELECT.

The new CHECK may scan the table and ALTER TABLE takes a strong lock. Nullable/no-default addition avoids a data backfill, but does not guarantee a lock-free deployment. Select a controlled maintenance window; do not mistake local parsing for an executed migration or runtime performance test.

Expected normalized body fingerprints:

| Function | Before 0014 | After 0014 |
| --- | --- | --- |
| `rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)` | `aa4441116ded963faa4e1ee8e3024e4b` | `399faf695b6a607f33bf1fb7c2dd9386` |
| `rosago_admin_mutate_destination(text,text,timestamptz,jsonb)` | `4cab3fdc6baf75133fd19b8f1dde6345` | same |

These hashes cover `md5(replace(prosrc, chr(13), ''))`, including source whitespace. They do not hash `pg_get_functiondef`, ACLs or ownership and are comparison fingerprints, not authorization.

## Deployment blockers and corrections

1. **Required: obtain the current production preflight export.** Any SQL error, missing prerequisite, FAIL status, source drift, unexpected overload or unresolved security REVIEW blocks deployment. Do not update expected hashes merely to bypass drift.
2. Both functions must belong to the approved trusted `postgres` owner. Require scalar JSONB, exact argument names, no defaults, PL/pgSQL, SECURITY DEFINER, only an empty search_path, VOLATILE, non-STRICT, PARALLEL UNSAFE and non-leakproof. Review other catalog properties against the approved definitions; extra settings require a separately reviewed correction.
3. PUBLIC must lack EXECUTE on both functions. `anon` must lack wrapper EXECUTE. `authenticated` must have wrapper EXECUTE and schema USAGE, but lack any direct, inherited or SET ROLE route to the inner function. `service_role`, `authenticator` and custom application roles must not provide an inner-function bypass. The wrapper owner must be able to call the inner function. Review privileged maintenance roles explicitly; an intentional authenticator-to-authenticated route is not itself an inner-function bypass.
4. Confirm required table columns and all baseline constraints, including seven categories, publication statuses, unique slug, coordinate pair/ranges, published coordinates, Tourism checks and audit PK/action/FK constraints. Confirm destination/audit policies and table/column grants against 0002, 0008–0009, 0011–0013 and the deployed photo contract. Baseline schema drift must be understood before deployment; 0014 does not repair it.
5. Confirm enabled event triggers have no unexpected data/security side effects. Retain the exported function definitions and ACLs outside the SQL Editor; obtain the normal deployment backup/recovery checkpoint. Fingerprints are not a recoverable data backup.
6. Confirm Environment remains disabled on every deployed application instance. Do not enable it as part of this phase.

No definite correction to the migration text was identified offline. Its guards are narrower than the full preflight: for example, they do not themselves reject all extra function settings, service-role/custom-role routes, or schema drift. Do not rely on migration execution to perform those broader checks. Run and review this preflight in the same controlled window, with concurrent schema/function changes excluded. If automatic enforcement of every reviewed invariant is required, prepare and review a separate hardening revision before deployment.

## Post-deployment acceptance

This is a future procedure, not authorization to apply 0014. Keep the flag disabled and writers paused. Run and export the entire post-deployment script in a fresh trusted SQL Editor session.

- Require the new inner hash and unchanged wrapper hash. Compare function OIDs, owner, EXECUTE ACLs and call/security configuration with the preflight export. Only the inner source/definition and corresponding catalog source change are expected; wrapper definition and metadata must remain identical.
- Require Environment to be nullable text with no default, identity or generation. Section 11 must show exactly the CHECK equivalent to `environment IN ('Indoor','Outdoor','Mix of Both')`, validated; no additional allowed values or changed legacy constraints. Deparser formatting can differ by PostgreSQL version, so the script exposes the definition for manual semantic review.
- Require `non_null_environment = 0` before any Environment writes. Compare destination counts, aggregate and per-row hashes, photo count, every status-group count/hash, complete audit count/hash, bucket metadata and object count/hash exactly with preflight. The destination hash excludes only `environment`; timestamps and every other saved field are included. Empty tables have stable empty-string digests.
- Require all preexisting column metadata, constraints, indexes, triggers, policies, RLS flags and grants unchanged. Only the new column/comment and named CHECK are expected additions. No publication transitions or audit rows should result from applying the migration itself.
- Resolve every FAIL/REVIEW. Any unexplained mismatch keeps deployment unaccepted and the feature disabled. Catalog checks do not exercise successful or rejected RPC mutations; such tests belong in a separately approved isolated database. No production smoke-test destination or upload is required by these scripts.

## Safe rollback plan

**Before COMMIT or on any migration error:** the transaction is atomic; use ROLLBACK in the same session if still open/aborted. Do not run compensating DML or individual statements from the migration.

**After a successful COMMIT, first response:** keep/return Environment to disabled on every application instance and verify the restart. If the nullable column and function are otherwise sound, leaving them in place with the flag disabled is the least invasive operational recovery. Keep submissions paused until the application/database contract is confirmed.

**If a function rollback is needed after separate authorization:** export current read-only evidence, ensure there is no intervening function/configuration/ACL drift, then run the entire prepared `rollback_keep_environment.sql` in a fresh trusted session. It guards the current 0014 inner and unchanged wrapper hashes, restores the exact photo-capable inner body, and checks both hashes before committing. A timeout or guard failure requires ROLLBACK and investigation; do not bypass it.

This rollback retains the nullable column, its CHECK and all saved Environment values. It changes no rows, wrapper, grants or policies. It never drops the column or uses CASCADE; dependency-removing cleanup would require separate review. Do not use `tools/rollback_admin_destination_photo_contract.sql`, which removes photo capability.

After rollback, use the post-deployment read-only script for an export: its inner-hash check will deliberately FAIL the 0014 expectation, and the actual hash must instead equal `aa4441116ded963faa4e1ee8e3024e4b`. All other expected checks and preservation comparisons must pass, including the retained Environment column and values. Compare against the immediate pre-rollback checkpoint if Environment edits had already occurred; do not expect those legitimate edits/audit entries to match the pre-0014 snapshot. Keep Environment disabled. The retained column intentionally prevents reapplying the original 0014; restoration requires a separately reviewed forward migration.

## Local validation completed

Using the repository `.venv`, all 23 focused tests and 16 subtests passed across `test_destination_environment.py` and `test_admin_photo_sql.py`. PostgreSQL grammar parsing passed for the migration and all prepared SQL; PL/pgSQL parsing passed for migration and rollback bodies. AST inspection confirms each verification file contains only a read-only transaction and SELECT, no DML/SELECT INTO and no destination RPC call. Rollback body equality and source-file SHA-256 preservation checks passed. These checks parse SQL offline; they neither connect to production nor apply migration 0014.

An initial attempt with the system Python could not import `postgrest` and lacked `pglast`; the complete successful validation used the existing repository virtual environment. No dependency installation was needed.

**Stop point:** verification preparation is complete. Deployment readiness remains pending the production SQL Editor evidence and operator review. Do not apply 0014 or enable Environment yet.
