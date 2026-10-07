# RosaGO profile migration draft

Status: offline draft only. No SQL has been executed. No migration framework
is introduced. Do not apply this automatically on application startup.

## Files and execution assumptions

- `0001_profiles.sql`: forward migration, one transaction.
- `rollback/0001_profiles.sql`: separate destructive development rollback.

Before any future execution, review the target schema, existing Auth triggers,
default privileges, and ownership with an authorized operator. Use the trusted
Supabase `postgres` migration role, which must be able to manage `auth.users`
triggers and own the security-definer function. These are deployment privileges,
not credentials to give Flask. Supabase's existing schema USAGE for
`authenticated` is assumed; do not broaden unrelated schema privileges.

The migration deliberately uses CREATE TABLE/FUNCTION/TRIGGER without
IF NOT EXISTS or CREATE OR REPLACE. Unexpected existing objects require review,
not silent reuse or replacement. It is not a rerunnable migration. The backfill
statement is independently idempotent and the trigger skips conflicting IDs.
Failure before COMMIT rolls back this migration's changes. Trigger installation
and backfill may block concurrent Auth writes; review deployment timing later.

## Schema and behavior

| Column | Type | Nullability | Default | Purpose |
| --- | --- | --- | --- | --- |
| id | uuid | NOT NULL, primary key | None | References auth.users(id), ON DELETE CASCADE |
| first_name | text | Nullable | NULL | Given name copied initially from Auth metadata |
| last_name | text | Nullable | NULL | Family name copied initially from Auth metadata |
| created_at | timestamptz | NOT NULL | now() | Profile creation time, including for backfilled users |

The AFTER INSERT Auth trigger copies NEW.id and only first_name/last_name from
NEW.raw_user_meta_data. Leading/trailing whitespace is removed; missing, JSON
null, empty, or whitespace-only names become SQL NULL. Nullable names prevent
absent name metadata from breaking signup. This does not introduce arbitrary
name-format validation. Metadata is untrusted display data, never authorization.

The trigger runs for unconfirmed users too. Profiles do not grant login or
verification status. It inserts into profiles, not auth.users, so it does not
recurse. A real trigger failure can block signup; local database tests must pass
before deployment. Backfill uses the same mapping and preserves existing rows.
Later Auth metadata edits do not resynchronize profiles. Profiles will be the
source of editable application names; email remains authoritative in Auth.

## Security review

- RLS is enabled. SELECT is limited to authenticated callers whose auth.uid()
  equals id. UPDATE checks both the existing and resulting row against that ID.
- No INSERT or DELETE policies or privileges are provided to normal users.
- All table privileges from PUBLIC, anon, authenticated, and service_role are
  revoked before granting authenticated SELECT and UPDATE(first_name, last_name).
  This new table has no preexisting column grants. There is no broad UPDATE grant
  that could override the column restrictions. Users cannot update id/created_at.
- Anonymous callers receive no privileges or policies. An absent Auth identity
  cannot satisfy ownership predicates. RLS also applies to direct API access.
- The function is owned by trusted postgres and uses SECURITY DEFINER only for
  the insertion that ordinary users are forbidden to perform. Its search_path
  is fixed to empty, objects/functions are qualified, and it uses no dynamic SQL.
  EXECUTE is revoked from PUBLIC and all application roles in the same transaction.
  Auth invokes it through the installed trigger; clients cannot use it as an RPC.
- Owners and privileged database operators remain trusted. RLS is not intended
  to constrain postgres. No service-role bypass is used for user profile access.
- Ownership comes from NEW.id, never metadata. No roles/admin flags are created.
  Future Admin authorization can reference the same Auth UUID in separate,
  protected structures without making profile fields authorization inputs.
- The primary key prevents duplicate profiles; ON CONFLICT(id) DO NOTHING
  prevents trigger/backfill conflicts from overwriting names already stored.

## Deferred local database verification plan

Use a disposable local Supabase/PostgreSQL test environment with its Auth schema
and roles. Do not use production accounts, email delivery, or live project APIs.
Mocks alone cannot establish PostgreSQL permission enforcement. Run user-access
tests under authenticated/anon roles with realistic test JWT subject claims;
never run them as postgres/service_role and mistake bypass results for RLS.
Use privileged access only to arrange fixtures and inspect final database state.

| Case | Later verification and expected result |
| --- | --- |
| A | Insert a local Auth fixture after migration; exactly one matching profile exists. |
| B | Supply first/last metadata with surrounding spaces/tabs/newlines; copied names are trimmed. |
| C | Test missing metadata, empty object, JSON nulls, empty and whitespace-only names; signup fixture succeeds and names are NULL. |
| D | Create Auth fixtures before migration; backfill creates their profiles. Edit a profile, repeat only backfill, and verify no overwrite or duplicate. |
| E | User A selects A's profile; one row is returned. |
| F | User A selects B's profile, including an unfiltered query; B's row is absent. |
| G | A updates A's first_name/last_name; succeeds. A updating B changes no rows. |
| H | A attempts to update id, including alongside a name edit; permission denied, entire statement has no effect. |
| I | A attempts to update created_at; permission denied. |
| J | A attempts INSERT/upsert for own or another user's ID; denied. |
| K | A attempts DELETE of own or another profile; denied. |
| L | Anonymous SELECT/UPDATE are denied; also verify authenticated requests without a subject cannot access rows. |
| M | Privileged deletion of a local Auth fixture cascades to its profile only. |

Also inspect actual table/column ACLs, policies, function owner/search_path, and
function EXECUTE grants. Verify an authenticated caller cannot invoke the trigger
function or introduce unexpected tables/functions to redirect its writes. Check
concurrent fixture creation/backfill, transaction rollback on failure, and the
separate development rollback in the disposable environment. After rollback,
Auth users remain and all four kinds of migration objects are gone. Rollback
must stop atomically if unexpected dependencies exist; do not add CASCADE.

## Rollback and integration dependency

Rollback deletes all profile rows permanently, removes the Auth trigger/function,
both policies, and the table, without deleting Auth users or their metadata.
It is for one successfully applied migration and is not idempotent. Later objects
depending on profiles must be reviewed separately. Preserve data before use.

Current Flask login stores only user_id/user_email and does not retain the
Supabase Auth credentials needed for authenticated RLS-backed requests. Resolve
server-side per-user credential/session handling in a separate integration step
before adding profile queries or UI. A signed Flask user_id alone does not set
auth.uid(). Do not use a service-role key to bypass this dependency. Registration,
login, recovery, .env, and Admin behavior are unchanged by this draft.
