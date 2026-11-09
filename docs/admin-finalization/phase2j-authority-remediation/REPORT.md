# Phase 2J — authority rollback remediation and isolated qualification

**PASS for the implemented fail-closed boundary and conditional interface tests. NO-GO for production.** The default shared-session factory now refuses startup without an explicitly supplied protected authority. Restored LMDB or same-host witness state cannot authorize sessions through the default `RedisRealm` path. No external infrastructure or production transport was provisioned; **all eight production readiness gates remain FAIL**.

With a test-only metadata service excluded from the legacy-store rollback operations, all three Phase 2I counterexamples were reproduced on the explicitly unprotected historical path and rejected on the new interface path. This is **conditional protocol evidence, not proof that an independently protected production authority exists**. The local test service shares this host/user and could itself be rolled back. If that trust boundary is violated, safe freshness is unproven; no claim is made that another local service solves it.

GO only for separately approved isolated external-service/transport and recovery qualification. No production Redis, authority, secrets, SQL, authentication settings, sessions, destinations, photos, audit records or flags were accessed/provisioned/changed. The production startup safeguard is unchanged. Nothing was staged, committed, pushed or deployed.

## Root cause and validation trace

The old path was `RedisModel.resolve` → `RedisRealm.snapshot` → `now/guard` → local descriptor → local record metadata → Redis GET/PTTL → metadata re-read → ciphertext digest check → AES-GCM decryption → expiry check. A matching restored descriptor/record/digest and still-unexpired envelope passed. Neither a ciphertext tag nor a hash states whether that record was revoked later.

| Phase 2I failure | Restored state / current state | Why stale authority passed |
| --- | --- | --- |
| Joint Redis/LMDB rollback | Old encrypted Redis record and old local metadata/control; same encryption keys and epochs. Later revocation disappeared from metadata. | Both copies agreed on the old digest/expiry. Generation was also restored, so local guard and AEAD checks had no independent current reference. |
| Authority-only rollback with leftover ciphertext | Old LMDB metadata restored; Redis was not restored. Failed cache deletion had left the original ciphertext physically present. | Metadata deletion was the effective revocation. Restoring it made the untouched, valid encrypted bytes usable again. Cache deletion cannot be the durability guarantee. |
| Redis/LMDB/witness rollback | Old Redis, local metadata and valid older witness journal prefix; matching control serial/epochs/keys. | A hash chain detects invalid edits but accepts a valid old prefix. The witness was inside the same recoverable host/storage boundary. No independently protected high-water state remained. |

These histories are indistinguishable from the earlier legitimate state if **every trusted input is restored together**. A client cannot infer a later revocation from matching old state alone. This requires an independent trust boundary, or refusing authority until an independently controlled invalidation/recovery action has occurred.

## Architecture selected and alternatives

The selected future architecture is an **external authoritative metadata service**, not an LMDB-plus-new-local-witness combination. It owns current record digests/deadlines, generation/epoch control, admission quotas and atomic expected-revision updates. Redis remains the encrypted payload cache. Local LMDB is not consulted by the protected client. This removes the dual-local-store circular proof; it does not by itself prove the external service is restore-safe.

| Alternative | Assessment |
| --- | --- |
| Independently administered authoritative session/metadata service | Selected interface. Requires authenticated primary/quorum reads, durable linearizable CAS, bounded operations, independent restore control and a restore-safe incarnation/freshness anchor. No provider/transport was selected or provisioned. |
| Durable transactional database | Viable if it supplies the same durability, conditional transactions and independent restore/epoch controls. Transactions or synchronous replication alone do not establish freshness after all members/backups are restored. No production SQL or schema work is authorized here. |
| Mandatory global invalidation after uncertain recovery | Required conservative recovery fallback: independently close traffic, fence old workers, advance never-reused generations/epochs and require sign-in/recovery restart. It is safe only if restore uncertainty is detected before authority dispatch and invalidation control cannot be restored with the app. An undetectable rollback cannot be fixed by a runbook alone. |
| Another same-host journal, witness, signing key or file counter | Rejected as production durability. It is inside the demonstrated rollback domain. RAM-only generations also do not provide safe multiworker/restart persistence. |

