# Phase 2M — Isolated PostgreSQL Session Store Implementation

Date: 2026-11-05. Scope: inactive implementation, real loopback PostgreSQL and synthetic authentication tests only.

**GO for the next isolated recovery-authority and neutral-integration qualification phase. NO-GO for activation, production schema changes or deployment.** The transactional adapter works in the tested local configuration. It does not solve independently trustworthy recovery freshness. All eight outstanding production gates remain FAIL. Two deliberately unsafe restore configurations actually restored revoked authority; they are security limitations, not successful security gates.

## 1. Exact changes and activation status

New root files:

- `postgres_session_store.py`: inactive PostgreSQL realm, snapshot, model, challenges and bounded loopback pool factory.
- `postgres_session_recovery.py`: mandatory recovery provider protocol, binding/proof types and fresh-proof validation.
- `requirements-postgres-isolated.txt`: optional local dependencies, psycopg binary 3.3.8 and psycopg_pool 3.3.1. Installed in the existing local virtual environment; tzdata 2026.6 was resolved transitively.

New test files: `tests/postgres_session_fixture.py` and `tests/test_postgres_sessions.py`.

New artifacts in this directory: this report, `local-schema.sql`, `local_lab.py`, `qualify_backend.py`, `browser_fixture.py`, `browser_checks.mjs`, `verify_evidence.py`, JSON results/fingerprints, pytest XML, sanitized output logs, browser startup/PID metadata and six synthetic browser screenshots. `verification-summary.json` inventories flat artifact hashes and the five root/test additions.

No pre-existing application, Redis, LMDB, protected-authority, route, SQL contract or dependency file was changed by this phase. Existing uncommitted work was preserved. The adapter is not imported by the running application and has no environment activation switch or production connection factory. The existing unconditional production startup refusal remains intact and is explicitly tested. No staging, commits, pushes, production requests, SQL, Auth changes, hosting or secret provisioning occurred.

The integration fixture substitutes dependencies only while constructing synthetic Flask test applications, with dotenv loading disabled and Supabase mocked. It uses the existing `redis-local` test assembly point, not a new deployable mode or a safeguard bypass. No Redis/LMDB connection is made by the PostgreSQL backend. Existing generic transition code is still named `RedisModel`; extracting a neutral protocol and explicit PostgreSQL dependency wiring is future work requiring approval.

## 2. Schema and transactional architecture

The operator fixture creates private schema `rosago_session_m` in disposable database `rosago_lab_m`. **The SQL is not a production migration and is never run automatically by the adapter.** PostgreSQL 17.11 is pinned to image:

`postgres@sha256:653186fe15006c099d2fb3bc1d8461c1dee9d036c43f2e5fdaf4f22e5e601876`

Only `127.0.0.1:16432` is published. Random operator/application passwords remain in memory and a temporary container environment file; no connection string or dump is archived. Fixtures verify container identity, phase label and loopback binding before removal. Completed fixtures and their anonymous volumes were removed; the failed browser fixture's owned container and temporary credential directory were also removed. The disposable Chrome profile was deleted. The pinned image remains cached locally.

| Table | Purpose and retention |
| --- | --- |
| `gate` | Operator-only namespace/protocol, authority ID, incarnation, independent User/Admin epochs and OPEN/BLOCKED/QUALIFYING status. Database gate alone cannot establish freshness. |
| `records` | Individually encrypted auth, browser, challenge, recovery, verification and rate state; realm/epoch/family, monotonic revision and explicit expiry. Logical expiry is checked on every read. |
| `versions` | Per-reference revision high-water mark, retained at least to the absolute deadline plus two seconds. Rejects restoring an older payload while this fence remains current. A trigger forbids backwards revision/retention changes through ordinary UPDATE. |
| `revoked` | Terminal reference tombstones, retained 28,802 seconds after revocation. Old snapshots cannot reinstall the reference while its marker is current. |

