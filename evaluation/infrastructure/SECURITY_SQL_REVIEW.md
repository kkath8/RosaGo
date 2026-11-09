# Final pre-application review — execution not approved

Reviewed 2026-11-07. Evaluation project: `jfaufpfzfhysqkhcdsrs`.
Neither SQL file nor the recorded manifest was changed. Nothing was applied.
All hosted queries used only `supabase-evaluation`: project URL matched,
inspection role was `supabase_read_only_user`, and `transaction_read_only=on`.
Production was not accessed. No passwords, emails, tokens or cookies were retrieved.

## Integrity and hosted baseline

| File | Verified SHA-256 |
| --- | --- |
| `private_sessions.review.sql` | `59899c43c3d3bfe232b9b91e87b979a3fa3338e2dd8ed7d070768fc6b05555ea` |
| `provider_access_guards.review.sql` | `4136cd079ad39201e3fb185c0de8410374a556cb38631f25ac51e81c19983307` |

Both match `manifest.json` and the new local verification/clipboard helper's
independent fixed hashes. Hosted PostgreSQL is 17.11. The proposed role, private
schema, helper function and restrictive policies are all currently absent.
All nine existing public tables have RLS enabled and are owned by postgres.
Existing 17 public policies remain unchanged.

Current data: two Auth accounts, two profiles, one Admin membership, two fictional
destinations (evaluation-garden Published; evaluation-draft Draft), zero provider
sessions, and 15 migrations, versions 20261107000101 through 20261107000115.
Ordinary User 3c572202-c1da-4e5a-aa20-d89be25b2d9f has a profile and no membership.
Admin 4bc67593-c979-4441-b42a-99b6d3da2885 has a profile and the sole membership.

## Private storage file

- Creates database role `rosago_session_app`: NOLOGIN, NOSUPERUSER, NOCREATEDB,
  NOCREATEROLE, NOINHERIT, NOREPLICATION, NOBYPASSRLS. It creates no password,
  enables no login, and grants no membership to either account/API role.
- Creates private schema `rosago_session` owned by postgres, and table
  `rosago_session.payloads`: opaque hashed record key, ciphertext bytea, absolute
  numeric expiry. Constraints validate the session key shape, ciphertext size
  1..45000 bytes and finite positive expiry. A primary-key index and expiry index
  are created. Encryption is an application responsibility; the SQL cannot prove
  arbitrary bytea is encrypted and stores no encryption keys.
- Enables and forces RLS. `session_payload_role` permits DML only for the dedicated
  session role. Only that role receives schema USAGE and table SELECT/INSERT/
  UPDATE/DELETE, without grant option. No schema CREATE, TRUNCATE, application,
  Auth or Storage privileges are added.
- Explicitly revokes schema/table privileges from PUBLIC, anon, authenticated
  and service_role. App Admin membership is an application row, not this SQL role.
  Ordinary Users and Admins therefore gain no direct access to private sessions.
  Trusted postgres/privileged operators remain able to administer/read ciphertext;
  this is not protection against a privileged database owner.
- Creates no functions, triggers, accounts or data rows. It does not expose the
  schema through Data API settings or enable session infrastructure.

**Default privilege limit:** its two per-schema default-privilege revokes cannot
override global grants, including PostgreSQL's built-in PUBLIC function EXECUTE
default. They are not a blanket guarantee for future objects. Explicit current
schema/table revokes establish the present boundary; every future object still
needs its own ACL review. Do not broaden global defaults as an unreviewed fix.
[PostgreSQL 17 documentation](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html).

## Provider access guard file

Creates `public.rosago_provider_session_current()` with no arguments and boolean
output. It is PL/pgSQL SECURITY DEFINER, owned by postgres, with empty search_path
and schema-qualified data references. It returns only a boolean and grants no
direct access to auth.sessions. The hosted postgres owner has the required Auth
schema USAGE and sessions SELECT privilege.

The helper requires non-null auth.uid(), exact evaluation issuer, authenticated
role/audience, matching subject, well-formed session UUID, future JWT exp, and an
existing auth.sessions row belonging to that caller with null/future not_after.
Claims are trusted only after the provider API verifies the JWT; this SQL does
not verify signatures. It is not a complete replacement for provider policy:
ban/account state, inactivity, refresh revocation timing, password-AMR/recovery
restrictions and enabled API surfaces still require real provider qualification.
The helper does not enforce the app's normal-login versus recovery realm rules.
Zero live provider sessions currently
exist, and no synthetic sign-in was performed for this review.

Missing/invalid claims, absent/foreign/expired sessions return false. Database or
claim-processing errors propagate and abort the request; there is no allow fallback.
False denies RLS visibility/writes, and privileged RPC entry raises SQLSTATE 42501.
This is fail-closed against current database evidence, not independent restore proof.

