# Local infrastructure candidate — remote deployment NO-GO

Target: evaluation project `jfaufpfzfhysqkhcdsrs`. Local implementation only is
approved. This package has not accessed or changed either hosted project,
created cloud services, performed real authentication, or deployed anything.
The existing production startup refusal and readiness failure remain in place.

## Implemented components

- `authority/worker.mjs` authenticates distinct application/operator credentials
  and delegates to one operator-selected SQLite Durable Object. Application
  requests cannot initialize, block, reopen, select another object or rotate epochs.
- `authority/ledger.mjs` persists control, bounded multi-record CAS, ciphertext
  digests, expiry, quotas, revocation tombstones and short-lived nonce receipts.
  It checks namespace, realm, epoch, generation, incarnation and server time.
  Missing/uninitialized control denies access. Restart never initializes OPEN.
  Blocking is irreversible for that object through this API.
- `authority_http_transport.py` checks the HTTPS endpoint, validates certificates
  and hostname, authenticates with a scoped bearer token, disables environment
  proxies/redirects/retries, bounds bodies/I/O, and rejects inherited clients
  after fork. ProtectedRevisionAuthority also checks nonce, sequence and binding.
  Plain HTTP/custom ports require explicit Python-only loopback test injection.
- `externally_fenced_postgres.py` uses PostgreSQL as an encrypted ciphertext
  cache. A read must match independent metadata before and after retrieval.
  Authority CAS precedes cache publication; uncertain publication never restores
  an earlier revision or repeats a provider operation. Auth, browser state,
  challenge/rate state and recovery families share this boundary.
- `durable_session_logout.py` atomically denies the selected app/browser handles
  and writes an encrypted receipt, then durably claims at most one provider
  logout attempt. Acknowledgement alone is insufficient: provider absence must
  be observed before reporting completion. An uncertain attempt is never repeated.
  A bounded internal scanner can recover pending receipts without retaining the
  browser cookie and reconcile using read-only provider checks. No background
  service, public reconciliation endpoint or extra application feature was added.
- LocalSessionRuntime can inject these dependencies into the existing User and
  Admin routes. Both routes report unconfirmed provider revocation as HTTP 503
  after clearing local browser authority. Existing local development behavior is
  preserved when the optional durable handler is absent.

## Local evidence and its limits

See `docs/production-readiness/remote-evaluation/external-infrastructure-results.json`
and `infrastructure-linux-results.json` for the latest sanitized results.

| Check | Result / boundary |
| --- | --- |
| Focused offline regression | 127 tests and 127 subtests pass |
| Real loopback TLS | Two tests pass: trusted exact hostname succeeds; untrusted/mismatched certificates fail |
| SQLite + actual local workerd | Three tests pass, including authenticated operator separation, CAS/rollback, replay/tombstones and persistent blocking across restart |
| Cross-component integration | Ten tests against disposable PostgreSQL 17 and actual Worker in a separate local workerd process; synthetic provider only |
| Restart qualification | Two additional database + authority restart checks preserve active state and terminal revocation |
| Linux candidate | 37 tests, dependency check, non-root, private-file exclusion and unconditional production startup refusal pass; network disabled, no ports published |
| Existing Linux evidence | Original `linux-build-results.json` SHA256 remains `b3645b00f1ebe1a724e96ccf8d0f9831ef98cb1e627d27d5249b7d73f10a470d`; earlier images retained |

Integration covers stale/full ciphertext-cache restoration, revoked recovery
grant restoration, single refresh winner and stale completion, publication
failure, independently blocked authority, separate Python processes/pools,
both existing app routes, realm-specific logout, crash/uncertain provider outcomes,
private SQL role denial, and direct SQL replay against all nine public tables
and all seven authenticated SECURITY DEFINER entrypoints.

The integration transport is an authenticated loopback shim into workerd;
certificate/hostname enforcement is tested separately with ephemeral local TLS.
This is not proof of Cloudflare hosted durability, Supabase Auth behavior,
PostgREST/GraphQL behavior or Render TLS/header handling. Test certificates are
not installed into OS trust. No owner passwords, tokens or cookies are used.
Pinned local tooling includes Wrangler 4.158.0, its Miniflare 5.20261104.0-beta
runtime, esbuild 0.28.2 and workerd 1.20261104.1; the beta simulator is not a
hosted-provider acceptance result.

Local reruns from repository root, after installing the existing local dependencies:

```powershell
.\.venv\Scripts\python.exe tools/qualify_external_infrastructure.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_authority_tls_local.py
```

Run `npm test` from `evaluation/infrastructure/authority` after its pinned local
dependencies are installed. These commands use only owned disposable local
services. They are not migration/deployment instructions.

## Review-only hosted package

`manifest.json` pins exact bytes and the evaluation target. None of these SQL
files is in the schema-operator migration directory; nothing auto-applies them.