Runtime uses a dedicated non-superuser role, with table-level state permissions, no gate mutation and no deletion of version or revocation history. A fixed, parameterized SECURITY DEFINER `lock_gate(text)` exposes only a gate read with a shared lock, fully qualified relation names and `search_path=pg_catalog`; PUBLIC execution is revoked. This avoids granting the runtime UPDATE merely to support PostgreSQL's `FOR SHARE` permission requirement. The role is trusted server code, not a per-user RLS security boundary. Hosted schema visibility, inherited roles/default grants, Data API exclusion and owner privileges still need separate review.

Each operation validates fresh recovery proof, starts a bounded transaction, checks/locks the gate, rejects standby/fsync-off or clock drift, then uses current database time. Writes take a transaction-scoped advisory lock per namespace/realm and compare expected snapshots before atomic record/version/tombstone changes. A second proof check occurs after completion. Admission and mutation share the same transaction. There is no partial ciphertext/metadata publication and no positive authority cache.

Creation allocates an unpredictable 256-bit reference; SQL stores only its SHA-256-derived key. Refresh reservation atomically installs one short-lived lease; credential replacement requires the exact lease, subject and provider-session identity and advances generation. Browser rotation atomically invalidates the old parent/reference while creating its successor. Logout installs terminal markers and removes authority atomically. Concurrent stale browser saves or late refresh results fail version checks rather than recreate a revoked session.

If commit succeeds but the post-operation proof is unavailable, the caller receives unavailable/uncertain, not a success or automatic retry. A focused test confirms the credential generation can have committed once and the old lease cannot be replayed. Already dispatched Supabase operations and issued JWTs cannot be recalled by local session revocation; server-side cookie invalidation is not global provider JWT revocation.

## 3. Cookies, isolation, encryption and lifetimes

The existing Flask realm interface is reused only through isolated injection. User cookies use `/`; Admin cookies use `/admin`. The HTTPS header tests preserve Secure, HttpOnly, SameSite=Lax and absence of Domain; cookie parsing rejects duplicates/swapped realms/legacy authority. Actual production ingress/TLS/browser behavior is unqualified. Admin requests use B's realm credentials and fresh mocked database membership checks, while User A remains independently authenticated. The destination mutation contract test checks B's bearer credentials and existing RPC argument contract; no real destination or audit row is written.

AES-256-GCM uses the unchanged bounded codec, random nonce and key ID; AAD binds namespace, new PostgreSQL protocol, realm, epoch, family and reference digest. Sensitive credentials, CSRF/browser values, PKCE material and grants are ciphertext. Expiry/revision and selected lifecycle metadata remain visible to the SQL role. Keys are generated for tests only. Production secret delivery, key rotation and rollback controls are not implemented by this phase.

| Family | Lifetime behavior reused from the approved transition code |
| --- | --- |
| Auth | 30-minute idle deadline, eight-hour absolute maximum; activity touch updates only metadata, physical expiry and revision, without reencrypting credentials. |
| Browser | Anonymous state 30 minutes; authenticated state up to eight hours, with auth-parent validation. |
| Refresh reservation | At most 30 seconds and bounded by the existing deadline; uncertain operations are not replayed. |
| Login CSRF challenge | 30 minutes; realm/purpose isolation and atomic consumption. |
| PKCE pending recovery | Ten minutes; reservation shortens the operation window. |
| Recovery grant | At most ten minutes/provider deadline; single-use reservation; separate provider replay receipt lasts 630 seconds. |
| Email verification | 30 minutes; independent resend/verification throttles and shared email rate state. |
| Login/allocation rate | Fixed 60-second window; increment does not slide the deadline. |

Unrelated reads do not renew these deadlines. Bounded writes reclaim up to 128 expired payloads. An operator-only cleanup function deletes at most 512 expired entries per table per call, preserving fences while dependent payloads/markers exist. It is not granted to the runtime. A monitored external cleanup schedule, vacuum/bloat management and cleanup/recovery concurrency qualification remain necessary; no sleeping Flask cleanup thread is relied upon.

## 4. Recovery trust boundaries and security findings

`RecoveryFence` requires an injected provider and configured binding. Missing provider is rejected. Every proof must match a new request nonce, expected authority/incarnation/realm epochs, a nondecreasing worker revision floor, an issue time within two seconds, a response budget of one second and OPEN/VERIFIED status. Workers reject a mismatching database gate. Existing pools cannot be inherited across process fork. No environment variable or database value bootstraps a trusted provider.

