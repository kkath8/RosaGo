# Phase 2I — isolated crash recovery and failover qualification

**NO-GO for production.** Crash recovery and Redis-only stale recovery were safe in the tested cases when current authority metadata was preserved. **Revoked authority was restored in three rollback scenarios.** The current local LMDB authority and same-host experimental witness are not restore-safe production infrastructure. GO only for a separately approved isolated authority-protection/remediation phase, not production provisioning or deployment.

Final evidence: **46 positive qualification checks PASS, three security findings FAIL**. The FAIL findings are deliberately reproduced counterexamples, not successful security gates merely because the harness expected them. They are recorded separately in [qualification-results.json](qualification-results.json) and [checkpoint-results.json](checkpoint-results.json).

Only this directory was added. Runtime, dependency, SQL and previous evidence files remain unchanged. No production service, authentication setting, session, destination, photo, Storage object or feature flag was accessed or changed. No SQL was executed. The unconditional production startup refusal remains active. Nothing was staged, committed, pushed or deployed.

## Infrastructure and fault model

Every Redis container used the Phase 2H image:

`redis:8.4.8@sha256:6805005a84497806df31105912c91415afe473da3c3d6732e74d112ec49254ac`

The crash lab used TLS/mTLS, verified CA/hostname, disabled plaintext/default user, separate User/Admin key ACLs, fsync-always AOF, noeviction, 64 MiB maxmemory and 64 maxclients. Operator and application identities were separate. As in Phase 2G/H, app-side `CONFIG GET` is a lab readiness concession, not approved production least privilege. A labelled private test bridge connected the primary/replica; host ports were numeric loopback only. No production endpoint or secret was supplied. Credentials and encryption keys were synthetic/ephemeral; providers were not contacted.

For this phase, **`aof-load-truncated=no`** was explicitly selected rather than Phase 2H's inherited `yes`. The corrupt-AOF test verifies refusal; it does not repair or silently truncate history. Other source authority and publication semantics were preserved.

The primary Redis process was killed with Docker `KILL`/SIGKILL; exit code **137** and non-running state were verified before each recovery. This bypasses Redis graceful shutdown. Restart uses the same owned container/volume. It is a real process-crash test, **not** a host power-loss, kernel, controller or physical-storage fault. The AOF snapshot was taken while the orchestrator was the sole writer with a small non-rewriting dataset; all manifest/base/incremental files were copied together into a separate disposable container.

The TLS replica was actually synchronized, paused, and its replication stream explicitly cut **before** the revocation it must miss. The primary acknowledged revocation, was killed, and the stale replica was resumed/promoted using operator control. It contained the old live ciphertext. The application still used current LMDB metadata. This is a controlled manual promotion, not Sentinel/provider election or automatic endpoint routing qualification.

## Exact scenarios and security outcomes

