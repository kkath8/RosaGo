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

## 0002: places catalog — applied in current development database

0002 has been applied and post-execution verified in the current development database.
This status is supplied by the project owner for Phase 5A-2; no new database
inspection was performed in that offline phase. No execution date, production
deployment, or verification of other environments is claimed. Do not rerun 0002.
`0002_places.sql` records the public tourism catalog foundation. Its original
draft header is preserved unchanged as requested; this README records its current status.
`rollback/0002_places.sql` is its separate, destructive development rollback.
Execution in another environment requires separate authorization and review of target objects, default
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

### Offline checks and verification in other environments

`tests/test_places_migration.py` statically checks the exact schema/security
contract and rollback scope without database connections. These checks cannot
prove SQL execution, PostgreSQL constraint semantics, actual ACLs, or RLS
enforcement. Separately authorized verification in another environment must cover text and
Unicode boundaries, malformed slugs, NaN/infinities, coordinate NULL combinations,
published-coordinate requirements, URL baseline checks, and timestamp override.
It must also verify published-only reads by both reader roles (including direct
draft/archived lookups), denial of every application write, function privileges,
and atomic rollback failure when unexpected dependencies exist.

## 0003: private trips — offline draft, not executed

`0003_trips.sql` is unexecuted. Phase 5A-2 only prepares SQL and static tests;
neither the migration nor its rollback has been run against any database.
Execution order is `0001_profiles.sql` -> `0002_places.sql` -> `0003_trips.sql`.
The first two are already applied in the current development database; verify
their actual target objects rather than rerunning them. There are no application
routes, TripService, UI, seeds, Admin changes, or integrations in this migration.

### Tables, ownership and lifecycle

- `trips`: generated UUID `id`; `user_id` defaults to `auth.uid()` and references
  `auth.users(id) ON DELETE CASCADE`; required `name`; optional `visit_date`;
  required `created_at` and `updated_at` default to `now()`.
- Name CHECKs require 1–100 characters and already-trimmed/nonblank text, using
  the existing POSIX-whitespace convention. They reject rather than normalize.
  Future Flask normalization must account for Python/SQL Unicode differences.
  Duplicate trip names are allowed. Dates allow NULL and past dates, but only
  0001-01-01 through 9999-12-31 (excluding infinities and BC/out-of-range dates).
- `trip_places`: only `trip_id`, `place_id`, positive integer `position`, and
  database-generated `created_at`. Composite PK `(trip_id, place_id)` disallows
  duplicate destinations. `(trip_id, position)` is unique, deferrable, initially
  immediate. Gaps are valid; sort by position. No copied catalog content.
- User deletion cascades through trips to memberships. Trip deletion cascades
  to memberships. The Places FK uses `ON DELETE RESTRICT`: archive referenced
  places rather than deleting them. A hard deletion requires separately reviewed
  removal of referencing memberships; this migration does not automate that.
- Archived/draft destinations retain membership and can be removed/reordered.
  Existing Places RLS still hides their details. Future reads must preserve
  memberships using a left join or separate merge, showing “Place unavailable”.
  Published destinations show current information, not historical snapshots.
- Indexes support `(user_id, created_at, id)` listing and `place_id` FK checks.
  The membership PK and position uniqueness supply the other required indexes.
- An invoker BEFORE UPDATE trigger sets `trips.updated_at` to transaction time
  on metadata updates, including no-op updates. Membership changes do not touch
  it. It is not a version counter or a catalog-verification timestamp.

### RLS and explicit privileges

Both tables enable RLS. Only authenticated users have policies. Trips SELECT,
INSERT, UPDATE (old and new row), and DELETE enforce the authenticated UUID.
Membership policies use EXISTS against the caller-owned parent. INSERT also
requires an existing published Places row; UPDATE/DELETE do not check publication.
The same protections apply to direct table API calls, not just the RPCs.

All table privileges are first revoked from PUBLIC, anon, authenticated, and
service_role. Authenticated users get SELECT/DELETE on both tables; trip INSERT
and UPDATE only on `(name, visit_date)`; membership INSERT only on
`(trip_id, place_id, position)` and UPDATE only on `position`. Generated UUID,
ownership, timestamps, and existing membership keys cannot be client-written.
Do not add broad grants that override these column restrictions. No anonymous
access, service-role application access, or changes to existing Places policies.
Existing authenticated schema USAGE and `auth.uid()` availability are prerequisites.
Trusted owners remain privileged; these policies do not constrain postgres.

All five new functions are SECURITY INVOKER with an empty search_path and
qualified relation references. No elevated function is introduced. Trigger-only
functions have all direct EXECUTE privileges revoked from the four roles.
Only the three named RPC signatures grant EXECUTE to authenticated, after
revoking default PUBLIC and other role grants in the same transaction.

### Atomic membership operations and direct writes

