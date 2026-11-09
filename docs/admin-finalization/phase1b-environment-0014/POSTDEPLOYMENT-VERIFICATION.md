# Migration 0014 — final post-deployment verification

**PASS. GO for enabling the Environment feature flag after user approval.** All 15 verification gates pass. No unexplained change, unresolved REVIEW finding or deployment blocker was identified. This review did not enable the flag or execute SQL.

## Export provenance and comparison

The operator reports migration 0014 executed successfully in production. This review compares the complete local exports, accepting their production attribution from the operator:

| Export | File in `C:\Users\USER\Downloads` | Rows | SHA-256 |
| --- | --- | ---: | --- |
| Approved pre-deployment | `Supabase Snippet Untitled query (4).csv` | 191 | `b5bd26e3085fd380072f415fdc625ceba118285b4dd8c0108f27fcd8ca97236a` |
| Post-deployment | `Supabase Snippet Untitled query (5).csv` | 193 | `35e34eef326c5d684a714f2217fa9da028c1bbeb0e64d2ed7149e1b363eaf318` |

Pre-export SHA-256 matches the saved approved review evidence. Post-export observation is **5 November 2026, 10:40:13.901144 Asia/Manila**, compared with 10:06:24.563297 before deployment. Both report PostgreSQL 17.11, current/session user postgres and transaction_read_only on. No duplicate section/subject pairs or explicit FAIL statuses appear.

All 191 preexisting result rows were matched by section and subject, with no removed rows. Exactly 186 are entirely unchanged as parsed CSV/JSON values. The five expected changed rows are the observation timestamp, the inner-function definition in three report sections, and the Environment gate transitioning from absent to present. The only two added rows describe `places.environment` and `places_environment_check`. There is no unexpected field-level difference.

## Deployment gates

| Gate | Result | Supporting evidence |
| --- | --- | --- |
| Export integrity | **PASS** | Complete 193-row export; original approved 191-row export unchanged; no duplicate result identities or explicit FAIL. |
| Destination preservation | **PASS** | Same 49 UUIDs; all 49 per-row legacy-field fingerprints exactly match; aggregate independently recomputed from UUID-ordered row hashes. |
| Publication preservation | **PASS** | 34 published, 2 draft, 13 archived; each status count and full-row digest exactly matches. |
| Image URL preservation | **PASS** | All 49 stored image_url values remain NULL; included in the matching complete legacy-row fingerprints. |
| Audit preservation | **PASS** | Same four audit rows by count and complete-row digest; no migration-created audit event. |
| Storage preservation | **PASS** | Same two Storage object metadata records by count/digest; complete destination-images bucket metadata identical. Object bytes were not independently downloaded or hashed. |
| Environment column | **PASS** | Nullable text, no default, no identity/generation, no column-specific ACL; expected ordinal 20 and exact approved comment; all 49 existing values NULL. |
| Environment CHECK | **PASS** | Validated, nondeferrable CHECK permits exactly Indoor, Outdoor and Mix of Both for non-NULL values. SQL NULL remains allowed. |
| Updated inner function | **PASS** | Independently extracted normalized body exactly matches reviewed 0014; expected new MD5; stable OID, owner, ACL and security/call properties. |
| Audit wrapper | **PASS** | Complete definition and normalized hash unchanged; OID, owner, grants, settings and full exported function catalog metadata unchanged. |
| Privileges and role switching | **PASS** | All 62 role-access rows, explicit EXECUTE ACLs and eight effective table-privilege rows unchanged from approved baseline. No application access to inner. |
| RLS and policies | **PASS** | All three table-security rows and four policy definitions unchanged. No new write policy, direct table write access or RLS weakening. |
| Existing constraints, indexes and triggers | **PASS** | All 23 existing constraints, four indexes, seven row triggers and six DDL event-trigger definitions unchanged. Only the approved new CHECK added. |
| REVIEW findings | **PASS** | All 84 previously accepted REVIEW rows unchanged; two new schema REVIEW rows independently assessed. All 86 resolved, none blocking. |
| Scope of deployment changes | **PASS** | Exactly two expected schema additions and five expected changed result rows; no removed rows, unrelated metadata change or data checkpoint drift. |

## Exact preservation checkpoints

| Checkpoint | Count | Pre- and post-deployment digest, identical |
| --- | ---: | --- |
| All destination legacy fields | 49 | `e2f5f0f0c95838888a523ea3c4d90925` |
| Published destinations | 34 | `d7ad131aba0fbd1a447edcf8846923f4` |
| Draft destinations | 2 | `e40280bd8d7556ccf75c6a82d4d2fb63` |
| Archived destinations | 13 | `ee8659239ba65b0bc1ac915fd460c013` |
| Audit records | 4 | `66d7db8ac1c0bb1cb30aa7a2cdad9bd3` |
| Storage object metadata | 2 | `42c16456f900236a75908be23ee2f9bd` |