| Scenario | Result | Acknowledged revocation / authority outcome |
| --- | --- | --- |
| SIGKILL after acknowledged User/Admin credential creation | **PASS** | Both records retain exact ciphertext/revision/expiry and validate after recovery. Redis-down requests deny authority. |
| SIGKILL after acknowledged refresh replacement | **PASS** | Updated generation 1 remains current; no return to the prior credential revision. No real Supabase refresh was issued. |
| SIGKILL after browser/login rotation using actual `begin_login`/`finish_login` | **PASS** | New credentials/browser remain valid; old credential/browser parents stay invalid; consumed User CSRF challenge cannot return. Admin stays separate. |
| SIGKILL after acknowledged revocation | **PASS** | Revoked credential stays invalid. Replaying its valid encrypted bytes after recovery cannot supply missing authority metadata. |
| Kill after independent authority prepare, before Redis publication | **PASS — fail closed** | Client receives uncertain failure; prepared metadata exists but Redis key is physically absent. Validation raises `RevisionConflict`. No old authority is substituted. This write was not acknowledged as successful. |
| Two spawned reader workers after recovery | **PASS** | 120 User/Admin reads retain A/B identities and reject opposite-realm handles. These are actual storage worker processes, not a target WSGI deployment. |
| Unpromoted replica queried as authority writer | **PASS** | Role validation rejects the replica before promotion. |
| Actual stale TLS replica promotion after missed acknowledged revocation | **PASS with current metadata** | Old ciphertext is physically present but metadata is absent; validation remains `INVALID`. Promotion does not recreate authority. |
| Restore old complete Redis AOF dataset, retain current metadata | **PASS** | Physically restored revoked record remains invalid. This loads old AOF files, not just a mocked read or manually replayed key. |
| Older local LMDB snapshot, current Redis with deleted victim key | **PASS for this case** | Old metadata cannot validate a physically missing key; typed failure. This does not establish authority rollback safety; see the next two FAILs. |
| Restore both old AOF dataset and old local LMDB | **FAIL** | **An acknowledged revocation is undone. Fresh reader accepts the revoked credential.** Current runtime has no independently protected freshness anchor. |
| Roll back local authority only, with ciphertext left after failed cache deletion | **FAIL** | **An acknowledged revocation is undone without restoring/replaying Redis at all.** A simulated cache `DEL` connection failure leaves encrypted bytes; current metadata denies them, but the old LMDB snapshot grants authority again. |
| Invalid JSON in a private authority copy | **PASS — fail closed** | A valid Redis credential is denied with `SessionStorageUnavailable`. No positive fallback. |
| Physically invalid LMDB file in a private copy | **PASS — startup refuses** | LMDB open raises its corruption/error class; no authority service is recreated. This does not cover every possible corruption or malicious valid replacement. |
| Injected unavailable local authority API | **PASS — fail closed** | Otherwise intact Redis credentials are denied. Local LMDB has no separately hosted service to take offline; this is explicitly an API fault injection. |
| Actual experimental witness process outage | **PASS — fail closed** | Witness-dependent adapter denies authority. Restart of the intact witness journal continues to deny the revoked/rolled-back state. |
| Old Redis + local LMDB with a current third witness | **PASS in experiment** | Current witness metadata detects the mismatch and denies both-store rollback. Not linked to runtime startup. |
| Roll back Redis, local LMDB and same-host witness journal together | **FAIL** | **An acknowledged revocation is undone.** A valid older journal prefix passes its hash-chain check. The test witness is not a protected anchor. |
| Real paused Redis socket timeout and reconnect | **PASS** | Bounded timeout denies authority; same preserved session works after unpause. No cookie or memory fallback. |
| Real 2.1-second delayed snapshot | **PASS** | Commit rejected with `RevisionConflict` after the existing freshness budget. |
| Real maxmemory pressure | **PASS** | New-session admission denies allocation; revocation remains possible through independent metadata. After SIGKILL/recovery the OOM-time revocation remains invalid. |
| Copied AOF with incomplete appended RESP command, strict policy | **PASS — startup refuses** | Redis exits nonzero rather than silently trimming/replaying uncertain history. No repair command was run. |
| Production mode activation attempt | **PASS — refuses** | Existing unconditional startup safeguard remains unchanged. |

Recorded observations distinguish `physical_exists`/PTTL/ciphertext digest from `authority_present`/revision digest/expiry and the validation result. `INVALID` means no current authority; `RevisionConflict` means an unusable or inconsistent revision. An availability error is not proof that Redis physically lost a record. The stale-promotion evidence, for example, explicitly records **physical existence=true, authority=false, validation=INVALID**.

## Can revoked authority ever be restored?

**Yes.** The three FAIL rows demonstrate it with the existing local architecture. Rejection after Redis-only recovery depends on retaining trustworthy, current authority state. The authority-only leftover-cache counterexample is particularly important: successful physical cache deletion cannot be assumed, and durable revocation must not depend on it. The runtime intentionally allows acknowledged metadata revocation even when cache cleanup fails; that is safe only while the authoritative deletion cannot be rolled back.

The Phase 2G mTLS witness proves a conditional protocol property: **if it remains current**, it blocks simultaneous rollback of Redis and local metadata. It does not prove independently protected storage. It shares the host/user/failure domain, stores a local journal, and is not used by the application factory. This phase actually restored its earlier valid journal and observed resurrection. A hash chain or `fsync` acknowledgment does not establish freshness after valid-prefix restoration.

No external consensus service, immutable freshness anchor, independent operator/IAM boundary or multi-host quorum was provisioned or qualified. No claim of durable production revocation is justified. Redis documents that asynchronous replication and even `WAIT` do not make failover strongly consistent. [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).

Browser-session revocation also does not globally invalidate an already issued Supabase JWT, undo a provider action, or recall an already dispatched database mutation. Those separate provider/in-flight boundaries were not changed or claimed as qualified.