1. `sql/private_sessions.review.sql`: creates a NOLOGIN, non-superuser,
   non-BYPASSRLS role; unexposed private `rosago_session` schema; encrypted payload
   table, constraints/index, forced RLS and narrowly scoped DML policy/grants.
   No application/Auth/Storage data privileges, Auth accounts or seed rows.
   A future separately approved credential operation is needed to enable a
   dedicated SQL login. Credentials must never be put in SQL files or shell history.
2. `sql/provider_access_guards.review.sql`: installs the caller-bound session
   helper; adds one restrictive policy to each of the nine public tables; adds
   session checks inside all seven authenticated definer RPC entrypoints.
   Each RPC replacement requires its exact original body hash/security attributes.
   Existing ownership, membership and publication checks remain. Private inner
   mutators stay inaccessible. Anonymous Published reads remain intentionally public.
   This supersedes the standalone helper proposal; do not apply both.
3. `authority/wrangler.review.toml`: review-only Worker/SQLite class binding,
   with no account ID, live routes, real object identity, secrets or service creation.
   Hosted routing, credential lifecycle and operator restrictions need later review.
4. `runtime.env.review.example`: existing evaluation settings and proposed
   private runtime inputs. New infrastructure variables have no environment loader
   yet. Do not copy this file into a running service or set proxy attestation early.
   The existing `render.evaluation.yaml` remains a closed candidate for one service;
   Gunicorn uses two post-fork workers and does not independently trust forwarded headers.

The SQL is generated/rehearsed against a reconstruction of all 15 unchanged,
hash-verified evaluation migrations. Changes in baseline table/definer inventory,
function bodies or security attributes stop preparation/application.
Neither file can prove a SQL Editor tab's project identity. Before any future
application, the owner must independently check the exact evaluation reference,
the manifest hashes and read-only evaluation MCP identity. No production access
is part of that procedure.

## Recovery procedure required before hosting

Application credentials never receive authority operator/PITR/account tokens.
The authority's management plane must be outside app credentials and session DB
backups. Close old authority admission and drain old workers before recovery.
Do not restore an authority database in place or reactivate an old deployment.
When freshness is uncertain, use a fresh object/identity/incarnation and distinct
User/Admin epochs, independently provision the binding, and invalidate all old
sessions. The API deliberately has no unblock or in-place restore operation.

This fences session ciphertext DB restores locally. It does **not** solve a
Supabase Auth database restore: old JWTs could regain direct API access if their
`auth.sessions` rows return. The external app ledger is not consulted by hosted
RLS. A provider-supported API quarantine/recovery procedure must prevent access
throughout restoration and invalidate old provider credentials before reopening.
That procedure is not qualified. Do not describe this architecture as safe against
arbitrary simultaneous database/authority restores or administrative rollback.

## Remaining release gates

1. Production composition is intentionally absent. Qualify the real evaluation
   custom SQL role/connection with verified TLS, bounded post-fork pools, key/epoch
   rotation, receipt retention/maintenance and readiness. Do not remove the startup
   guard simply because local tests pass.
2. Qualify independently controlled Cloudflare deployment/binding/secret rotation,
   failure recovery and no-PITR-in-place operating controls. Local SQLite/workerd
   persistence cannot establish the hosted trust boundary.
3. Review/apply the new SQL only under separate evaluation-only approval; verify
   through the unchanged read-only MCP. Then separately authorize live checks of
   provider session removal/not_after, logout acknowledgement/absence and old JWT
   rejection through REST, RPC, enabled GraphQL and relevant other API surfaces.
   JWT cryptographic validity can outlast logout. Already admitted/in-flight
   operations cannot be retroactively undone by a later session check.
4. Resolve Auth restore/direct-API fencing above. Closing Render alone is insufficient.
5. Under later quarantined deployment approval, verify actual Render header
   overwrite, exact origin/Host, HTTPS-only issue/delete cookies, concurrent
   Gunicorn workers, load/memory/connection limits and failure behavior. CAS can
   safely return transient 503; availability/load acceptance is not yet complete.
6. Authority bounds are 4096 live records/32 MiB ciphertext accounting, 8192
   revocation tombstones (up to eight hours), and 8192 five-second mutation receipts.
   These are fail-closed limits, not a measured respondent capacity guarantee.

No simpler equivalent architecture has been qualified. A same-host disk/flag
does not supply independent restore authority; adding Redis or another managed
database adds a service without resolving direct Auth API restoration. Keep one
Render service + existing evaluation PG + one independent authority candidate.

**Next hosted approval, after SQL review:** owner-operated application of exactly
the two manifest-pinned evaluation SQL files. This does not waive the recovery/API gates.
It excludes login credentials, Auth settings/accounts, cloud services, spending,
deployment, live sign-ins and production changes. Those each remain separately
gated. No further approval is needed to continue authorized local remediation.