Redis documents that replication/`WAIT` is not strong failover consistency. Etcd recovery also treats restoring a cluster as a distinct recovery operation; a consensus product is not automatically a non-restored external anchor. These are inputs to provider qualification, not evidence that this implementation is production-ready. [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/), [Etcd recovery](https://etcd.io/docs/v3.6/op-guide/recovery/).

### Trust and rollback boundaries

| State | Permitted role / trust assumption |
| --- | --- |
| Redis ciphertext, TTLs, replicas and AOF snapshots | May be missing or stale. Cannot grant authority without current protected metadata. Old valid ciphertext is not proof of freshness. |
| Local LMDB/control and legacy witness journal | Untrusted as current authority by default. Can be used only in an explicitly unprotected historical test path. Neither bootstraps a protected binding. |
| AES keyring | Provides confidentiality/integrity, not revocation freshness. Restoring old keys alongside snapshots can make old ciphertext decryptable. Real secret-manager/rotation qualification is still required. |
| External metadata service | Must be outside the app/Redis/local-witness restore and administrative boundary, return linearizable current state and acknowledge only durable conditional changes. Application identities cannot rewind/control its incarnation or restore its backups. |
| Authority binding | Authority identity, current protected incarnation and minimum sequence must come from a separately reviewed control plane, not the restored stores. New/cold workers must not bootstrap from an old restored descriptor. |
| Transport | Must authenticate the actual service, bind responses to requests, enforce deadlines/size/realm permissions, and never transparently retry uncertain mutations. No production transport is implemented. |

The service's incarnation must be protected by an independently controlled monotonic freshness anchor, or recovery must create a never-reused incarnation before opening requests. **A rolled-back service that can emit old metadata with a fresh nonce and an apparently current identity/sequence violates the trust contract and remains unsafe/unproven.** Client-side structural checks do not detect every such lie. This cannot be resolved with the currently available same-host test infrastructure.

## Exact corrective implementation

1. **New `protected_session_authority.py`:** `AuthorityBinding`, a `FreshnessTransport` protocol and `ProtectedRevisionAuthority` implement the existing metadata authority API. Each operation requires a fresh request ID, matching pinned identity/incarnation, nondecreasing sequence and bounded response. Malformed, replayed, unavailable, late, closed or inconsistent responses raise sanitized `SessionStorageUnavailable`; conflicts raise `RevisionConflict`. There is no positive metadata cache or local fallback.
2. **`record_session_store.py`:** `RedisRealm.guard` now requires the protected adapter by default. `local_realms` refuses before reading key/LMDB configuration or touching Redis if no protected adapter is explicitly supplied. No environment variable enables a fallback. An explicit Python-only `unprotected_local_testing=True` option retains historical mechanics/counterexample tests; it is not a supported production path and is never selected by application environment/configuration. The unconditional production refusal remains unchanged in `session_realms.py`.
3. The protected service atomically owns metadata commits, then the existing backend publishes encrypted payloads to Redis. This preserves the prepare-before-publication rule, independent expiry and revocation semantics. A failed/uncertain external commit is not retried; an ambiguous provider action is not repeated. Missing publication can lose availability but cannot restore old metadata through a compensating rollback.
4. **`tests/protected_authority_fixture.py`:** a clearly labelled test-only service uses LMDB/RLock and a separate Manager process for isolation/concurrency scenarios. Its local persistence and process sequence are **not** an external durability guarantee. The Manager IPC codec/authentication is not a proposed production transport. No production module imports this fixture.
5. **`tests/test_protected_session_authority.py`:** new negative/default/configuration/response-validation/deadline/conflict tests. Existing Flask Redis fixtures now explicitly inject the protected adapter backed by the synthetic service. Historical direct-store tests explicitly declare the unprotected test option, preventing them from being mistaken for protected rollback qualification.

The externally authoritative payload is only metadata: digest, logical expiry, accounting/scope and generation/activity fields. Supabase credentials, recovery secrets, CSRF material and mutable browser values remain encrypted in bounded Redis records using the existing AEAD/AAD rules. No SQL/RPC/audit/photo/Environment contract, business route or recommendation logic changed.

### Deliberate behavior change

The normal **`redis-local` application startup now fails closed** until a separately reviewed protected service is injected. Existing saved Redis/LMDB settings alone are insufficient. The application does not silently resume local sessions or switch to development/memory mode. In the current unavailable-infrastructure state it cannot offer successful shared-mode sign-in; deliberate reauthentication is needed after future approved service/cutover configuration, not before service readiness.

Existing development-mode authentication remains unchanged and local-only. Production still refuses activation. No production endpoint, secret, new environment bypass, backend selector or automatic legacy-session import was added. Old Phase 2F–2I lab helpers are preserved historical evidence; helpers that construct raw authority now need an explicit local test option and must not be used as production launchers.

## Before/after isolated qualification

All Redis tests used the Phase 2H digest pin `redis:8.4.8@sha256:6805005a84497806df31105912c91415afe473da3c3d6732e74d112ec49254ac`. The destructive lab reused the unchanged owned-container controls from Phase 2I: TLS/mTLS, restrictive realm ACLs, fsync-always AOF, strict truncated-load refusal, noeviction and numeric-loopback published ports. No app permissions were broadened.

The external **test fixture was excluded from the old Redis/LMDB/witness rollback operations**. It remained current in a separate process/directory. It is still on the same host/user and is not independently protected infrastructure. An initial synthetic metadata seed into the legacy copy was test setup to reproduce the historical acceptance path, not an implementation of production session migration.

| Scenario | Historical unprotected path | Corrected default | Injected-current-service test / classification |
| --- | --- | --- | --- |
| Authority-only rollback with leftover ciphertext | **FAIL:** revoked session accepted; Redis unchanged after revoke | **PASS:** raw local authority rejected | **Conditional PASS:** external deletion remains current; record denied; revoked user must sign in again |
| Joint old AOF + LMDB restore | **FAIL:** revoked session accepted | **PASS:** local-only proof rejected | **Conditional PASS:** physically restored ciphertext denied by current external metadata |
| Old AOF + LMDB + witness journal prefix | **FAIL:** old witness permits revoked session | **PASS:** witness is not a protected adapter | **Conditional PASS:** current external metadata denies it; witness state is irrelevant |
| Redis-only old dataset | Old record physically present | No local fallback | **Conditional PASS:** no current metadata; denied |
| Local LMDB-only restore/current LMDB | Local bytes may match old cache | **PASS:** neither is accepted as protected proof | Protected path never reads local LMDB; relies on external service |
| All local legacy stores restored, no external authority configured | Matching restored state could historically grant authority | **PASS, closed:** factory refuses startup | Requires reviewed authority configuration and reauthentication; no local continuation |
| All stores **including the freshness service/control plane** rolled back | Phase 2I demonstrated resurrection | Default remains closed when no service is configured | **UNPROVEN/unsafe if the service contract is violated.** Independent anchor/restore enforcement unavailable; no production PASS |
| Redis SIGKILL/recovery, current external service | — | Default not enabled without infrastructure | **Conditional PASS:** valid A/B sessions survive; revoked session stays denied |
| Stale actual TLS replica promotion | Old ciphertext physically present | No local fallback | **Conditional PASS:** missed acknowledged revocation does not reappear |
| Independent User/Admin revocation | — | No cross-realm fallback | **Conditional PASS:** revoking either leaves the other valid |
| Restarted app-side processes | — | Raw metadata cannot bootstrap them | **Conditional PASS:** four fresh/restarted reader processes perform 80 correct A/B reads; two further refresh workers yield one owner |
| Freshness service unavailable | — | **PASS, closed** | Active Redis credentials and readiness denied; no fallback |
| Replayed nonce, old incarnation/sequence, corrupt descriptor, nonfinite response | — | **PASS, closed** | Unit tests reject the tested invalid responses; this is not proof against an authenticated service lying about current metadata |
| Late reply / metadata conflict / cross-realm commit scope | — | **PASS, closed/conflict** | No automatic retry or silent overwrite |

Evidence: [qualification-results.json](qualification-results.json). It records physical existence=true, historical resurrection=true and corrected resurrection=false for each of the three original scenarios. **27 isolated checks passed.** Redis crash recovery to TLS readiness measured **0.5626 seconds**, excluding failure detection/service recovery/production load. This is not a production RTO or a sustained throughput qualification.

The response budget rejects a reply that arrives too late; it does not interrupt a hung transport by itself. A real bounded I/O transport/watchdog is still required. The per-client RPC lock serializes response-floor updates but is not a cross-worker lock; the authoritative server must provide CAS. Its live process/LMDB fixture supplied those semantics in the test. Production fencing, host restart, all-member restore, power loss, quorum/election, secret controls and operator IAM remain unqualified.

## Tests and preservation

| Suite | Final result |
| --- | --- |
| New authority/default boundary plus readiness unit run | **14 tests + 31 subtests PASS** (included in focused/full results) |
| Focused protected-interface + real Redis + readiness | **77 functions + 31 subtests PASS**; [focused-output.txt](focused-output.txt), [focused-test-results.xml](focused-test-results.xml) |
| Complete Python `tests/` | **1,105 functions + 1,402 subtests PASS; 63 opt-in Redis cases skipped**; [python-output.txt](python-output.txt), [full-test-results.xml](full-test-results.xml) |
| JavaScript | **68 PASS, 0 FAIL**; [javascript-output.txt](javascript-output.txt) |
| Destructive conditional qualification | **27 checks PASS; all three historical failures reproduced then denied**; [qualification-results.json](qualification-results.json) |

The skipped 63 cases were run separately in the focused suite; counts overlap. The focused Flask fixtures inject the protected service adapter for login/logout/CSRF/recovery/membership/actor paths. Direct-store historical tests use the explicit unsafe option and **do not** establish protected production durability. Source fingerprints distinguish the expected changes from preserved auth/crypto/business code. Migration 0014, photo-contract SQL and audit-wrapper SQL bytes remain unchanged. See [verification-summary.json](verification-summary.json).

No actual production membership change, audit insertion, Supabase refresh/recovery or business mutation occurred. Admin B attribution and fresh membership behavior are synthetic regression evidence; real audit-write acceptance remains separately authorized. Chromium/mobile/actual target WSGI acceptance was not rerun. User/Admin cookie construction, encrypted state, CSRF purpose/realm boundaries, recovery isolation and destination contracts were not changed.

An initial unit launch lacked OS permissions for temporary LMDB files and failed in fixture setup; the same tests passed with local process/temp-file permissions. The first destructive run attempted an `EXISTS` diagnostic using an application identity without that grant; it was corrected to the already allowed GET, without granting permission. Final results above are from the corrected runs. No final test failure remains within the stated scope; independent infrastructure remains an unresolved gate, not a passed test.

## External dependencies and recovery requirements

Before production: select/review the authoritative service and exact failure model; implement authenticated, bounded, non-retrying transport with per-realm/namespace permissions; provision only under separate approval; qualify durable linearizable commits and primary/quorum reads; establish a restore-safe independent incarnation/epoch anchor and bootstrap path for cold workers. Separate app, snapshot-restore, secret/KMS and control-plane gate-opening permissions. Application credentials must not rewind records or restore backups/change generations.

An uncertain restore/failover must close dispatch **before** old authority is used, fence/drain old workers and reconcile already dispatched provider/database operations without replay. If freshness cannot be proved, use a new never-reused protected incarnation/generation/epochs, invalidate old bindings and require independent User/Admin sign-in and recovery/verification restart. If the anchor is unavailable or may also be old, remain closed. Never rewind metadata to match Redis, import old handles as live authority, disable the safeguard or switch to memory/shared-cookie Admin authority. A separately qualified compatible rollback/maintenance release is required.

## Eight production gates

| Gate | Status / outstanding work |
| --- | --- |
| G04 — HTTPS/hosts/proxy | **FAIL** — actual topology, private ingress, certificates and browser acceptance remain unqualified. |
| G06 — key lifecycle | **FAIL** — secret manager/IAM/KMS, rotation/retirement and compromise/recovery not qualified. |
| G12 — startup/readiness | **FAIL** — safe default closure implemented; real protected transport/backend and reviewed production launcher/readiness missing. Safeguard retained. |
| G13 — multiworker/recovery | **FAIL** — conditional multi-process/crash cases pass; target WSGI, rolling releases and infrastructure recovery remain unqualified. |
| G14 — durable revocation | **FAIL** — original local acceptance paths are blocked by default; no independently protected production service/freshness anchor or all-store restore guarantee exists. |
| G17 — Redis operations | **FAIL** — local fixed-image TLS/AOF cases pass; provider/authority failover, operator readiness separation, capacity and alerting remain unqualified. |
| G18 — fault bounds | **FAIL** — transport cancellation/watchdog, fleet clocks, quorum/disk/host faults and sustained SLOs remain unqualified. |
| G20 — rollout/rollback | **FAIL** — reviewed target release, reauthentication cutover and independently protected recovery rehearsal remain outstanding. |

**GO for the next approved isolated service/transport qualification phase; NO-GO for production. Stop here pending explicit approval.**

## Exact files changed

- Added `protected_session_authority.py`.
- Modified `record_session_store.py`.
- Added `tests/protected_authority_fixture.py` and `tests/test_protected_session_authority.py`.
- Modified `tests/redis_record_cases.py` and `tests/test_redis_sessions.py`.
- Added this documentation directory: `REPORT.md`, `run_qualification.py`, `verify_evidence.py`, `qualification-results.json`, `verification-summary.json`, focused/full Python output/XML and JavaScript output.

No dependency, environment, deployment, SQL, business/auth route or previous evidence file changed. Previous uncommitted work is preserved. Owned Docker containers/network/anonymous volumes and active local test listeners were cleaned up; ephemeral keys, copied stores and journals were not archived. Generated bytecode is not a deliverable.