## Measurements and preservation

Controller-observed recovery starts at `docker start` and ends at verified TLS PING, followed by record validation. It excludes the time before recovery was initiated, detection/election, protected-control-plane recovery and target load-balancer acceptance. These are measurements of this small Docker Desktop fixture, not production RTOs.

| Crash point | Recovery seconds | Record outcome |
| --- | ---: | --- |
| Acknowledged creation | 0.5616 | Both live credentials preserved |
| Acknowledged refresh | 0.5508 | Both live credentials preserved; User generation 1 |
| Acknowledged rotation | 0.5378 | Five checked old/new credential/browser/Admin states preserved |
| Acknowledged revocation | 0.5212 | Three checked live/revoked states preserved |
| Authority prepare before publication | 1.0513 | Prepared web key absent; denied |
| Revocation under OOM | 0.6263 | Revoked record remains invalid |

Across the five acknowledged-transition crash rounds, **13/13 checked state observations** retained their ciphertext/revision/expiry and validity outcomes (including intentionally invalid old/revoked states). The prepare-before-publication round separately measured one denied partial record. The harness does not claim every key in Redis was checkpointed or that all crash timings were explored.

The stale promotion command plus validation took **0.0094 seconds** after explicit stream isolation/resume; this is not failover detection time. The paused Redis lookup/unpause path took **1.1724 seconds** with one-second application socket timeouts. Two reader processes completed 120 reads in **3.5308 seconds including process spawn/imports**. A separate 4-thread batch completed 100/100 TLS credential reads in **0.3700 seconds (~270.27 operations/s)** with **zero MSET calls**. This excludes network-witness/quorum costs, provider requests and production load. Activity writes, peak memory, disk-full/power-loss latency, connection storms and sustained percentile SLOs were not measured here.

Fail-closed loss and resurrection are different: an unavailable acknowledged session would preserve the no-resurrection security property but fail continuity/availability acceptance. No acknowledged live-record loss was observed in the checked crash cases. The intentionally unacknowledged partial record was denied, not silently converted into successful login.

## Regression and integrity results

| Suite | Final result | Evidence |
| --- | --- | --- |
| Isolated destructive qualification | **46 positive checks PASS; 3 security findings FAIL** | [qualification-results.json](qualification-results.json) |
| Existing real-Redis session/readiness suite | **67 functions + 21 subtests PASS** | [focused-output.txt](focused-output.txt), [focused-test-results.xml](focused-test-results.xml) |
| Complete Python `tests/` suite | **1,095 functions + 1,392 subtests PASS; 63 opt-in Redis cases skipped** | [python-output.txt](python-output.txt), [full-test-results.xml](full-test-results.xml) |
| JavaScript | **68 PASS, 0 FAIL** | [javascript-output.txt](javascript-output.txt) |
| Reviewed source / SQL bytes | **14/14 source and 3/3 SQL fingerprints unchanged** | [verification-summary.json](verification-summary.json) |

The 63 opt-in cases were run in the focused suite, with four offline readiness functions and 21 subtests. Counts overlap; do not add them as unique tests. The focused suite used a separate owned loopback plaintext fixture required by the current local factory; destructive crash/replication tests used TLS. Real Supabase sessions, real database-backed membership changes, actual audit insertion and production records were not exercised. Existing focused tests cover synthetic fresh membership denial, B's scoped request credentials, CSRF/recovery isolation, independent logout and stale-response handling. Unchanged business/SQL source fingerprints and full regressions preserve the local destination/Environment/photo/audit contract evidence. They do not certify live production row counts or actual audit writes. Chromium/mobile and actual target WSGI/HTTPS acceptance were not rerun here.

Two early fixture attempts did not qualify stale promotion: one operator TLS promotion timed out after unpause, and a later attempt allowed buffered replication to deliver the deletion, so the promoted record was not actually stale. The final setup explicitly severs the stream before revocation and verifies a physically present stale key afterward. Operator connections are refreshed after unpause; an uncertain promotion acknowledgment is reconciled by ROLE without blindly repeating the control command. The final run received a direct acknowledgment. Application timeouts and authority rules were not relaxed. The final 46 checks/three security findings are from the final corrected setup, not the aborted attempts.

## Required production architecture and recovery contract

