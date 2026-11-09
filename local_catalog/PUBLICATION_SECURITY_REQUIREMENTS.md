# Provider authority and publication prerequisites — 2026-11-08

Status: unresolved. No authentication, authorization or hosted setting changed.
This source/documentation review does not certify live provider behavior.

## Established limitation

Supabase documents that sign-out revokes refresh capability but access JWTs
remain valid until expiry: [Python sign-out documentation](https://supabase.com/docs/reference/python/auth-signout).
Its [session documentation](https://supabase.com/docs/guides/auth/sessions)
describes checking JWT `session_id` against `auth.sessions` after sign-out.

The local evaluation helper implements that type of session-row check. **Our
restore threat inference:** if an older valid row is restored while the JWT
remains unexpired, a check whose only authority is that restored database can
accept it again. Shorter JWT lifetimes reduce the window but do not satisfy
the required immediate revocation/restore protection.

The independent web-session ledger prevents reuse of revoked opaque RosaGo
handles when its fencing is intact. It does not itself mediate raw JWT access
to hosted Supabase. The existing inactive gateway resolves the independent
ledger each operation but neither disables the hosted API nor covers Auth
endpoints. Its evaluation-only issuer and missing location-verification RPC
allowlist entry are deliberate activation gaps, not reasons to widen it now.

The production owner schema snapshot lacks even the evaluation provider helper.
The proposed location-verification RPC fails closed for that missing helper.
Therefore its positive synthetic clone test cannot qualify production use.

## Smallest candidate and proof still required

A server-only data path is a candidate because RosaGo already has Flask routes.
It would require closing direct data bypass and qualifying the inactive gateway
for every existing User/Admin service, public catalog read and audited RPC.
Supabase documents [disabling the Data API](https://supabase.com/docs/guides/api/securing-your-api#disable-the-data-api)
for applications that no longer use its data endpoints. **Do not disable it
now:** current RosaGo uses those endpoints and would break. No hosted setting
change is authorized, and feasibility is not end-to-end qualified.

Required proof for this candidate:

- Restricted DB login with no superuser/BYPASSRLS/inheritance; post-fork pools,
  authenticated encrypted transport and server-established claims. Retain
  existing RLS, Admin membership, RPC entry guards and audit semantics. Do not
  replace them with service-role access or accept browser JWTs as DB identities.
- Durable independent revocation/generation authority beyond the restored DB,
  authenticated requests, strict outage failure, restoration fencing and no
  stale-handle or refresh-based automatic re-enrollment. Fence records against
  authority/database rollback in both User/Admin realms.
- Inventory and test all direct paths: REST, GraphQL, privileged RPCs, Realtime,
  Storage mutations and Auth account/recovery/refresh operations as applicable.
  A Data API shutdown alone does not prove those other products are protected.
  Public destination photos can remain intentionally public; they are not a
  private-data revocation guarantee.
- Prove stale JWTs and restored refresh material cannot regain protected access
  or create an accepted RosaGo session after revocation/restore. Establish safe
  recovery/re-authentication after fencing; never recover authority from old
  session rows automatically. Auth-provider-managed endpoints need a separate
  review; a backend gateway does not wrap them by existing.
- Qualify durable logout outcomes, provider denial/outage, request/revocation
  races, cross-worker/restart recovery, trusted proxy HTTPS and secure cookies.
  Real provider acceptance remains separately approved testing, not an offline
  claim.

An alternative retaining direct APIs would need independently durable session
validity enforced on every protected path and privileged function. A revocation
table restored with Auth, a background-synchronized cache with stale success,
or a Flask-only middleware is insufficient. Supabase notes that PostgREST
[pre-request checks](https://supabase.com/docs/guides/api/securing-your-api#pre-request-checks)
do not cover Realtime, Storage or other products. Asynchronous notification of
the authority is not an authoritative per-request check. No such complete
direct-access solution is implemented or approved here.

## Publication versus deployment

Catalog corrections and an inert schema extension can be reviewed locally
while remote deployment is paused. They do not repair provider authority.
The combined mapped-only production rollout specifically depends on the
authenticated verification RPC and a qualified mutation path, so it remains
blocked, independently of coordinate/content approvals. Any smaller schema-only
application would need its own exact scope, compatibility proof and separate
approval; do not treat it as approval for publication or weaker security.

Seven synthetic coordinator admission and seven MockTransport provider tests
passed in this stage. They establish strict booleans, bounded transport,
redirect/error handling, scoped logout and no retry of uncertain logout; they
do not exercise a real Supabase restore, JWT verifier or hosted bypass closure.

Next work is local architecture/acceptance qualification and a separately
reviewable security package. No paid provisioning, hosted configuration or
security SQL application is requested as a shortcut. Remote deployment is NO-GO.
