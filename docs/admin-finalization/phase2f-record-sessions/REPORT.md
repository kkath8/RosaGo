# Phase 2F — record sessions, revision fencing and local verification

**GO for the next isolated qualification/review phase after approval. NO-GO for production provisioning, activation or deployment.** The production startup refusal is unchanged. Redis-only replay protection is demonstrated locally; independently protected production authority storage and qualified recovery/failover are still blockers.

## Resume and exact implementation changes

The resumed work reviewed the Git diff and the three existing partial modules before editing. They compiled, but the old tests imported removed aggregate functions, fixtures did not bootstrap independent authority, and configuration/readiness, quotas, faults and evidence were unfinished. The original work and test source were copied into `resume-baseline/` before changes. Earlier unrelated uncommitted work was retained; nothing was staged, committed, pushed or deployed.

Exact application/dependency/test files changed or added across Phase 2F:

| File | Change |
| --- | --- |
| `record_session_store.py` | New v3 bounded per-record backend, independent revision checks, native TTLs, atomic cache publication, family adapters, memory admission and local readiness. Completes the prior partial implementation. |
| `session_authority.py` | New independent LMDB metadata authority: fsynced cross-process transactions, generation gate, revision digests, expiry index, family counts and realm byte quotas, bounded writer admission and local-filesystem restrictions. Completes the prior partial implementation. |
| `redis_session_flask.py` | Completes opaque browser integration, atomic login/logout/rotation, field CAS, safe static bypass, cookie handling and root/HTTPS validation. |
| `session_crypto.py` | Extracted AES-GCM/tagged JSON codec with a 32 KiB plaintext / 45,000-byte ciphertext record bound and sanitized serialization failure. |
| `redis_session_store.py` | Compatibility imports into the v3 backend; the whole-realm aggregate implementation is removed from the runtime path. |
| `session_realms.py` | Initializes the required independent authority-backed local backend, opt-in HTTPS/proxy qualification and both-realm readiness endpoint. Keeps unconditional production refusal. |
| `session_readiness.py` | New offline production configuration preflight and explicit local HTTPS/proxy qualification. Neither grants production approval nor connects to remote Redis. |
| `app.py` | Cookie Secure config reflects the selected adapter, preserving insecure HTTP only in the explicit development/local HTTP profiles. No business route logic changed. |
| `normal_auth_flask.py`, `admin_session_flask.py` | Classify backend entry failures as unavailable without clearing authority; retain a rendered login/recovery path after uncertain credentials. |
| `requirements.txt` | Add pinned `lmdb==1.7.5`, retaining `redis==6.4.0` and the existing UTF-16 file encoding. Installed only in the local venv. |
| `tests/redis_record_cases.py` | New real Redis record/revision/TTL/replay/crypto/admission/concurrency/resource cases, reusable by the Flask integration fixture. |
| `tests/test_redis_sessions.py` | Migrates aggregate-specific fixtures to v3 and retains the User/Admin, recovery, CSRF, cookie, stale-request and B-attribution scenarios. Original test source is archived in the resume snapshot. |
| `tests/test_session_readiness.py` | New offline startup/configuration/proxy/security-negative cases. |

This documentation directory also contains the report, local operating instructions, sanitized evidence, fault/benchmark harness, a two-process browser fixture/router, test output/XML, six screenshots and historical resume snapshots. Snapshots are evidence, not deployable modules.

## Actual data layout and lifecycle

Redis keys are `<namespace>:sessions:v3:<realm>:<epoch>:<family>:<SHA256(reference)>`. User/Admin realms and epochs stay separate. The reference can be a random 256-bit handle or a purpose-bound deterministic reference such as an email cooldown; raw handles, email addresses and IPs are not key names. No v1 aggregate is imported as authority.

Each encrypted record authenticates its full key, key ID and complete identity/generation-bearing payload. A fresh AES-GCM nonce is used on replacement. Credentials, PKCE verifiers, grants, CSRF challenges, browser values and verification state remain encrypted. Keyring material is generated in memory for tests and is never saved in evidence/source. Mutable User browser state remains server-side behind its opaque root cookie; Admin uses only its separate /admin cookie. The secure profile remains host-only, Secure, HttpOnly, Lax with the approved cookie prefixes.

