# Auth restore/replay investigation — NO-GO remains

Target remains evaluation `jfaufpfzfhysqkhcdsrs`. No hosted project was modified
or queried for account data during this investigation. No live sign-in, cloud
resource, secret/configuration change, deployment, commit or push was performed.
The two installed security files were not rerun and their hashes are unchanged.

## Finding and exact security boundary

**The complete Auth restore/replay vulnerability is not resolved.** The local
regression test reproduces it against a reconstruction of the verified schema:
session exists -> helper true; delete session -> false; restore same row -> true.
A JWT signed with a synthetic test key still verifies before and after deletion
and restoration, until expiry. This is not a live Supabase acceptance test.

The external ledger can prove a RosaGo handle was revoked and prevent a stale
session-store restore. It cannot, by itself, prevent a request sent directly to
the Supabase origin. It also cannot know about provider revocations that were
never reported to it. An unobserved out-of-band revocation followed by restoration
cannot be distinguished from continuous validity using the restored DB alone.
Restoring schema/policies as well as rows can remove an in-database gate entirely.

## Options reviewed

| Option | Assessment |
| --- | --- |
| Shorter JWT lifetime | Reduces exposure window, not immediate revocation or restore safety. No settings changed. |
| Revocation table or epoch in the same DB | Its state can roll back with Auth. Not an independent authority. |
| Existing independent app ledger | Required for cookies/shared-session restoration; insufficient for direct provider endpoints. |
| Async webhook/pg_net revocation mirror | Cannot provide synchronous fail-closed admission. pg_net requests start after commit; delivery/restore gaps remain. |
| Synchronous external check from every RLS and privileged RPC | Could protect covered data operations if authority enrollment, nonce/authentication, outage handling and all revocation events are complete. Adds DB network I/O, secrets and latency; still misses Auth endpoints and can be removed by schema rollback. No managed Auth triggers or HTTP extensions proposed for installation. |
| CORS, custom proxy/domain or database IP restrictions | Does not close the original HTTPS API origin. Database network restrictions do not cover PostgREST/Storage/Auth HTTPS. |
| Rotate a signing key | Rotation alone retains old-token trust. Explicit old-key revocation and cache handling are different operations. Restored refresh tokens can still mint new tokens unless invalidated under a real issuance quarantine. |
| Server-only data gateway + Data API disabled | Viable candidate boundary for application data, preserving SQL RLS. Does not disable or fix Auth APIs, Storage or Realtime. Requires a complete service port and real platform closure tests. Prototype only; not selected/activated for production. |
| Fresh identity trust after a quarantined incident | Stronger recovery candidate: never import sessions, refresh tokens or signing trust into an active provider; old origin must remain unavailable. Requires provider-supported quarantine or separately approved fresh-project recovery. Not qualified or performed. |