The local test controller runs outside database snapshots; it can demonstrate that a **current** controller fences old data and old deployments. It is process-local test infrastructure on the same host, without protected persistence, authentication or an enforceable restore detector. Nonces prevent proof replay; they cannot detect a restored service generating a fresh nonce response from old state. The per-worker revision floor also cannot protect a newly started worker from a consistent all-store rollback.

| Tested scenario | Security outcome |
| --- | --- |
| Old payload restored after logout, current tombstone retained | Rejected; terminal revocation remains valid. |
| Old refreshed payload restored, current version history retained | Fail closed on inconsistent revision. |
| Full pg_dump restore, controller incorrectly continues VERIFIED with old epoch | **UNSAFE: revoked session resolves again.** This proves a DB-local gate and independent process alone are insufficient. |
| Declared uncertain restore, controller BLOCKED/UNCERTAIN | Fail closed before accepting restored authority. |
| Current controller advances epochs; DB gate still old | Fail closed. |
| Current controller advanced; application environment/binding rolled back | Old deployment rejected, including a fresh worker with the old binding. |
| DB gate QUALIFYING | Fail closed. |
| Gate and current controller agree on a never-used new epoch | Old sessions absent in new namespace; deliberate reauthentication required. New verified login works. |
| DB recovery epoch rolled backwards independently | Rejected by current controller/binding. |
| DB, deployment binding and test controller all rolled back | **UNSAFE: revoked session resolves again.** No production rollback-resistance claim. |
| Missing/unavailable/stale/corrupted/inconsistent proof | Rejected or unavailable; no cookie-to-credential reconstruction or memory fallback. |
| Ordinary clean PostgreSQL restart and new worker processes | Valid ciphertext/revisions/deadlines preserved; acknowledged revocation remains invalid. |

Database restore, deployment environment rollback and code redeployment are separate risks. They must be fenced independently, not treated as ordinary clean restart. The tested provider supplies no automatic detection of an undeclared database restore. A stale internally consistent controller can incorrectly attest freshness; such a provider is outside the security assumptions and demonstrably unsafe.

The minimum production recovery contract remains: independently current control outside DB/config backup boundaries; close traffic and drain old workers/in-flight requests before any uncertain restore/promotion; invalidate all sessions with never-reused incarnation and realm epochs; install/verify the new gate in maintenance; start only approved compatible workers; require fresh independent logins and restart in-progress recovery/verification. Keep the gate closed if current control cannot be established. Operator intent alone is insufficient without enforceable pre-use fencing and tested incident ownership. No suitable production provider, transport, protected revision floor, restore interlock or redeployment policy has been supplied or qualified.

## 5. Exact test results and failures

- Final focused real-PostgreSQL run: **39 passed, 21 subtests passed, 34.49 seconds**. This includes nine original storage cases plus two additional TTL/resource-bound cases, shared offline recovery checks, Flask workflow cases and inherited storage cases repeated in the Flask fixture. Counts overlap; these are executed tests, not 39 unique security requirements.
- Full Python regression: **1,108 passed, 74 skipped, 1,407 subtests passed, 77.39 seconds**. The 74 opt-in skips are 63 legacy Redis cases and 11 PostgreSQL storage cases; PG application cases are constructed only for the focused fixture. The PG cases are exercised in the focused run, not by supplying a live DSN to the full regression suite. Offline recovery checks overlap both runs.
- JavaScript: **69 passed, zero failures**, 337.094 ms recorded duration. Node needed permission to spawn its local test workers; the restricted attempt failed with EPERM before the successful rerun.
- Browser: **24 checks passed** using Chromium, two tabs/one temporary profile, both login orders, independent logout, mobile/desktop navigation and no horizontal overflow. These are two Flask instances in **one** process; they are not two production WSGI workers. Separate process tests cover backend sharing/refresh ownership/restart only.
- Backend qualification: **20 checks passed**, including **two checks that confirm unsafe recovery counterexamples**, not 20 secure scenarios. Evidence: `qualification-results.json`.

