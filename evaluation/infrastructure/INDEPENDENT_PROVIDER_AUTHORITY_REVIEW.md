# Independent provider admission — evaluation candidate

Production publication and remote deployment remain **NO-GO**. Nothing here
authorizes hosted SQL, service creation, secrets, sign-ins or deployment.
Neither installed security SQL file has been changed or rerun. Catalog and image
packages are unchanged. The original successful Linux build evidence is retained.

## Root cause and scope

An unexpired, correctly signed access JWT is not cryptographically revoked by
logout. The installed caller-bound helper additionally requires its matching
`auth.sessions` row. Deleting that row denies access; restoring it can make the
same JWT pass again. All nine restrictive policies and seven entry-guarded RPCs
inherit that weakness. Checking only RosaGo browser sessions cannot protect a
request sent directly to Supabase's application-data APIs.

This candidate requires **both** the current Auth row and synchronous independent
admission for the exact evaluation issuer, user and provider session UUID. It
does not replace RLS, Admin membership, ownership, publication rules, CSRF,
JWT verification or encrypted shared-session/recovery fencing.

The local native result is in
`docs/production-readiness/remote-evaluation/independent-provider-local-results.json`.
It distinguishes native PostgreSQL/RLS, real pgsql-http HTTPS and actual workerd
SQLite from synthetic Auth rows/claims, a synthetic Vault view, and simplified
application rows. The seven **captured real RPC definitions** are tested at their
denial entry points; successful business operations are covered by the existing
application regressions, not claimed as full native RPC qualification here.

## Implemented changes

- `authority/provider-ledger.mjs`: admission and permanent revocation tombstones
  in the independent SQLite Durable Object. Unknown, expired and revoked sessions
  cannot obtain data access. A revoked/expired UUID cannot be enrolled again.
  Independent provider deadlines only shorten; restoring `not_after` cannot
  extend them. Refresh cannot renew the eight-hour absolute admission ceiling.
  No JWT, password, refresh token or destination data is stored in this ledger.
- `authority/worker.mjs`: separate enrollment, check and revoke credentials;
  fixed authority object/issuer/incarnation/namespace; fresh nonces and time;
  enrollment is unavailable to database credentials. Operator block remains
  irreversible through this API. Tombstones are never automatically collected;
  bounded capacity exhaustion denies access and needs a reviewed cutover.
- `independent_provider_sessions.py`: explicit post-fork evaluation composition
  for both existing Flask login flows. Only the existing verified password-login
  result can enroll, before the guarded Admin membership query. Refresh delegates
  to the existing verifier without enrollment. Independent revoke precedes the
  single bounded provider logout attempt. No environment activation was added.
- Shared runtime and User/Admin initializers accept this explicit adapter
  factory. Default development behavior and the production startup refusal stay
  in place. Existing bounded HTTPS transport supports exact provider paths.
- `sql/independent_provider_authority.review.sql`: private, forced-RLS config
  containing two Vault secret UUID references; private DEFINER functions with
  empty `search_path`; a strengthened existing public helper; caller-bound raw
  row-presence diagnostic for logout confirmation; synchronous Auth row triggers
  for deletion and expiry constraints. ALWAYS triggers cover replica-mode DML;
  TRUNCATE is denied. Enrollment secrets never belong in PostgreSQL or Vault.
  The SQL contains an unconditional **UNQUALIFIED** gate and cannot be applied
  as supplied. No application/account DML, changes to the nine policies, existing
  seven RPC bodies, old migrations, memberships, destinations or session cache.
- `sql/independent_provider_authority.verify.readonly.sql`: read-only inventory
  of definitions, ACLs, policy/trigger state, record counts and migration history.
  It does not reveal Vault values or session credentials. Its project label is
  an expected target, **not independent proof of database identity**.
- `sql/independent_provider_authority.quarantine.review.sql`: separate gated
  emergency denial candidate. It retains tombstones, private ACLs and triggers;
  it never restores the vulnerable row-only helper.

## Transport and failure behavior

The database calls the authority synchronously without positive caching. A
missing configuration, unknown session, failed TLS, redirect, timeout, stale
nonce, malformed response, duplicate result header or blocked authority denies
access. There is no asynchronous pg_net grant window or fallback to JWT expiry.
Within-flight transactions/queries cannot be recalled retroactively.

