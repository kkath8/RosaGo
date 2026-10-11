# RosaGO migrations

Status: `0001_profiles.sql` was applied manually during Phase 2B to the development
Supabase project and remains the canonical migration record for the profiles
schema. This does not record a production deployment. No migration framework is
introduced. Do not rerun this migration as part of normal application startup.

## Files and execution assumptions

- `0001_profiles.sql`: forward migration, one transaction.
- `rollback/0001_profiles.sql`: separate destructive development rollback.

Before applying to another environment, review the target schema, existing Auth triggers,
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

## Rollback and current authentication integration

Rollback deletes all profile rows permanently, removes the Auth trigger/function,
both policies, and the table, without deleting Auth users or their metadata.
It is for one successfully applied migration and is not idempotent. Later objects
depending on profiles must be reviewed separately. Preserve data before use.

Normal authenticated browser sessions use an opaque `auth_session_id` reference;
Supabase credentials remain server-side in the normal auth session architecture.
Authenticated requests resolve a verified `AuthenticatedContext`, with a
request-owned Supabase client using the verified user's bearer token. Phase 2C-3
reads the user's own profile under this context, with RLS still protecting access.
Legacy `user_id`/`user_email` cookie values are not authentication authority.
Password recovery remains a separate flow.

## 0002: places catalog — offline draft, not executed

`0002_places.sql` prepares the public tourism catalog foundation. It has NOT been
executed against Supabase; no deployment or live RLS verification is claimed.
`rollback/0002_places.sql` is its separate, destructive development rollback.
Execution requires separate authorization and review of target objects, default
grants, PostgreSQL UUID-function availability, and trusted migration-role access.
Neither file runs on application startup; neither is intended to be rerun.

The table contains only public tourism/business information, never user PII.
It has exactly: UUID `id`, `name`, globally unique `slug`, `description`,
`category`, `address`, nullable `latitude`/`longitude`, nullable `image_url`,
`status`, and timezone-aware `created_at`/`updated_at` timestamps.

- Names, descriptions, and addresses must be nonblank and already trimmed,
  with PostgreSQL character-length limits of 150, 3000, and 500 respectively.
  Checks use PostgreSQL POSIX whitespace classification; they reject rather
  than silently normalize. Slugs are 1–120 lowercase ASCII letters/digits with
  single separating hyphens; uniqueness includes draft and archived rows.
- Category is constrained text: `attraction`, `dining`, `shopping`,
  `accommodation`, `nature`, or `heritage`.
- Coordinates are either both NULL or both present. Values must be finite and
  within latitude -90..90 and longitude -180..180. Published records require
  both. Geographic membership in Santa Rosa still requires curation review.
- Status is `draft` (default), `published`, or `archived`. Only published rows
  are readable by `anon` and ordinary `authenticated` users, even by known ID
  or slug. RLS and SELECT-only grants enforce separate layers of this rule.
- All default table grants are revoked from PUBLIC, anon, authenticated, and
  service_role before granting only SELECT to anon/authenticated. There are no
  application write grants, write policies, or Admin policies. Existing schema
  USAGE for those reader roles is assumed; unrelated schema privileges are not
  changed. Trusted database owners remain privileged; no service-role client
  or RLS bypass is introduced into the application.
- A places-specific BEFORE UPDATE trigger overrides supplied `updated_at`
  using `pg_catalog.now()`. It is SECURITY INVOKER with an empty search_path;
  direct function privileges are revoked from application roles and PUBLIC.
  `created_at` defaults to creation time; future authorized writer contracts
  must preserve it. `updated_at` is not a source-verification timestamp.
- An optional image URL must be trimmed, have an HTTPS prefix plus content,
  and be at most 2048 characters. These SQL checks are only a baseline.
  Future curation/application code must parse URLs, approve hosts, reject
  embedded credentials, and review image rights/attribution. No uploads or
  storage are introduced.
- Only the primary-key and global slug-unique indexes are created implicitly.
  No PostGIS, extra indexes, seed records, real places, or sample data are added.

Real content and provenance come later: record source URL/name, actual date
verified, supported facts, coordinate checks, and image rights in versioned
content documentation. Do not invent records or publish without verification.
Admin authorization and content-writing paths require a separate reviewed phase.

Rollback removes only the places trigger, function, policy, and table, in one
transaction. It deletes all catalog rows if later populated. It does not touch
profiles/Auth objects, use CASCADE, or suppress missing-object errors. Unexpected
future dependencies must stop rollback for review rather than be destroyed.

### Offline checks and deferred database verification

`tests/test_places_migration.py` statically checks the exact schema/security
contract and rollback scope without database connections. These checks cannot
prove SQL execution, PostgreSQL constraint semantics, actual ACLs, or RLS
enforcement. Separately authorized database verification must cover text and
Unicode boundaries, malformed slugs, NaN/infinities, coordinate NULL combinations,
published-coordinate requirements, URL baseline checks, and timestamp override.
It must also verify published-only reads by both reader roles (including direct
draft/archived lookups), denial of every application write, function privileges,
and atomic rollback failure when unexpected dependencies exist.