| Family | Logical expiry / Redis TTL |
| --- | --- |
| `auth` | 1,800-second idle, capped at 28,800-second absolute lifetime. Successful authorization updates independent activity metadata and PEXPIREAT; it does not reencrypt unchanged tokens. |
| Auth refresh reservation | The credential revision becomes busy and expires within 30 seconds. Expiration removes authority rather than making an old refresh token available to another owner. Successful verified replacement restores the remaining idle/absolute bounds. |
| `web` | Pre-login browser state: 1,800 seconds. Authenticated browser binding: fixed 28,800-second bound; credential idle expiry independently controls authentication. Reading a page does not renew/rewrite browser state. |
| `login` | Realm-purpose challenge, 1,800 seconds, consumed with the browser's login-operation reservation. Login completion additionally has a 30-second parent-operation deadline. |
| `pending` | PKCE pending state, 600 seconds. Reservation shortens remaining authorization to at most 30 seconds; ambiguous exchange burns the flow. |
| `grants`, `used` | Recovery grant: tighter of verified expiry or 600 seconds; provider-session replay marker: 630 seconds. Password-update reservation is at most 30 seconds and uncertainty burns authorization. |
| `email`, `email_rate` | Pending verification: 1,800 seconds; per-email resend cooldown separately expires at its due time (normally 60 seconds). Unknown provider result retains the busy fence until expiry/restart of the flow. |
| `rate` | Independent fixed 60-second counters, purpose/realm/address bound; 20 attempts per window. Denied attempts do not extend the window. |

Each family record has its own Redis expiry; unrelated traffic cannot extend it. The independent authority also has an expiry-ordered index. Any metadata write/maintenance pass reclaims up to 256 expired entries across all families. An inactive realm needs no Redis traffic for native cache TTL cleanup. Expired metadata is logically denied even before physical index cleanup. There is no global 120-second receipt bucket or its previous 34-operation/second ceiling; exact prepared revisions support in-request acknowledgment reconciliation.

Authenticated browser bindings now use a fixed absolute TTL rather than renewing a separate browser idle timestamp. Authentication's 30-minute idle limit remains independently enforced. Recovery retry behavior is deliberately conservative: a new link/verification flow may be required after uncertainty. Legacy handles, an incompatible epoch/key/schema, or an uncertain cache publish may require reauthentication. An obsolete delayed cookie response cannot revive server authority, but may leave the affected browser realm needing sign-in.

## Independent revision authority and demonstrated limits

The independent LMDB environment stores only revision digests, deadlines, activity/generation metadata, quotas and the control descriptor. It stores no provider credentials. It uses sync/metasync, no async write map, and one local environment shared by processes. A bounded OS writer lock precedes metadata transactions; no provider call is made while that lock is held. Network paths and OneDrive/synchronized paths are rejected. Environment handles are shared locally, not positive authentication snapshots.

An atomic metadata transaction checks every expected revision and generation, takes replacement/deletion capacity credit, and commits all new digests/removals **before** Redis publication. Revocation is therefore authoritative even if old ciphertext remains or Redis cannot delete it. Cache publication checks old bytes, uses one MSET for positive revisions, then applies native expiries. A publish/TTL error never rolls the independent revisions backward to restore old credentials. Exact bytes and valid TTLs can reconcile a lost acknowledgment; otherwise affected state fails closed. Redis and a provider/database write are not one transaction, and business requests are never automatically replayed.

Read authorization requires the current independent descriptor/revision and matching ciphertext/TTL. It is not satisfied by a Redis replica, receipt, Lua success or a stale worker-local cache alone. Tests demonstrate both same-process old-ciphertext replay and a second Redis primary containing an older valid copy: acknowledged revocation remains denied with current independent metadata. Separate worker processes also demonstrate shared authority and one refresh owner.

**Unresolved production blocker:** the negative control restores an older authority snapshot alongside the older Redis copy, starts a fresh reader, and observes that old authority can return. This is explicitly recorded as `known_unresolved_joint_rollback_grants_old_authority: true`, not a security PASS. Local LMDB must not be restored with Redis or placed on an ephemeral/shared network filesystem. This prototype does not supply protected multi-host authority, an external anti-rollback generation anchor, independently controlled restore approval or a qualified production failover barrier. A fully compromised application/host or correlated rollback of both stores is outside its demonstrated protection. The production startup safeguard remains required.

Local browser-session revocation also does not globally invalidate an already issued Supabase JWT or recall an already dispatched provider/database operation. Fresh database-backed Admin membership and database-derived actor attribution remain unchanged. No provider Auth settings were changed.

An explicit revocation-only snapshot can fence unavailable/corrupted old credentials without treating their cache contents as authenticated data. Such a snapshot is forbidden from installing any positive record. This allows fresh verified sign-in to replace an uncertain old revision while preserving the other realm; it is not an authentication fallback. Entry failures are classified as unavailable so the login form remains available instead of hiding the deliberate reauthentication path.

## Admission, resource bounds and operational behavior

