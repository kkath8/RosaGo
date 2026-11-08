# Migration 0014 — final production CSV review

**GO for controlled manual deployment, after user approval. No migration-specific blocker or required SQL correction was identified.** This supersedes the earlier evidence-pending NO-GO in REPORT.md. Deployment and feature activation have not been performed or authorized by this review.

## Evidence reviewed

Source: `C:\Users\USER\Downloads\Supabase Snippet Untitled query (4).csv`.

- SHA-256: `b5bd26e3085fd380072f415fdc625ceba118285b4dd8c0108f27fcd8ca97236a`.
- 191 data rows, 191 distinct section/subject pairs, no explicit FAIL status.
- All 84 REVIEW rows individually assessed and accepted as nonblocking; no REVIEW was accepted merely because it lacked a FAIL label.
- Snapshot: 5 November 2026, **10:06:24.563297 Asia/Manila**, PostgreSQL 17.11, current/session user `postgres`, read-only transaction on.
- Compared with unchanged migration `migrations/0014_destination_environment.sql`, the deployed photo contract, 0013 audit wrapper, baseline migrations and the previously deployed `data/santa_rosa_places/archive/publish.sql` transition.

The export's production attribution is supplied by the operator; the CSV itself contains the database name `postgres`, not an independently verifiable project identifier. No fresh live connection or SQL execution occurred. The source CSV was read without modification.

Every row has a disposition and rationale in [production-csv-row-review.csv](production-csv-row-review.csv). Extracted checkpoints, source provenance, section totals and independent comparison results are saved in [production-csv-review-evidence.json](production-csv-review-evidence.json).

## Resolution of every REVIEW group

| Finding | Rows | Assessment |
| --- | ---: | --- |
| `REVIEW_UNEXPECTED_WRAPPER_ACCESS` | 1 | `authenticator` has no immediate EXECUTE; it can SET ROLE `authenticated`, exactly the intended PostgREST impersonation route. It cannot reach the inner function. The wrapper delegates to the inner's fresh `auth.uid()` membership check, so authenticated access alone does not confer Admin mutation authority. Accepted. |
| `REVIEW_EXTRA_INNER_ACCESS` | 1 | `cli_login_postgres` has no immediate EXECUTE but can SET ROLE `postgres`. This is the managed CLI administrative boundary, not an ordinary application bypass. No `anon`, `authenticated`, `service_role` or `authenticator` route to the inner exists. Accepted; do not revoke a managed administrative role to make a generic REVIEW disappear. |
| `REVIEW_OWNER_TRUST_REQUIRED` | 2 | Both functions belong to expected `postgres`: non-superuser, BYPASSRLS. That ownership supports the reviewed SECURITY DEFINER admin design. `supabase_admin` has the separately expected superuser capability. Neither is an ordinary application role. Accepted. |
| `REVIEW_COMPARE_BASELINE` — table security | 3 | Places, audit and memberships owned by `postgres`; RLS enabled, FORCE RLS false. Places grants SELECT to anon/authenticated; audit and memberships grant SELECT to authenticated. Owner privileges remain administrative. Accepted. |
| `REVIEW_COMPARE_BASELINE` — columns | 25 | All 19 baseline places columns and all six audit columns match types, nullability, defaults, comments and absence of per-column ACLs. No generated/identity surprises or Environment column. Accepted. |
| `REVIEW_COMPARE_BASELINE` — constraints | 23 | All validated, nondeferrable; definitions match the actual deployed baseline, including incoming trip/audit FKs. Detailed assessment below. Accepted. |
| `REVIEW_COMPARE_BASELINE` — policies | 4 | Published catalog SELECT for anon/authenticated; full catalog SELECT and audit SELECT for authenticated Admins; membership SELECT restricted to own `auth.uid()`. All SELECT-only, permissive, no WITH CHECK or write policies. Accepted. |
| `REVIEW_COMPARE_BASELINE` — row triggers | 7 | Six PostgreSQL FK triggers and the expected BEFORE UPDATE `updated_at := now()` trigger. No unreviewed data-changing row trigger. No top-level DML in 0014 means these row triggers do not rewrite records during deployment. Accepted. |
| `REVIEW_DDL_SIDE_EFFECTS` | 6 | All complete definitions and command tags reviewed individually below. Only the PostgREST schema-reload notification applies to 0014. Accepted. |
| `REVIEW_COMPARE_BASELINE` — indexes | 4 | Places UUID PK and unique slug; audit PK and `(occurred_at DESC,id)` index. Expected definitions, untouched by 0014. Accepted. |
| `REVIEW_COMPARE_BASELINE` — effective privileges | 8 | Across anon/authenticated/authenticator/service_role and places/audit: no effective INSERT, UPDATE, DELETE, TRUNCATE or column INSERT/UPDATE. Only anon/authenticated places SELECT and authenticated audit SELECT. Accepted. |