Sources: [sessions](https://supabase.com/docs/guides/auth/sessions),
[asynchronous networking](https://supabase.com/docs/guides/database/extensions/pg_net),
[API security and Data API disable](https://supabase.com/docs/guides/api/securing-your-api#disable-the-data-api),
[network restriction limits](https://supabase.com/docs/guides/platform/network-restrictions#limitations),
[key rotation/revocation and caches](https://supabase.com/docs/guides/auth/signing-keys).

## Minimal safe local implementation

`server_data_gateway.py` is an **inactive candidate**, not a new public endpoint.
It accepts an opaque internal server session handle, never browser JWT claims.
Each operation resolves the encrypted record through the independent ledger,
checks expiry/refresh state, sets transaction-local caller identity under the
existing authenticated RLS role, checks the installed provider helper and checks
the independent record again before the data operation. Observed provider denial
terminally revokes the app handle; unknown outcomes never become allow decisions.
Anonymous access is restricted to the existing published Places read path.

The candidate uses a separate non-inheriting SQL login, without superuser or
BYPASSRLS. Existing policies and guarded Admin RPCs remain authoritative. Database
identity comes from the trusted server, so the new private SQL credential is an
impersonation-capable server secret, like an API authenticator credential. It
must never reach browsers, be shared with the session-storage role, or be used
by a generic SQL endpoint. This trust-boundary change needs review before use.

Current prototype supports explicit-column bounded reads, own-profile updates
and an allowlist of existing RPCs. Existing profile and Admin destination services
pass through it locally. It is **not** a full PostgREST replacement: all service
queries, filters, writes and failure contracts must be inventoried/ported before
disabling Data API. Unsupported operations fail; there is no HTTP fallback.
The production startup guard stays closed and no environment switch activates it.

`SQLProviderSessionCheck` provides a narrowly scoped read-only SQL status callback
for encrypted server records/logout receipts when Data API is off. Expired access
credentials yield unknown, not false proof of provider session removal. The logout
journal still claims at most one provider mutation and requires absence evidence.

The provider HTTP adapter now streams responses: it caps status proofs before
buffering, rejects encoded/late proofs, and acknowledges logout from headers
without reading an arbitrary response body. No mutation retries were added.

`evaluation_sql_credentials.py` validates proposed credentials offline: only the
evaluation direct host or a project-bound pooler username; approved dedicated
roles; sslmode=verify-full, system roots, bounded connection settings, no service,
hostaddr, options or privilege overrides. No credentials were generated for hosting
or saved; no remote connection factory or startup activation was added. Actual
hosted TLS/certificate/custom-role behavior is not established by this validator.

## Local evidence

- Restore/gateway lab: **9 tests**, including current SQL vulnerability reproduction,
  synthetic signed-JWT replay, existing profile/Admin services, RLS ownership and
  published/draft visibility, actual adapter logout over MockTransport, durable
  terminal denial, refresh fencing, two separate Python processes/fresh pools and
  authority restart. PostgreSQL 17 and actual local workerd; synthetic accounts only.
- Offline regression: **131 tests and 138 subtests** pass, including credential
  validation and streaming provider-proof failure cases.
- Authority: **3** SQLite/workerd tests pass for CAS, revocation/replay, distinct
  operator permission and durable blocking through restart.
- Linux qualification: see restore-replay-linux-results.json for final counts,
  non-root/dependency/import checks, loopback TLS and production startup refusal.
  No public application listener or published port. Original Linux evidence/images
  are retained; optional gateway dependencies are installed only in a new local
  test image, not in active deployment requirements.

Artifacts: docs/production-readiness/remote-evaluation/restore-replay-local-results.json
and restore-replay-linux-results.json. The local lab reconstructs captured metadata;
it does not execute either installed security SQL file or contact Supabase.

These tests prove the independent gateway continues to deny an app-revoked handle
after Auth-row restoration. They do **not** prove the hosted Data API is disabled,
the hosted Auth API rejects that JWT, or every out-of-band revocation is captured.

## Required changes and approvals — none applied

New `sql/data_gateway.review.sql` creates only a NOLOGIN/non-BYPASSRLS role with
non-inherited SET membership in existing anon/authenticated roles. It does not
alter RLS, create accounts, enable login, change passwords, expose a schema or
disable Data API. It is outside the existing migration runner and has its own
review manifest. Do not run it merely to complete this investigation.

If the gateway alternative is adopted, its complete port and acceptance must
precede a separate approval for (a) that exact role SQL, (b) a private verified-TLS
gateway login/credential procedure, and (c) evaluation-only Data API disable plus
verification of REST/RPC/GraphQL closure and other enabled API surfaces. Existing
one-Render-service + independent-authority + evaluation-PG topology can remain;
no additional paid service is required by the prototype itself.

**Data API disable alone is not a full Auth replay fix.** Before deployment the
owner needs a provider-confirmed recovery procedure which keeps *all* authenticated
API paths and token issuance fenced before/during/after restoration, invalidates
all restored refresh/session state, removes old signing trust, re-verifies guards,
creates fresh authority binding/epochs and only then admits new logins. A bool
environment flag or a Render maintenance page is not evidence of that property.

If this cannot be guaranteed on the hosted provider, do not support in-place Auth
restore. Evaluation must fail closed and remain stopped, with a separately
approved clean trust-domain rebuild and an inaccessible old origin. A normal
Supabase clone is not that rebuild: it copies Auth data and Vault's root key.
Project pausing is unavailable on paid plans; it cannot be assumed to be the
quarantine mechanism. No new project, pause, deletion, clone or rotation is authorized.
[Clone contents](https://supabase.com/docs/guides/platform/clone-project),
[pausing limitations](https://supabase.com/docs/guides/platform/free-project-pausing).

**Exact next approval before any hosted action:** accept a provider-confirmed
Auth-quarantine/recovery design and the chosen data-access boundary. For the
gateway route, a later approval must explicitly name the new role SQL/hash,
private credential operation and Data API change. It must exclude production,
accounts/seeds, spending/deployment and live testing unless separately listed.
No further approval is needed for already authorized local remediation. It is
premature to request deployment approval or to mark the restore blocker resolved.

Actual provider logout/replay, Auth quarantine and cache/refresh invalidation,
full gateway service compatibility, private SQL TLS/credential lifecycle, hosted
authority control isolation and actual Render proxy/cookie/Gunicorn/load tests
remain release gates. No hosted setting should change until that exact operation
is separately approved. Do not rerun either installed SQL file.