pgsql-http's POST implementation follows redirects. The candidate uses its HEAD
path, which does not enable redirect following, with bounded nonce-bound JSON
headers. Only read/inspect and monotonic deny/shorten operations use HEAD; fresh
admission uses the application's no-redirect POST transport. Requests and responses
are no-store. The native test checks redirects and TLS hostname rejection.
Every database call resets pooled curl options, disables proxies, and sets
300ms connect/1000ms total timeouts. Reset preserves libcurl's secure certificate
and hostname defaults; no superuser-only insecure TLS override is required.
Hosted extension version/behavior, system CA trust and network egress still need
qualification. A response header length check occurs after the C extension has
received it; this is not a pre-allocation memory limit. The endpoint is trusted,
fixed operator configuration. Load, worker limits and outage impact require tests.

Auth trigger network side effects do not roll back with a PostgreSQL transaction:
a rolled-back DELETE may leave a session independently revoked. This deliberately
fails closed; a new password login creates a fresh provider session. Authority
outages block Auth session DML and protected data access. Availability must not
be restored by removing guards. The raw-presence diagnostic is distinct from
admission: independent denial or provider expiry cannot falsely confirm that
the provider row was deleted. Expired/unusable JWT diagnostics return unknown.

## Limits that still block production

1. Managed Supabase **Auth endpoints do not execute application RLS**. The row
   triggers reject ordinary logical resurrection of revoked sessions, but a
   privileged physical restore can bypass triggers. Local results do not prove
   logout/refresh/account mutations against real GoTrue, nor universal denial at
   `/auth/v1/*`. A restored refresh credential must never enroll a session;
   newly issued JWTs for that same revoked SID remain denied by application RLS.
   This does not by itself protect Auth account mutations after privileged replay.
2. A full old-schema restore can remove the helper, restrictive policies or
   triggers themselves. No in-database guard can guarantee its own survival of
   that restore. Recovery requires independently controlled maintenance/quarantine
   **before** restoration, external authority block, inspection of schema/ACL
   fingerprints, reviewed credential/key cutover if needed, and fresh login.
   If all managed Auth API access must survive arbitrary privileged rollback
   without that quarantine, this candidate is insufficient: a provider-supported
   independent enforcement boundary or a revised server-only identity architecture
   is required. Do not claim this risk closed by application RLS alone.
3. The independent authority must not be restored to an earlier OPEN ledger.
   Lost/corrupt/rolled-back authority state requires block and a new explicitly
   bound incarnation; never bootstrap from PostgreSQL or reuse an old object.
   Hosting, operator separation and this recovery discipline are unqualified.
4. Real Vault/pgcrypto ownership/extension execution privileges, permission to add
   ALWAYS triggers to managed `auth.sessions`, GoTrue cleanup/refresh compatibility,
   hosted TLS/latency, direct REST/GraphQL/Storage/Realtime coverage and load are
   not established by local synthetic fixtures. Anonymous public catalog/images
   intentionally remain public; they are not private session-authorized resources.
   The native fixture bootstrap owner is a superuser; it does not establish
   hosted `postgres` permissions. The evaluation MCP OAuth refresh also failed
   during this work, so no hosted compatibility result is claimed.
5. Render TLS/proxy/cookies, per-worker credential construction, cross-worker
   runtime and restart recovery still require the existing staged acceptance
   gates. This work does not qualify or enable production startup.

## Evaluation qualification sequence — separate approvals required

1. Review this package and its SHA-256 manifest. Confirm **evaluation only**
   `jfaufpfzfhysqkhcdsrs` in the dashboard. Run
   `sql/independent_provider_authority.preflight.readonly.sql` and save its complete
   `independent_provider_authority_preflight_json` as
   `evaluation/infrastructure/evaluation-provider-authority-preflight.json`.
   This is the exact next operator action; it enables no extension and changes
   nothing. Then run the read-only verification SQL
   before any approved DDL and save the complete JSON baseline privately. Do not
   repeat production catalog/storage exports. Check availability/version of http
   and Vault and managed Auth trigger permissions; do not enable extensions yet.
2. Resolve the managed Auth/physical-restore policy above with the owner. Approve
   a strictly evaluation-scoped authority service, operator custody, any costs,
   TLS origin, fixed binding, three provider credentials and existing independent
   recovery credentials **before** provisioning. Database may hold only check
   and revoke/shorten credentials. Enrollment stays solely in the verified-login
   backend; operator credentials stay outside both database and web application.
