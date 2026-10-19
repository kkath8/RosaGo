# Admin authorization foundation (review only)

0008 is not applied. Migrations 0001–0007 remain immutable. This phase does
not provision anyone, add destination writes, or change registration/profiles.

`admin_memberships.user_id` references Auth identity; presence grants Admin.
`granted_at` records provisioning time. Authenticated callers can read only
their own row through RLS; nobody receives application membership write grants.
Anonymous callers have no access. The no-argument `rosago_is_admin()` predicate
uses `auth.uid()`, invoker rights, an empty search path, and explicit execution
grants. It reveals only current-caller membership. Do not reference it from the
membership policy itself. Future RLS policies can use it; future elevated RPC
owners must receive explicitly reviewed privileges and independently authorize
the caller. This migration grants no such write authority.

Flask uses the existing request-owned authenticated client and requires a
literal boolean RPC response. Each Admin request checks membership anew; no
role is stored in cookies or sessions. Errors deny access with a fixed 503.
Until Phase 7A-2, unauthenticated access redirects to `/login`; after login,
visit `/admin`. There is no separate Admin session or login implementation.
All `/admin` responses, including errors, are private/no-store. The placeholder
renders with `g.auth` removed. No `g.admin` is introduced.

## First Admin: future operator procedure

1. Review and separately authorize deployment of 0008; verify grants, ownership,
   schema exposure and RLS in an isolated PostgreSQL/Supabase environment first.
2. Register a normal account and verify its email. Signup creates no membership.
3. A trusted operator verifies the exact account UUID through Supabase Auth's
   trusted management interface. Do not authorize by an application email check.
4. Through the trusted database operator connection, insert only that verified
   UUID into `public.admin_memberships(user_id)`. Do not use Flask, a public
   endpoint, application credentials, or a startup seed for provisioning.
5. Verify `/admin` access and denial for an unrelated normal account. Record
   the operator/change approval outside the application.

Revoke through a controlled operator deletion of that membership. Subsequent
checks fail without waiting for JWT refresh; already-running authorized requests
are not retroactively cancelled. Public registration/profile edits cannot grant
or revoke membership. No runtime service-role key or broad Auth-table access is
needed. Auth-user deletion cascades membership deletion.

## Limits and deployment checks

Static migration tests do not execute SQL or prove live RLS. Before deployment,
test own/foreign reads, anonymous denial, all membership writes, predicate calls,
and revocation using actual application database roles/JWT subjects. Do not
mistake postgres-owner access for RLS validation. Missing migration fails closed.
The existing auth store is process-local; shared-worker deployment needs a
shared store preserving refresh coordination and revocation. Existing login and
logout CSRF/Origin hardening belongs to the shared-auth work in Phase 7A-2.
