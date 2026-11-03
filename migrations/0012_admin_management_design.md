# Admin management deployment review

Both SQL files are **unapplied**. The application does not run them at startup.

`0012_admin_management.sql` is the smallest new authorization capability needed
for destination writes and cross-user operational projections. It creates two
functions, with no new destination tables/columns or direct table write grants.
`0013_admin_destination_audit.sql` adds the optional durable audit store and wraps
the mutation function in the same transaction. Review and approve both together
if all destination mutations must be logged from initial deployment.

## Preconditions to verify without rerunning old SQL

- Trusted executor/function owner is the Supabase migration role (`postgres`).
- Existing `profiles`, `places`, `trips`, `trip_places`, `admin_memberships` and
  `rosago_is_admin()` match the current repository contracts.
- Tourism columns from 0011 already exist. Do not rerun 0010, 0011 or the Tourism
  transition/import scripts. Enable `ROSAGO_TOURISM_METADATA_ENABLED=true` only
  when the existing columns are confirmed deployed.
- Verify the deployed category constraint includes the existing `industrial`
  category. Preserve the target database's publication/coordinate constraints;
  these new migrations do not weaken them.
- Review function ownership, privileges and Supabase API exposure in the actual
  project. No service-role key is required or introduced into Flask.

## Authorization and transaction boundaries

Both functions use `SECURITY DEFINER` and an empty search path. All relations and
non-keyword functions are schema-qualified. They lock the caller's membership
row using `auth.uid()` and `FOR SHARE`, preventing concurrent revocation from
passing unnoticed during the mutation/projection transaction. PUBLIC, anon and
service_role execution privileges are revoked; only authenticated callers receive
EXECUTE, and every invocation independently checks membership.

Destination writes lock the existing row, compare `updated_at`, validate the
exact payload allowlist and enforce explicit transitions. The immutable slug is
resolved to the existing row UUID; updates target that UUID. No identity, image,
source, source-row, actor or status field is accepted in an edit payload. The
database's existing constraints/triggers remain in force. A new UUID-derived slug
is generated for new drafts. There are no retries or hard deletes.

The operational function returns only the bounded user directory allowlist and
saved-trip aggregates. It introduces no cross-user SELECT policies on profiles,
Auth tables, trips or memberships. Search is literal `strpos`, with no dynamic
SQL or wildcard expression interpolation. Users are ordered by creation time and
identifier, with at most 25 per page. Popularity returns at most ten destinations;
category usage contains at most the existing seven categories. No private trip
names, notes, budgets, conversations, auth metadata or credentials are projected.

The audit wrapper revokes access to the renamed inner function. It logs one
actor UUID/action/destination UUID/timestamp record per successful RPC, containing
submitted field names and resulting status only. Logging failure rolls back the
destination mutation. Actor UUIDs are retained without an Auth foreign key so
account removal cannot erase historical attribution. Audit read RLS requires fresh
Admin membership; application clients receive no direct audit write grants.

## Required operator verification after approval

Use a disposable database or an explicitly isolated Draft test destination first.
Test anonymous and nonmember direct RPC rejection, member revocation, all field
and enum constraints, incomplete coordinates, stale edits, each valid/invalid
publication transition, and rollback when an audit insert fails. Verify audit
inner-function denial, audit read isolation, safe directory projection and literal
search, exact trip aggregates, and published-only public RLS after each transition.
Confirm Supabase/PostgREST return the scalar JSON objects expected by Flask.

The repository's tests exercise the actual HTTP client/parser/auth/routes against
isolated transports, plus static SQL contracts. They do **not** establish live
PostgreSQL syntax, RLS, ownership, grant or deployment correctness. No SQL has
been executed for this implementation. Do not mark live writes verified until
these operator checks pass. Audit UI is deliberately omitted while persistence
deployment remains unverified.