3. Approve exact evaluated SQL hash and separate credential/bootstrap procedure.
   The current UNQUALIFIED gate must not be casually removed in SQL Editor.
   Produce a newly reviewed executable artifact only after all prerequisites
   and exact configuration references are known. Never rerun installed scripts.
   Any required extensions, Vault entries and Auth triggers are additional
   hosted operations, not already approved by this local implementation request.
4. During a planned evaluation maintenance window, initialize the new authority
   once, verify scoped HTTPS endpoints and denial tests, store the two scoped
   secrets through a private supported Vault workflow, and configure their UUID
   references. Never paste secrets into chat, logs, shell history or a checked-in
   SQL file. Applying empty private configuration intentionally denies all guarded
   sessions and Auth DML until the operator completes the approved bootstrap.
5. After owner-operated DDL, stop for read-only verification. Compare all nine
   policies, both ALWAYS triggers, all twelve affected/entry-guard functions and
   ACLs to the locally qualified bodies; compare baseline counts/history and
   account/membership/destination identity to pre-application evidence. Never
   weaken privileges to work around an error. Stop on any mismatch.
6. Obtain separate controlled **evaluation live-auth** approval. Use only the two
   existing synthetic accounts, protected local HTTPS, disposable test data and
   private in-memory tokens. Test User/Admin verified enrollment, membership
   denial for User, published/draft visibility, expiry, current/global logout,
   repeated logout, raw JWT replay through REST and guarded RPCs, token refresh,
   account-update replay, authority outage, and multi-worker/restart recovery.
   Never send bearer credentials to diagnostic logging or browser localStorage.
   Save status codes/booleans, not requests, tokens or cookies.
7. Only with separate explicit approval, an evaluation-only operator restore drill
   can capture and attempt to restore a synthetic session/refresh state. Check
   logical restore rejection, application-data denial even when row triggers are
   deliberately bypassed in a controlled fixture, and the managed Auth endpoints.
   Never disable hosted controls or restore a production database for this drill.
   A managed-provider replica/isolated clone may be necessary to qualify physical
   restore safely. Any unresolved Auth endpoint replay remains a failed gate.
8. After complete evaluation qualification, prepare a distinct production-targeted
   security migration, fresh release review and approvals. This SQL is hard-bound
   to evaluation and must never be applied to production by changing only a URL.
   The existing catalog publication package is still unapproved for execution.

## Failure, rollback and recovery

Before any future hosted application, retain operator baseline definitions/ACLs,
counts/identity evidence and migration history. On error stop; inspect state read
only; never rerun a partially applied transaction blindly. SQL DDL is transactional
but external revocations are intentionally irreversible through database rollback.

Rollback means **quarantine**, not return to row-only authentication: stop test
traffic, independently block the authority object, and, if separately approved,
apply the reviewed evaluation emergency-denial helper. Keep restrictive policies,
triggers, Vault separation and tombstones. Do not restore old Auth/session rows,
delete the independent registry, turn off RLS, reuse credentials/incarnation, or
retry an uncertain provider logout. Reconcile with raw presence and fix forward.
If no durable independent state is trustworthy, invalidate the old binding and
require reviewed new infrastructure/credentials and fresh password sign-ins.

## Reproduce the offline evidence

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe tools\qualify_independent_provider_local.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_independent_provider_sessions.py tests/test_provider_session_check.py tests/test_provider_session_transport.py tests/test_shared_session_runtime.py tests/test_authority_http_transport.py
Push-Location evaluation/infrastructure/authority
node --test --test-isolation=none test/provider-ledger.test.mjs test/provider-worker.test.mjs test/ledger.test.mjs test/worker.test.mjs
Pop-Location
```

The native harness uses only the two cached images named in its source, no image
pulls, network-none containers with shared loopback, and actual local workerd over
a private file relay. All fixture containers/state are removed afterward. It
does not assert a JWT signature or real PostgREST/GoTrue behavior; verified-login
adapters and crypto boundaries have separate offline regression coverage.

Official references: [Supabase sessions](https://supabase.com/docs/guides/auth/sessions),
[Auth hooks and their supported events](https://supabase.com/docs/guides/auth/auth-hooks),
[database HTTP extension](https://supabase.com/docs/guides/database/extensions/http),
[pgsql-http implementation](https://github.com/pramsey/pgsql-http/blob/master/http.c).
There is no documented universal managed Auth request hook in that hook list.