Adds one AS RESTRICTIVE FOR ALL policy, TO authenticated, on each existing table:
admin_destination_audit, admin_memberships, itinerary_drafts, places, profiles,
trip_itinerary, trip_places, trip_stop_plans and trips. Both USING and WITH CHECK
require the helper. These are additional AND conditions; existing ownership,
publication and Admin checks remain. Anonymous Published reads remain public.
Existing authenticated access becomes conditional on a current provider session.
[PostgreSQL policy documentation](https://www.postgresql.org/docs/17/sql-createpolicy.html).

Adds an entry guard to exactly seven existing SECURITY DEFINER functions:

| Function | Hosted original body MD5, matching the script guard |
| --- | --- |
| rosago_admin_mutate_destination | 4cab3fdc6baf75133fd19b8f1dde6345 |
| rosago_admin_operational_overview | 1f4d6573ce99452bdb52b0488c6e9d8b |
| rosago_itinerary_draft_adjust_preview | 48289089d3380eb9805de3c178fca84a |
| rosago_itinerary_draft_create | 5a98abe0ca0962adb15ad34c3da7c74e |
| rosago_itinerary_draft_return_to_editing | d11eec9e49c00e25ee2ad8b790d0e979 |
| rosago_itinerary_draft_store_preview | d59daed134d2bc215985d1100b2749c0 |
| rosago_itinerary_draft_update_preferences | 9194014e756ced5d5b466d2dab0eb02a |

For all seven, hosted language, postgres ownership, SECURITY DEFINER, empty
search_path and ACL match the reviewed baseline. Only postgres/authenticated have
EXECUTE; anon/service_role/PUBLIC do not. Replacement bodies were independently
checked: removing the new entry guard reproduces each exact original body hash.
CREATE OR REPLACE preserves their owners/ACLs. The new helper explicitly revokes
all execution from PUBLIC/anon/authenticated/service_role, then grants only
authenticated EXECUTE (postgres retains owner rights). Unlogged private mutator
and profile trigger remain inaccessible to API roles. Installation DO-block
EXECUTE statements contain fixed reviewed definitions, not user-supplied SQL.
[PostgreSQL function documentation](https://www.postgresql.org/docs/17/sql-createfunction.html).

## Data preservation and restore limits

Installation creates DDL/permissions only. DML within replacement function bodies
is stored, not invoked during installation. No existing accounts/profiles,
memberships, places, itinerary records or migration rows are edited. No Auth,
SMTP, redirect, Storage or JWT setting is changed. The applicable hosted DDL
event trigger only notifies PostgREST to reload its schema. Each file has its own
BEGIN/COMMIT; the two files together are not a single atomic transaction.

SQL Editor does not automatically add rows to Supabase CLI migration history.
The 15 existing entries should stay unchanged, not become 17. Save the hashes and
read-only postflight evidence locally; migration-history reconciliation would be
a separate reviewed action. These scripts are not idempotent: do not rerun or
add IF NOT EXISTS to work around an error.

**Auth restore/rollback remains a security blocker.** Restoring a previously
removed auth.sessions row can make an old, still-unexpired JWT pass the helper
again. Restoring older public schema can also remove the policies/guards. These
guards neither consult the external authority nor automatically detect a restore.
Closing Render alone does not close direct Supabase APIs. Independent API
quarantine, credential invalidation, guard re-verification and controlled reopening
remain unqualified. Already admitted/in-flight operations are not retroactively
undone. Applying this incremental SQL would not qualify deployment/live testing.

## Exact owner-operated procedure — only after separate explicit approval

1. In VS Code PowerShell, from the repository root, verify without connecting:

   ```powershell
   .\evaluation\infrastructure\verify-security-sql.ps1
   ```

   Both PASS hashes must match this review. No SQL was executed by this helper.
   It does not verify the current dashboard tab or connect to a project.

2. Open https://supabase.com/dashboard/project/jfaufpfzfhysqkhcdsrs/sql/new . Check
   that exact reference in the address bar and project settings. Use the primary
   evaluation database and postgres execution role. Do not change any settings.
   The SQL files themselves do not enforce database project identity: their
   comments/evaluation issuer are not a guard against choosing the wrong tab.

3. After explicit approval, copy only the first file's SAME verified bytes:

   ```powershell
   .\evaluation\infrastructure\verify-security-sql.ps1 -Copy private_sessions.review.sql
   ```

   Paste into a fresh SQL Editor query. Confirm the complete content starts with
   the private-storage review header and includes BEGIN through COMMIT, with no
   extra statements. Recheck the project reference and postgres role. With no
   partial text selected, run the entire file once. Expected successful DDL result:
   Success / No rows returned. On any error, warning indicating a different scope,
   target/hash/content mismatch or unexpected output, STOP and report it; do not
   edit/retry/drop anything. Do not override an unexpected approval warning.

4. Stop for read-only supabase-evaluation postflight before the second file:
   role remains NOLOGIN and non-privileged; schema/table/index/constraints exist;
   table RLS+FORCE and exactly the intended policy/grants exist; API roles have no
   private schema/table access and no membership in the new role; table is empty
   if the inspector has access; otherwise verify catalog only, without granting
   the inspector access. Confirm original data and 15 migrations remain unchanged.

5. After that check passes, copy only the second file:

   ```powershell
   .\evaluation\infrastructure\verify-security-sql.ps1 -Copy provider_access_guards.review.sql
   ```

   Use another fresh query, verify the same target/role, complete guard file and
   BEGIN/COMMIT, then run the entire file once. Do not also run the older standalone
   provider_session_rpc.review.sql. Stop on any baseline/hash/permission/error
   mismatch. If this transaction fails after file one committed, file one stays
   installed: do not attempt an automatic rollback or rerun either file.

6. Read-only MCP verifies the helper and seven new function definitions/ACLs/
   search paths, nine restrictive policies plus original 17 policies, private
   role/storage boundary, unchanged account/profile/membership/destination state,
   and unchanged 15 migration rows. Do not sign in, enable the role, set passwords,
   deploy, provision resources or access production as part of this procedure.

**Awaiting explicit owner approval of these exact hashes and evaluation-only
application. No SQL execution is authorized by the present review request.**