Current local policy is 4,096 live records **per family**, at most 32 MiB of ciphertext **per realm**, at most eight records in one transition, and a 32 KiB plaintext / 45,000-byte ciphertext record ceiling. Policy is part of the independent descriptor; incompatible workers are denied. Replacement/deletion credit is atomic, avoiding the former full-capacity rotation failure. No new space is required to remove revision authority, although an underlying authority disk/map failure can still deny a write rather than falsely acknowledge it.

New positive cache writes inspect actual memory usage and reserve at least 64 KiB or twice the intended ciphertext size under configured Redis maxmemory. This is admission headroom, not a guarantee against a concurrent OOM. Real OOM after independent preparation was tested: old credentials remain fenced, and the affected session needs reconciliation/sign-in. Revocation remains available under the tested Redis OOM condition. Noeviction is checked at startup/readiness; observed eviction closes authority access until controlled operator handling. There is no RAM fallback, replica authority cache or automatic generation change.

Local Redis connect/command timeouts are one second, command retries zero, pool maximum 16 per realm/worker, writer admission timeout one second, snapshot age bound two seconds, and Lua publication age bound ±250 ms. Redis/worker UTC disagreement beyond five seconds denies access. Filesystem/LMDB fsync, process scheduling and host clock recovery still require an external watchdog/qualified operating environment; these bounds are not a production real-time guarantee.

Static resources bypass the store without obtaining authority. Ordinary record reads do not SET, MSET or refresh TTL. Authorized activity performs the small TTL/independent-metadata update needed for idle expiry. UI updates use field CAS; conflicts are explicit, and cosmetic flash conflicts do not mask a known successful business response. New requests during unavailable cache/authority fail closed; some explicitly authority-free requests can remain available.

Local startup verifies both realms, initialized independent metadata, current generation/epochs, primary role, noeviction, clock agreement and backend availability. Readiness is available at `/auth/session-readiness` in redis-local mode and never reports production approval. The local readiness implementation uses operator-capable CONFIG/INFO checks; a least-privilege production monitoring/control integration remains unqualified. Production configuration preflight validates explicit mode/backend, verified-TLS URL form without override queries, keyring, HTTPS origin/trusted hosts, root mount, proxy trust and secure cookie flags, but does not enable a remote factory or bypass the production refusal.

## Measurements and test evidence

Exact counts and source fingerprints are in [verification-summary.json](verification-summary.json). Raw sanitized evidence is in `redis-test-results.xml`, `full-test-results.xml`, `javascript-output.txt`, `browser-results.json` and `backend-qualification.json`.

Final results: **67 focused tests plus 21 subtests PASS; 1,095 full Python tests plus 1,392 subtests PASS; 68 JavaScript tests PASS; 24 real-browser checks PASS; eight final-code server fault checks PASS.** The full suite's 63 opt-in Redis cases are skipped without the explicit loopback URL and are exercised in the focused run. The four offline readiness functions and their 21 subtests appear in both runs and must not be counted twice. No unresolved functional test failures remain. The correlated-store-rollback negative control remains an observed security limitation and a production blocker.

The benchmark used actual Redis 7.4.7 with AOF/fsync-always, redis-py 6.4.0, LMDB 1.7.5 on the local Windows host, and synthetic 1,500-character access / 64-character refresh credentials plus small User settings. It is a component benchmark, not production HTTP throughput or a chosen service SLO.

| Concurrent credential/browser pairs | Redis records | Measured Redis MEMORY USAGE sum |
| ---: | ---: | ---: |
| 100 | 200 | 392,000 bytes |
| 1,000 | 2,000 | 3,920,000 bytes |
| 2,000 | 4,000 | 7,840,000 bytes |

The LMDB file/map was 64 MiB; that file size is not a measurement of resident pages or peak process RSS. Creating the 2,000 pairs took 80.466 seconds with durable metadata and Redis persistence. Additional state families, queue buffers, provider traffic and burst workloads still need target-topology sizing.

At 2,000 pairs, four threads completed all 400 credential reads at 705.56 operations/second, with zero MSET/PEXPIREAT calls. All 400 authorized activity updates completed at 91.47 operations/second, with zero MSET calls and 400 PEXPIREAT calls. Measured network deltas were 146,821 input / 1,895,435 output bytes for reads and 240,491 input / 2,624,141 output bytes for activity. These include protocol/measurement overhead. Fsynced authority updates are a measurable throughput cost. Phase 2E's old aggregate estimate was a calculated worst-case bound, not an apples-to-apples measured baseline; no speedup percentage is claimed.

Eight actual local server fault checks passed: outage denial; intact AOF restart; separate stale-primary rejection; same-process replay rejection; real OOM/admission denial; revocation under OOM; OOM after prepare without rollback; and eviction denial. The correlated-store-rollback negative control remains an observed unresolved limitation.