Destination fingerprints exclude only the newly added Environment key. They cover all other saved fields, including UUID, slug, name, description, category, address, coordinates, image_url, status, timestamps and Tourism/provenance fields. Every individual UUID/fingerprint pair matches, in addition to the aggregate and publication-group digests. This establishes preservation of the 49 original rows within the exported logical-data scope.

The bucket remains public, with a 5,242,880-byte limit, JPEG/PNG/WebP MIME types and all other exported settings/timestamps unchanged. Two Storage objects do not mean two destination photo associations: both exports show zero non-NULL places.image_url values. No object deletion or cleanup is warranted by these results.

## New schema and function verification

`places.environment` is text with `not_null=false`, `default=null`, empty identity/generated settings and no column ACL. Its comment exactly matches migration 0014. All 49 preexisting destinations report NULL Environment.

The exported constraint is exactly:

```sql
CHECK (environment = ANY (ARRAY['Indoor'::text, 'Outdoor'::text, 'Mix of Both'::text]))
```

This is the catalog-deparsed equivalent of the reviewed IN expression; no extra allowed string or alternate OR condition exists. A nullable column plus this CHECK intentionally accepts SQL NULL. The constraint is validated.

| Function | OID, unchanged | Verified normalized prosrc MD5 |
| --- | --- | --- |
| `rosago_admin_mutate_destination_unlogged(text,text,timestamptz,jsonb)` | 18221 | `399faf695b6a607f33bf1fb7c2dd9386` |
| `rosago_admin_mutate_destination(text,text,timestamptz,jsonb)` | 18271 | `4cab3fdc6baf75133fd19b8f1dde6345` |

The exported definitions were parsed offline, their bodies extracted and CR-normalized, and compared character for character with migration 0014 and the reviewed 0013 wrapper respectively. The recomputed MD5 values match the export. All three definition copies in the export agree. The wrapper's entire pre/post result rows are identical.

Both functions retain owner postgres, exact four named input arguments, scalar JSONB return, PL/pgSQL, SECURITY DEFINER, only empty search_path, VOLATILE, non-STRICT, PARALLEL UNSAFE and non-leakproof. No defaults/variadic/support/transform changes; cost 100 and rows 0 unchanged. Complete exported pg_proc catalog metadata, including OIDs and ACLs, matches pre-deployment.

Inner EXECUTE remains postgres-only. Wrapper EXECUTE remains postgres plus authenticated, without grant options. PUBLIC has neither; anon and service_role cannot call either. Authenticated cannot reach inner directly, by inheritance or by SET ROLE. The wrapper and inner continue enforcing the audited mutation contract, and the exact 0014 body retains the photo validation/omission/null behavior reviewed before deployment.

## Remaining REVIEW statuses

The 84 original REVIEW rows are exactly unchanged, so their previously approved assessments remain applicable. This includes authenticator assuming authenticated, the managed CLI administrative role assuming postgres, expected postgres ownership/BYPASSRLS, SELECT-only RLS policies, existing validation/FK constraints, table privileges and all six DDL event triggers. The expected schema watcher only requests PostgREST cache reload; no new trigger or side effect appears. The intentional absence of the historical published-coordinate requirement remains consistent with the deployed publication transition.

The only two new REVIEW rows are the nullable Environment column and the exact validated CHECK. Both pass the explicit checks above. There are **86 REVIEW rows, zero unresolved findings**. No policy or grant correction is needed to clear a generic REVIEW label.

## Final recommendation and limits

**GO for enabling Environment after user approval.** The database deployment gates are satisfied against the saved production baseline. No rollback or corrective database change is indicated.

Verification is based on the two supplied SQL Editor snapshots and unchanged reviewed source files. No runtime mutation/authorization probe or hosting configuration inspection was performed. Storage evidence establishes identical database metadata, not an independent image-byte integrity measurement. These limits do not introduce a migration-specific blocker given the unchanged checkpoints and exact deployed function/schema match.

Machine-readable evidence is in [postdeployment-verification-evidence.json](postdeployment-verification-evidence.json); all 193 row dispositions are in [postdeployment-row-review.csv](postdeployment-row-review.csv). Prior source-file SHA-256 values were rechecked and remain unchanged.

No SQL was executed, production record changed, feature flag enabled, or stage/commit/push performed during this review. **Stopped after verification.**