Coverage includes CSRF cross-realm rejection, unauthorized Admin denial, fresh membership failure handling, B's mutation attribution contract, User/Admin independent expiry, PKCE callback/reset and email verification across Flask instances, disjoint browser CAS/conflicting writes, in-flight login/logout fencing, static bypass, lost post-commit acknowledgement, real role-denial probes, pool exhaustion, gate-lock timeout, clock drift, stale snapshots, admission denial and bounded operator cleanup. Independent family expiry and fixed rate windows are exercised against real SQL, with shortened local deadlines.

Initial resolved fixture errors: the gate-lock SELECT required UPDATE permission (corrected with the narrow read/lock function); cleanup used a reserved variable name (renamed); spawned browser helpers collided by module name (explicit helper loading fixed it). A failed browser launch required verified local fixture cleanup. There are no remaining functional test failures in the final recorded runs. The two unsafe restore findings are unresolved security failures under those trust configurations. PostgreSQL power-loss/crash failover, real protected-controller failure, actual Supabase pooler/TLS and hosted browser acceptance remain unproven.

## 6. Measurements and operating bounds

Measured on local Docker PostgreSQL 17.11 with synchronous_commit and fsync enabled, synthetic 1,500-character access tokens, 64-character refresh tokens, AES-GCM and a separate-process test controller. Component measurements include its local RPC cost; they are not hosted HTTP throughput or an SLA.

| Measurement | Observed |
| --- | ---: |
| Clean restart to validated reads | 0.8679 s |
| Database outage denial | 1.0021 s |
| 100 credential/browser pairs created sequentially | 6.2599 s |
| Pair creation p50 / p95 | 61.283 / 69.056 ms |
| 100 reads, four threads, pool size two | 136.04 operations/s |
| Read p50 / p95 | 27.598 / 42.2 ms |
| 100 activity touches | 5.1795 s |
| Payload revisions advanced by those touches | 100 |
| Ciphertext changes from reads / touches | 0 / 0 |
| Dataset payload rows / revision rows | 204 / 204 |
| Ciphertext bytes | 326,904 |
| Allocated gate + records + versions + empty tombstone table/index bytes | 835,584 |

The dataset includes a few restored/epoch-test records; it is not precisely 100 active users. Roughly 8.2 KiB allocated per credential/browser pair at this small scale is illustrative only; WAL, backups, dead tuples, autovacuum, recovery/CSRF/rate volume and other Supabase data are additional. No realistic peak-load or retention-window capacity claim is made.

Default per-realm admission: 4,096 retained reference-history entries and 32 MiB live ciphertext; configurable only within explicit hard caps (16,384 entries / 64 MiB). This is a reference/churn bound, not 4,096 users. High churn can deny fresh allocation/rotation until safe cleanup. Revocation of existing state remains possible at admission capacity. Storage OOM/disk-full or hosted DB connection exhaustion is not qualified.

Pool defaults: min zero/max two, at most eight waiters, one-second checkout, two-second connection timeout and health check. A future W-worker deployment with one such pool per worker consumes at most 2W client connections, plus maintenance/other services; use the actual shared project/pooler budget, not a guessed limit. Each worker creates its own pool after fork.

Transactions set 750 ms lock, 1,500 ms statement and 2,500 ms idle-transaction limits; a two-second total-operation check runs before commit. Clock difference over five seconds fails closed. Provider proof validation rejects responses over one second after return; a real transport must itself enforce a deadline, since an arbitrary blocked Python provider is not interruptible by that check. A post-check failure may follow commit and must never trigger blind retry. These are local bounds, not distributed response guarantees.

Writes currently serialize per realm, perform bounded quota accounting over the small dataset, and update a separate high-water row. Snapshot reads use one transaction plus gate/time/read queries and two control proofs; activity touch uses a snapshot transaction and a write transaction, updating two revision-bearing rows. This avoids aggregate rewrites but still costs multiple round trips. Query consolidation and narrower contention need representative workload evidence before production tuning.

## 7. Compatibility and remaining production work