| RPC (all return void) | Contract |
| --- | --- |
| `rosago_trip_add_place(uuid, uuid)` | Lock own trip; reject unavailable/duplicate place; append at max(position)+1; reject integer exhaustion. |
| `rosago_trip_remove_place(uuid, uuid)` | Lock own trip; reject NULL place ID; delete membership if present; preserve gaps and allow unavailable destinations. |
| `rosago_trip_reorder_places(uuid, uuid[])` | Lock own trip; require exact duplicate-free membership permutation; assign positions 1..N in supplied order. |

Each call runs in the caller's transaction (one PostgREST RPC request), without
internal commit or multi-request pseudo-transactions. Each locks the parent trip
FOR UPDATE with an explicit `auth.uid()` ownership predicate before reading any
membership. RPCs require READ COMMITTED isolation and reject other isolation
levels before accessing rows: each subsequent statement must see membership
committed while waiting for the parent lock, rather than a fixed older snapshot.
Verify the target API's effective isolation before use. Missing/other-user trips
use the same fixed failure. Null, duplicate,
multidimensional, omitted and foreign reorder entries fail before mutation;
an empty array is accepted only for an empty trip. Array lower bounds do not
affect order because WITH ORDINALITY is used. Reorder defers only the named
position constraint, then restores it to IMMEDIATE to validate before returning.
The intended caller issues one operation per request; the function does not
preserve an outer caller's earlier deferral of that constraint.

Direct table privileges remain as approved. An invoker BEFORE ROW trigger on
every membership INSERT/UPDATE/DELETE acquires the same parent FOR UPDATE lock
before changing the row; it also rejects membership identity changes. It relies
on parent and membership RLS, and uses no published-place check, preserving
archived membership edits. During parent/user cascade deletion the parent row
has already been deleted and its lock is held by that transaction, so DELETE
allows the missing parent. INSERT/UPDATE require a visible, lockable parent.
Normal direct DELETE still needs own-parent membership RLS; this cascade case
does not grant access to other users' rows. Verify both cascades under real roles.

The trigger serializes actual membership changes, but cannot make a client's
earlier SELECT or precomputed position part of a transaction. RPCs are the
supported read/modify/write interface. Direct writes retain positive/unique
position constraints and may fail on stale choices. PostgreSQL can acquire a
child row lock before the row trigger runs, so direct UPDATE/DELETE or multi-trip
batches can deadlock with parent-first RPCs. A deadlock aborts a transaction,
never a partial reorder; do not catch and continue database errors. No guarantee
of deadlock-free direct batches is made. Application code must not automatically
retry uncertain mutations. After failure, reload and let the user choose again.

Concurrent complete reorders are serialized, with last successful order winning;
no optimistic version field is introduced. Addition checks current publication
under normal database visibility, not a promise that the place stays published
through commit or afterward. Concurrent archival can yield an unavailable entry.
The foreign key still prevents dangling references.

Explicit exceptions contain fixed messages and no row IDs/provider data. Native
constraint/deadlock errors may still contain database diagnostics; the future
TripService must translate them to fixed public errors without returning raw
SDK exceptions, auth objects, or tokens. SQL cannot replace that service boundary.

### Application, rollback and verification plan

Apply manually once, in one transaction, only after separate authorization and
pre-execution verification of the target, prerequisite FKs/policies/ACLs, UUID
function, roles/schema privileges and absence of all new object names. No
IF NOT EXISTS/CREATE OR REPLACE or startup runner is provided. Unexpected objects
must stop deployment for review. Perform post-execution verification before
claiming 0003 applied; static tests do not establish SQL runtime validity.

`rollback/0003_trips.sql` removes the three RPCs, two triggers/helper functions,
eight policies and both trip tables (and their owned constraints/indexes), in
one transaction. It permanently deletes trip data. It does not remove Places,
Profiles or Auth objects, use blanket CASCADE, or ignore unexpected dependencies.
Export/review before separately authorized use. Roll back dependent trips before
attempting an older Places rollback; never remove dependencies silently.

`tests/test_trips_migration.py` checks SQL text, exact schemas, policy and ACL
contracts, RPC locking/permutation structure, rollback scope, and this status
documentation. Also run existing Places static migration checks. No SQL is
executed, no network is used, and no application regression is needed here.

Before live application, separately authorized disposable PostgreSQL/Supabase
verification must cover real roles/JWT subjects (two users, anon, missing subject),
all generated-column write denials, direct table and RPC ownership/publication,
date/name boundaries, duplicate/position constraints, metadata timestamps,
archived removal/reorder, both cascades and restricted place deletion. Include
simultaneous append/remove/reorder/direct updates, deadlock/serialization aborts,
parent deletion races, empty/NULL/multidimensional arrays, permutation rollback,
READ COMMITTED wait visibility, rejection of other isolation levels, and
immediate/deferred constraint checks. Inspect actual function ACLs and
search_path; verify trigger-only functions cannot be invoked as RPCs. Test
unexpected dependency failures and rollback atomicity in a disposable environment.