The additional role-switching information was also reviewed even where the generic checker emitted PASS. `supabase_storage_admin` and `supabase_realtime_admin` can assume authenticated and thereby call the wrapper; neither can call the inner. `cli_login_postgres` can also assume authenticated. These are existing platform/administrative capabilities; the mutation's Admin membership check remains necessary and unchanged. `postgres` and `supabase_admin` retain privileged access by design. No additional custom-role route to the inner was present among all 31 roles examined for both functions.

Supabase identifies `cli_login_postgres` as a temporary CLI administrative role, and documents its postgres membership in [its CLI role guidance](https://supabase.com/kb/troubleshooting/permission-denied-when-deleting-the-cli_login_postgres-role-808bae) and [backup/restore documentation](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore). Treating this role as an ordinary application user would produce the wrong deployment conclusion.

### Constraint baseline correction

The original 0002 schema is not the complete current production baseline. The deployed publication transition explicitly drops `places_published_coordinates_check` and extends categories to include `industrial`. Its absence in this CSV is **expected**, not missing integrity enforcement to repair during 0014. The earlier preparation report's generic instruction to require published coordinates is superseded by this finding. Do not reinstate that constraint or rerun the publication/import script.

The 19 places constraints preserve UUID PK, unique slug, text lengths/trim, slug format, seven categories, three publication states, coordinate pair/ranges/finite values, optional HTTPS image URL and all seven Tourism checks. Published destinations may intentionally lack coordinates under the deployed contract. The audit's three constraints enforce PK, six valid actions and destination FK with ON DELETE RESTRICT. The incoming `trip_places.place_id` FK also retains ON DELETE RESTRICT. All 23 exported definitions are compatible with adding a separate nullable Environment value.

### All six DDL event triggers

| Trigger | Relevant execution and effect |
| --- | --- |
| `issue_graphql_placeholder` | `sql_drop`, only DROP EXTENSION. 0014 and the prepared rollback contain no extension drop. Does not run for their commands. |
| `issue_pg_cron_access` | CREATE EXTENSION only. No extension creation occurs; its grants/default privileges do not run. |
| `issue_pg_graphql_access` | CREATE EXTENSION only. Its GraphQL wrapper/grants changes do not run. |
| `issue_pg_net_access` | CREATE EXTENSION only. Its role/grant/function changes do not run. No network request is made by 0014. |
| `pgrst_ddl_watch` | Applies to ALTER TABLE, COMMENT and CREATE FUNCTION. Definition only issues `NOTIFY pgrst, 'reload schema'`; no data, policy or grant mutation. This is expected API schema-cache maintenance. |
| `pgrst_drop_watch` | Handles dropped objects. No DROP command exists in 0014 or the prepared rollback. No applicable drop action. |

## Exact function and photo-contract verification

Both identities are exactly `(text,text,timestamptz,jsonb)`, named `p_action`, `p_slug`, `p_expected_updated_at`, `p_values`; four input arguments, no defaults, no variadic/mode/transform surprises, scalar JSONB. Both are PL/pgSQL SECURITY DEFINER with only `search_path=""`, VOLATILE, non-STRICT, PARALLEL UNSAFE, non-leakproof. Cost 100, rows 0 and no support function match the reviewed defaults.

The complete exported function definitions were parsed offline. Their bodies were extracted and compared **character for character after CR normalization** with the approved local sources, not merely accepted from the CSV's status or claimed hash.

| Function | Production OID | Verified current normalized body MD5 | Expected after 0014 |
| --- | --- | --- | --- |
| Inner | 18221 | `aa4441116ded963faa4e1ee8e3024e4b` | `399faf695b6a607f33bf1fb7c2dd9386` |
| Audit wrapper | 18271 | `4cab3fdc6baf75133fd19b8f1dde6345` | unchanged |

Only these two expected overloads are exported. Inner EXECUTE ACL is exactly postgres; wrapper EXECUTE ACL is exactly postgres plus authenticated. No PUBLIC EXECUTE or grant options. Authenticated has wrapper schema USAGE but no direct, inherited or SET ROLE access to the inner. Anon and service_role cannot call either function. Wrapper owner can call inner.

The migration changes only the inner. Removing the Environment allowlist addition, validation block and optional update reproduces the deployed photo-capable body exactly. Image omission still preserves the stored URL; JSON null still clears it; supplied URLs retain the same project `brnkigrrqdrywahvcbvc`, bucket, UUID-like path and jpg/png/webp restriction. There is no fetch or upload in the migration.

The public `destination-images` bucket exists with a 5,242,880-byte limit and JPEG/PNG/WebP MIME types, matching `admin_photo_service.py`. No Storage policies appear in the complete policy export. This is compatible with the existing server-only, freshly Admin-authorized uploads using the dedicated Storage secret; 0014 needs no new Storage grant or policy. The export does not test object bytes or the upload service at runtime.

## Preservation of the exact production checkpoint

| Object or state | Before deployment | Expected immediately after 0014, with writers paused |
| --- | --- | --- |
| Destinations | 49 distinct UUIDs and 49 per-row fingerprints | Same UUIDs, counts and every saved legacy field |
| Published | 34 | 34 |
| Draft | 2 | 2 |
| Archived | 13 | 13 |
| Non-NULL `places.image_url` | **0** | **0**; all 49 stored image URLs remain NULL |
| Audit history | 4 rows | Same 4 rows, no migration-created audit event |
| Storage objects in destination-images | 2 | Same 2 metadata records and unchanged object bytes |
| Environment | Column absent | Nullable text column; NULL on all 49 preexisting rows |

Do not describe the two Storage objects as two destination photo associations: the export explicitly records zero non-NULL image URLs. They may have other references; this review does not delete or classify them as disposable.

The 49-row aggregate was independently recomputed from all exported per-row fingerprints in UUID order and matches `e2f5f0f0c95838888a523ea3c4d90925`. This digest covers every legacy field, including timestamps and image_url; only Environment is excluded for pre/post comparability. Other mandatory postflight checkpoints:

- Published: `d7ad131aba0fbd1a447edcf8846923f4`.
- Draft: `e40280bd8d7556ccf75c6a82d4d2fb63`.
- Archived: `ee8659239ba65b0bc1ac915fd460c013`.
- All four audit rows: `66d7db8ac1c0bb1cb30aa7a2cdad9bd3`.
- Both Storage object metadata records: `42c16456f900236a75908be23ee2f9bd`.

Migration 0014 contains no top-level INSERT/UPDATE/DELETE, backfill, mutation-function call or Storage operation. Adding the nullable column does not invoke the stored function body or updated_at row trigger. The applicable DDL watcher only requests a schema reload. Therefore, **the reviewed migration preserves these records, states, URLs and audit history by construction**. Actual preservation after execution must still be established with [postdeploy_readonly.sql](postdeploy_readonly.sql); a pre-deployment CSV cannot certify a deployment that has not occurred.

## Transaction, guards and rollback assessment

- One BEGIN/COMMIT encloses preflight, column/CHECK/comment, the single CREATE OR REPLACE FUNCTION and postflight. Any guard/DDL/postflight error aborts the entire transaction. Use ROLLBACK in the same session after a failure; never continue with selected statements.
- All current preflight conditions are satisfied by this export: exact source hashes, owners, required signatures/SECURITY DEFINER/empty search path, ordinary-role EXECUTE restrictions, no PUBLIC EXECUTE, and neither Environment column nor named CHECK present.
- Postflight checks the new inner hash and unchanged wrapper hash before COMMIT. Owner and grants are retained by CREATE OR REPLACE, with no DROP/recreate, and current auxiliary properties match the replacement defaults. See [PostgreSQL's function replacement semantics](https://www.postgresql.org/docs/17/sql-createfunction.html).
- The whole file cannot be reapplied successfully: after deployment the inner no longer matches the required photo baseline and the new column/CHECK already exist. Do not select only the function replacement or edit the guard hashes to bypass this protection.
- Migration preflight does not lock out concurrent function/security edits between checking and replacement. Exclude concurrent schema/function/grant deployments, pause destination/Storage writers, and use a controlled low-traffic window. The validated CHECK may scan the table and ALTER TABLE needs a strong lock. These are operating conditions, not a defect requiring speculative SQL changes.
- Before successful COMMIT, transaction rollback removes all 0014 effects. After COMMIT, keeping Environment disabled and leaving the nullable schema in place is the least invasive recovery if the schema is sound.
- The prepared [rollback_keep_environment.sql](rollback_keep_environment.sql) guards the current 0014 inner and unchanged wrapper, restores the exact deployed photo-capable inner body, checks hashes and commits atomically. It retains the Environment column, CHECK and any saved values, all destinations/photos/statuses/audit records, owners, grants and policies. Do not use the pre-photo rollback, DROP COLUMN or CASCADE. On timeout/drift, stop and ROLLBACK rather than bypassing checks.
- A retained column intentionally prevents replay of the original 0014 after a function rollback. A later restoration needs a separately reviewed forward migration. Verify rollback against its immediate pre-rollback data checkpoint and expect the inner photo hash, not the 0014 hash.

## Decision and stop point

**GO: migration 0014 is ready for controlled manual deployment after explicit user approval.** All 84 REVIEW findings are resolved as expected platform capabilities, correct deployed baseline metadata or harmless schema-cache maintenance. No actual compatibility/security/preservation blocker and no required migration correction were found.

Before a later approved deployment, keep the reviewed source unchanged, keep Environment disabled on all deployed instances, pause writers/concurrent database deployments, and retain a current recovery checkpoint. If data/security/schema state changed since the CSV, collect a fresh preflight and compare it rather than assuming the snapshot is still current. After execution, run the prepared postflight before reopening writes; feature activation requires its own approval.

This recommendation uses the supplied production snapshot plus offline source review. It does not claim a new runtime RPC/authorization test, hosting flag inspection, image-byte verification, or post-deployment result. Previous successful parsing and focused tests remain applicable because migration and contract source SHA-256 values are unchanged; exported function bodies additionally passed SQL/PL/pgSQL parsing during this review.

No migration, rollback, production query or mutation was executed. No feature flag, application code, migration, grant or policy was changed. No stage, commit or push occurred. **Stopped after review; awaiting approval.**