Flask route/workflow contracts passed via synthetic injection. Active wiring remains intentionally absent. Future work must extract/inject neutral adapters for browser, auth, pending, grants, verification and challenges, avoiding a deployable dependency on a legacy `redis-local` factory. Readiness/startup configuration is still Redis-specific and must not be relabeled as PostgreSQL-ready.

The SQL uses ordinary PostgreSQL transactions, JSONB, bytea, advisory transaction locks and row locks. Supabase compatibility is plausible, not tested. For persistent IPv4 hosting, Supabase documents its session pooler; transaction pooling also requires disabling prepared statements/session-scoped assumptions. The isolated factory already uses `prepare_threshold=None`, transaction-scoped locks and SET LOCAL, but actual custom-role pooler connection/grants and server version still require isolated qualification. Production needs a separate reviewed factory with certificate/hostname validation and protected secret delivery; this loopback-only factory deliberately cannot connect remotely. [Supabase connection documentation](https://supabase.com/docs/guides/database/connecting-to-postgres), [Psycopg pool documentation](https://www.psycopg.org/psycopg3/docs/advanced/pool.html).

Render Free currently sleeps after 15 idle minutes and loses local filesystem changes on sleep/restart/redeploy. Keeping sessions in Supabase avoids local-disk loss, but sleep/wake is not tested here and does not justify extending expiry. Render explicitly positions Free for preview/testing rather than production. No LMDB/test controller, keys or recovery authority should live on that ephemeral disk. Actual project connection limits, plan capacity, backup capabilities, availability target and operating ownership remain unknown. [Render Free documentation](https://render.com/docs/free).

Required before activation: protected recovery/interlock decision and proof, neutral app wiring, additive reviewed private schema/grants and deployment configuration, verified DB TLS/custom-role pooling, keyring delivery/rotation, trusted-host/root/proxy/cookie acceptance, monitored cleanup/capacity/alerts, crash/commit-uncertainty and hosted faults, provider recovery acceptance, explicit epoch cutover and compatible rollback rehearsal. Destination management, Environment, photos, audit SQL and recommendations need no contract changes; fingerprint evidence confirms the existing three SQL contracts and 17 prior source/dependency files remain unchanged.

## 8. Updated eight production gates

| Gate | Status | Evidence still required |
| --- | --- | --- |
| G04 HTTPS/hosts/proxy | **FAIL** | Local cookie/header/browser contracts only; real ingress, host enforcement, proxy trust and HTTPS acceptance absent. |
| G06 Keys/secrets | **FAIL** | Actual DB role/credential/keyring delivery, rotation, predecessor-reader and config rollback controls unqualified. |
| G12 Startup/readiness | **FAIL** | Production refusal preserved. No approved PostgreSQL launcher, neutral wiring, real recovery provider or readiness configuration. |
| G13 Multiworker/recovery | **FAIL** | Local separate-process reads/refresh ownership/restart passed; full hosted Flask worker/pooler/sleep/rolling-deploy behavior unqualified. |
| G14 Durable revocation | **FAIL** | Atomic local revoke/version fences pass. Same-epoch full restore and all-trust-store rollback restore revoked authority without enforceable independent recovery control. |
| G17 Operations | **FAIL** | Actual capacity/limits, TLS/roles, monitored cleanup, persistence/backups, alerts and protected recovery ownership absent. |
| G18 Faults/SLOs | **FAIL** | Local outage, bounds and small benchmark pass; crash/power-loss/failover, actual network/control latency, disk/OOM and peak workload unqualified. |
| G20 Rollout/rollback | **FAIL** | No approved active implementation, protected cutover or compatible code/environment rollback rehearsal. |

## 9. Decision

The isolated transactional store is a viable implementation candidate, not an approved production authority. **GO for a separately approved isolated phase to resolve recovery trust/interlocks and neutral Flask integration. NO-GO for activation or production deployment; all eight production gates remain FAIL.** If the restore boundary cannot be independently enforced, remain closed and require deliberate reauthentication through a qualified recovery process. Do not add another same-boundary witness or claim PostgreSQL itself prevents rollback.

Stop pending approval. No activation, production schema or infrastructure work is authorized by this report.