The sizing/throughput run preceded the final busy-error classification and reauthentication correction; its successful read/activity paths are unchanged. All eight fault cases were repeated against the final implementation in `fault-checks-final.json`, without rerunning the 2,000-pair benchmark. Final focused and browser tests exercise the completed integration.

Focused tests cover all state families, actual cross-process reads/refresh ownership, TTL cleanup, CAS/deleted-parent rejection, shared recovery/verification, independent A/B login/logout/expiry, CSRF, nonmember denial, B's mutation bearer/actor contract, encryption/key transitions, lost acknowledgments, capacity, oversized state, pool exhaustion, lock deadlines and static bypass. Browser tests use two actual Flask worker processes and a local router, one Chrome profile/two tabs, desktop/mobile and both login orders. They are not a qualified production WSGI/proxy/TLS deployment.

Windows launcher indirection initially left a fixture worker holding a temporary metadata file during cleanup. The fixture now records actual worker PIDs and final-code hashes at startup, uses fresh dedicated ports, and shuts down the actual worker servers before joining launchers. The final 24-check browser run uses those verified workers; `worker-processes.json` hashes match the final runtime sources. This is test-harness evidence, not a production process supervisor.

Initial failures were resolved: sandbox-created temporary-file/IPC access required authorized local process permissions; one migrated child fixture used the wrong synthetic key; an outage mock bypassed the typed boundary; the browser's first relative fetch ran before navigation; and the correlated-rollback harness initially reset TTL instead of preserving absolute expiry. A final stress run also exposed a reader seeing committed busy metadata before ciphertext publication. It already denied authority; it now classifies the window as busy so a concurrent reserver cannot acquire/replay another refresh. The four-thread reservation check repeats ten times in each store/Flask fixture. No real secrets were exposed. Final functional failures, if any, are listed in the verification summary rather than hidden by those earlier attempts.

## Phase 2E gate assessment

PASS means the stated implementation/local envelope is verified, not production certification. **12 PASS, 8 FAIL remain.**

| Gate | Result / current scope |
| --- | --- |
| G01 Baseline integrity | PASS — saved resume evidence and final source/SQL fingerprints. |
| G02 Realm authority | PASS — separate namespaces, references, cookies and server contexts. |
| G03 Cookie construction | PASS — secure profile and local browser/header tests. |
| G04 Production HTTPS/proxy | FAIL — local qualification is implemented; actual ingress/TLS/host deployment is not qualified. |
| G05 Encryption | PASS — per-record AEAD and independent revision binding. |
| G06 Production key operations | FAIL — no reviewed production secret manager, rollout/retirement/compromise qualification. |
| G07 Atomic lifecycle | PASS locally — independent multi-record revision commit and conservative cache publication. |
| G08 Refresh/expiry fencing | PASS within the stated local authority/clock model. |
| G09 A/B, CSRF, recovery | PASS locally. |
| G10 Membership/actor contract | PASS locally; actual production audit insertion remains unverified. |
| G11 Outage denial | PASS locally — no fallback or false cache-based revocation acknowledgment. |
| G12 Production startup/readiness | FAIL — guard correctly retained; a qualified production authority/backend/launcher/monitor integration is absent. |
| G13 Actual hosting qualification | FAIL — two real local workers verified; target WSGI/fork/pool/rolling deployment remains unqualified. |
| G14 Durable production failover | FAIL — Redis-only replay denied, but correlated authority rollback and protected multi-host recovery remain blockers. |
| G15 Capacity/retention correction | PASS for the measured local bounds: independent TTLs, cross-family metadata GC, quotas, admission and tested control operations. Target infrastructure sizing remains G17. |
| G16 Write-amplification correction | PASS locally — no read ciphertext rewrites, measured per-record sizing/throughput. Production traffic/SLO certification is not claimed. |
| G17 Redis infrastructure | FAIL — production private TLS, ACL/monitoring separation, capacity/persistence/failover/provider/version qualification outstanding. |
| G18 Clock/resource operating guarantees | FAIL — implemented local checks/deadlines tested, but trusted host time, filesystem/watchdog bounds and incident recovery are not production-qualified. |
| G19 Business/database preservation | PASS locally — full regressions and SQL fingerprints; no production SQL/data/Storage operations. |
| G20 Rollout/rollback rehearsal | FAIL — no qualified previous v3 production release, staging restore/key-roll/rollback rehearsal or release approval. Safe fallback remains maintenance/reauthentication. |

The next approved isolated phase should qualify the protected authority/control-plane deployment and fault model, real TLS/proxy/ACL/monitor integration, realistic burst/resource limits, key rotation and compatible rollout/rollback. Do not provision/connect production Redis, ship redis-local mode, disable the startup guard, or resume the deferred production Draft write test on the basis of these local results.