Before any production release, replace the local metadata authority with a separately reviewed, independently administered transactional/consensus service. Its guarantees must be specified against an explicit fault model: acknowledged deletion/refresh fencing, linearizable conditional reads/writes, quorum loss, writer promotion, partitions, damaged storage and old backups. Per-realm workload mTLS/RBAC must not permit operator generation changes or snapshot restoration.

That service also needs a **restore-safe freshness anchor outside the Redis/authority snapshot domain**. A consensus cluster alone can still be rolled back if all members and bootstrapping control state are restored together. Require never-reused epochs/generations, independent operator controls, audited recovery approval, and a mechanism that prevents both existing and newly booted workers from accepting an old descriptor. A post-promotion notification, Redis `WAIT`, local file, matching old ciphertext/digest or reversible journal serial is insufficient. If the provider cannot enforce this, do not transparently reopen authentication after uncertain recovery.

The operating process must block authority dispatch before potentially stale promotion, fence old workers, drain/reconcile uncertain provider/database requests, establish a current protected generation and known writer, advance affected realm epochs when freshness is uncertain, and require deliberate User/Admin sign-in plus recovery/verification restart. Do not restore old handles or rewind authority to repair missing Redis records. If the independent anchor is unavailable or its freshness cannot be established, remain closed. Keep a qualified maintenance/rollback path; never switch production to development/memory mode or legacy shared-cookie Admin authority.

Qualify provider-equivalent crash/host/volume faults, retained multipart AOF artifacts, truncation refusal/recovery policy, TLS/ACL/operator separation, key-manager access/rotation, worker pool lifecycle, clock bounds, capacity/monitoring/alerts, cold-worker and rollback release behavior. No hosting/provider guarantees can be inferred from Docker SIGKILL. Redis describes the differences between AOF policies and recovery modes in its [persistence documentation](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).

## Eight production readiness gates

| Gate | Updated production status |
| --- | --- |
| G04 — HTTPS/hosts/proxy | **FAIL** — target topology/browser/private ingress qualification still absent; this phase adds no production hosting approval. |
| G06 — secret/key lifecycle | **FAIL** — independently protected secret delivery, IAM/KMS, fleet rotation/retirement and compromise recovery remain unqualified. |
| G12 — startup/readiness | **FAIL** — safeguard retained; production factory/external authority and restore-safe pre-use gate remain unimplemented. |
| G13 — multiworker/restart | **FAIL** — local SIGKILL and reader-process results improve evidence; target WSGI, rolling lifecycle and complete recovery acceptance remain outstanding. |
| G14 — durable revocation | **FAIL, demonstrated** — authority-only leftover-cache rollback, joint two-store rollback and all-three witness rollback restore revoked authority. |
| G17 — Redis operations | **FAIL** — fixed-image local AOF/SIGKILL/TLS replica/strict truncation cases pass; provider failover/volume guarantees, operator separation, alerts and capacity remain unqualified. |
| G18 — clock/resource bounds | **FAIL** — local timeout/OOM/delay cases pass; host clocks, watchdog/fsync bounds, disk/resource faults and sustained SLOs remain outstanding. |
| G20 — cutover/rollback | **FAIL** — no qualified target release/rollback or independently protected authority restore rehearsal. |

The previous 12 source/local PASS gates retain their limited scope. **All eight production gates remain FAIL.** The appropriate next phase is approved isolated authority architecture/remediation and fault qualification. Do not proceed to production provisioning or deployment based on this report.

## Files and cleanup

Only `docs/admin-finalization/phase2i-crash-failover/` was added: `lab.py`, `qualify.py`, `verify_evidence.py`, `REPORT.md`, `qualification-results.json`, `checkpoint-results.json`, `verification-summary.json`, focused/full Python XML and output, and `javascript-output.txt`. Generated bytecode is not a deliverable. The lab imports the unchanged ephemeral PKI and experimental witness helpers from Phase 2G and the pinned image descriptor from Phase 2H; their hashes are captured in the verification summary.

Owned containers/anonymous volumes and the labelled test network were removed using ID/label/loopback checks. Temporary synthetic secrets, AOF copies, authority copies and witness journals were removed with their owned temporary directory. No raw credentials or private keys are in archived evidence. The already downloaded Redis image remains cached locally. Stop after this review, pending explicit approval.
