# Phase 2G — isolated infrastructure and security qualification

**NO-GO for production infrastructure activation or deployment.** All eight outstanding production readiness gates remain FAIL. The isolated work adds useful security evidence, but does not qualify independently protected authority storage, the production hosting/secret configuration, or restart persistence. GO only for a separately approved isolated remediation and target-infrastructure qualification phase.

The application and dependency files are unchanged from Phase 2F. Only this qualification directory was added. No production Redis, authority, Supabase service, database, authentication setting, destination, Storage object or feature flag was accessed or changed. No SQL was executed. Nothing was staged, committed, pushed or deployed. The production startup safeguard still rejects production mode.

## Results and scope

- **59 isolated safety assertions PASS; one operational finding FAIL.** See [qualification-results.json](qualification-results.json), [restart-diagnostic.json](restart-diagnostic.json) and [lab-output.txt](lab-output.txt).
- Fresh complete Python regression: **1,095 functions and 1,392 subtests passed; 63 opt-in Redis cases skipped**, in 80.12 seconds. See [full-test-results.xml](full-test-results.xml) and [python-output.txt](python-output.txt). The 59 standalone qualification assertions are separate from pytest.
- Phase 2F's 67 focused functions plus 21 subtests, 68 JavaScript tests and 24 Chromium checks remain **prior evidence**, not reruns in Phase 2G. This phase's HTTPS client is HTTPX with CA verification, not Chromium. There was no production browser or actual provider acceptance test.
- Two actual Flask worker processes, PIDs 27656 and 23040, served through a real local HTTPS reverse proxy. Saved worker fingerprints match the reviewed source. Providers, Admin membership and business clients were synthetic. Workers rejected connections outside the loopback Redis test endpoint.
- All 14 Phase 2F source fingerprints and all three saved SQL byte fingerprints are rechecked by [verify_evidence.py](verify_evidence.py); results are in [verification-summary.json](verification-summary.json). These prove local source preservation, not live database record counts.
- The owned disposable container and five listeners were absent after cleanup. Private certificates, passwords, keyrings and witness journals were generated temporarily; no CA was installed in the OS/browser trust store. No generated secrets are archived here.

The lab ran Redis 7.4.7 on Docker Desktop, TLS-only on numeric loopback, with an ephemeral private CA and mutual TLS. The TLS proxy and workers were laboratory Python/Werkzeug servers, not a qualified production WSGI installation. TLS clients verified both CA and hostname; verification was never disabled.

## Eight remaining production gates

These are the same gate IDs as the [Phase 2E review](../phase2e-security-readiness/REVIEW.md). A local component PASS does not close a production deployment gate. The other 12 gates retain their Phase 2F source/local scope; no broader production certification is implied.

| Gate | Result | New isolated evidence | Exact evidence still required to close |
| --- | --- | --- | --- |
| G04 — HTTPS, hosts, proxy | **FAIL** | Verified HTTPS, untrusted Host rejection, sanitized forwarded headers, two workers, Secure/HttpOnly/Lax host-only cookies with User `/` and Admin `/admin`. | Reviewed real domain/certificate lifecycle, actual proxy-hop count and header sanitization, private/direct worker reachability controls, canonical origin and root routing. Repeat browser/mobile, Host/Origin and spoofing tests on that topology. |
| G06 — key lifecycle/secrets | **FAIL** | Current `k1` reader upgraded to `k1+k2` with `k2` writes; new ciphertext works; old-key-only reader denies it; predecessor ciphertext remains readable. | Approved secret manager/KMS, workload/operator IAM separation, audited access, backup/recovery, staged fleet rotation, retirement covering every state family and backup, and compromise rehearsal. |
| G12 — startup/readiness enforcement | **FAIL** | Local readiness is explicitly not production approval; blocked authority denies requests/readiness; production startup still raises. | Implement and review the production factory/entrypoint and independent authority integration behind the retained release safeguard. Prove missing/wrong mode, TLS/ACL/keyring/descriptor/proxy failures stop all workers; distinguish liveness from authority readiness; remove app-side configuration inspection. |
| G13 — multiworker hosting/restart | **FAIL** | Two actual worker processes preserve A/B identity and deny blocked generations. **AOF restart availability failed.** | Resolve the restart finding below, then repeat intact cache/authority and worker restarts with unchanged deadlines and all state families, actual WSGI fork/pool lifecycle, rolling compatibility and delayed responses. |
| G14 — durable revocation/failover | **FAIL** | Experimental mTLS witness rejects old Redis plus an older local LMDB snapshot, witness outage and stale worker generations. | Runtime integration with independently administered/protected storage and a non-restored freshness anchor. Qualify quorum loss, promotion, backup restoration and attempted correlated rollback, including old workers and in-flight operations. The same-host experiment is insufficient. |
| G17 — Redis operations | **FAIL** | TLS/mTLS, realm ACLs including nested Lua, noeviction, limits, real OOM/eviction/connection exhaustion and monitoring samples tested. | Resolve restart loss; qualify the selected provider/version, least-privilege app/operator separation without the lab `CONFIG GET` concession, durable-volume recovery/failover procedure, patching, capacity headroom and actual alert delivery/on-call response. |
| G18 — clock/resource bounds | **FAIL** | A +10-second worker-clock fault, 3-second-old snapshot, exhausted pool, server connection cap and memory-pressure denial tested. | Target-host NTP/regression and suspend/resume bounds, absolute request/watchdog deadlines including authority fsync, peak RSS/CPU/persistence costs, sustained percentile latency/error SLOs and independent-authority load. A single injected offset is not full clock qualification. |
| G20 — cutover/rollback rehearsal | **FAIL** | Witness BLOCKED → QUALIFYING → OPEN, new epochs, old-worker denial and mandatory fresh sign-in demonstrated. Proposed procedures in [OPERATIONS.md](OPERATIONS.md). | A qualified release/rollback pair on the actual isolated target platform, all-worker drain/fence, authority and secret recovery, genuine browser/recovery acceptance and approved operator exercise. Production business-write acceptance remains separately authorized. |

## Protected revision authority: evaluated architecture and demonstrated limits

The current runtime still uses **local LMDB authority**, separate from Redis but on one host. It is not a multi-host protected authority service. Restoring both metadata and encrypted Redis data can revive old authority under the same descriptor; Phase 2F already documented this blocker.

The recommended next candidate is a small transactional/consensus metadata service in an independently administered failure and recovery domain. Require linearizable conditional metadata commits, primary/quorum reads, per-realm workload identities, operator-only generation control, and bounded request/commit deadlines. Keep digests, revisions, expiry, quota/control metadata there; encrypted credentials remain in Redis. Never use a Redis replica, Redis `WAIT`, or a journal stored in the same backup as the sole freshness authority. Redis explicitly documents that replication acknowledgments do not make failover strongly consistent. [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).

A separately operated consensus service is a candidate, **not a selected or qualified product**. Consensus protects particular live failures; it does not prove freshness after all members are restored from an older snapshot. Require an independently protected, never-reused generation/epoch anchor, restore procedures that cannot reopen an old generation, and separation between application, snapshot-restoration and gate-opening permissions. A proposed implementation must specify how a new/restarted worker validates freshness without trusting a rolled-back bootstrap descriptor. Etcd's recovery and TLS/RBAC guidance are relevant inputs, not proof that this application is qualified. [Etcd recovery](https://etcd.io/docs/v3.6/op-guide/recovery/), [Etcd security](https://etcd.io/docs/v3.6/op-guide/security/).

`witness_lab.py` is an **experiment only**, never imported by application startup. It runs in a separate process with a separately persisted hash-chained journal, fsync before acknowledgment and mTLS roles. App identities can conditionally change their realm's metadata, but cannot change operator control. An expected serial rejects stale operator updates. The adapter commits witness metadata before local LMDB metadata and then publishes to Redis through the existing runtime. A later failure never compensates by restoring the old witness revision; mismatches deny authority.

Demonstrated: acknowledged revoke; replay of valid old ciphertext; simultaneous restoration of old local metadata and old ciphertext in a new reader; local-authority outage; actual witness process outage/restart; operator BLOCKED/QUALIFYING denial; rejected stale operator serial; fresh epochs and credentials; old-worker denial. None silently restored revoked authority in these tests.

**Not demonstrated:** protected cross-host storage, immutable freshness anchor, application-host compromise resistance, rollback of the witness itself, consensus partitions/leader changes, secure operator disaster recovery or bounded production load. The journal and leaf private keys share the same host/user as the application test; a hash chain detects modification/incomplete entries but not replacement with a valid older prefix. Operator serial CAS is not an external anti-rollback anchor. The witness has no production quota/cleanup service, full control-descriptor validation or hardened deployment API. It must not be copied into production. There is no claim of durable production revocation.

Fail-closed recovery must close dispatch before using an uncertain writer, fence old workers, establish a new independent control generation and never-reused realm epochs, and require new login/recovery/verification flows. Never import old handles or rewind the witness to match Redis. Already dispatched provider/database operations cannot be recalled; reconcile uncertain results instead of automatically repeating them. Details and acceptance evidence requirements are in [OPERATIONS.md](OPERATIONS.md).

## Fault results and restart failure

| Test family | Isolated result | Limit |
| --- | --- | --- |
| CA/hostname/mTLS, no plaintext listener | PASS | Ephemeral local CA; actual provider CA/certificate rotation not tested. |
| Realm ACL direct read and nested Lua, config writes/flush/ACL admin denial | PASS | App `CONFIG GET` remains an explicit readiness concession; not final least privilege. |
| Witness rollback mismatch, outage and controlled recovery | PASS | Only Redis/local LMDB rollback with a current witness; not correlated witness rollback. |
| HTTPS A/B identity, User logout preserving B, cross-CSRF, generation gate | PASS | Synthetic providers; reverse login/logout and recovery browser regressions are prior Phase 2F evidence. |
| Redis client-pool exhaustion and real maxclients rejection | PASS | Not a production sustained connection/handshake flood. |
| Real OOM and admission denial, independent revoke during OOM | PASS | Disposable operator changed limits; never production. |
| Real eviction followed by authority denial | PASS | Operator reset stats only for subsequent lab cleanup; resetting evidence is not a production recovery policy. |
| +10-second clock discrepancy and delayed snapshot | PASS | Partial fault coverage; material negative/server clock steps and fleet time qualification remain. |
| Intact Redis AOF restart/session availability | **FAIL** | Missing unexpired cache record; authority denied. Root cause unresolved. |

The last restart diagnostic records the target record present with TTL **1,797,433 ms** before restart and absent afterward (`PTTL=-2`), while independent metadata had approximately **1,795,782 ms** remaining. Database key count changed from **1,359 to 1**. AOF was enabled, `appendfsync=always`, and its reported last write status was `ok`. That configuration and metric do not override the observed failure. This occurred before deliberately inducing OOM/eviction. The finding appeared on repeated lab attempts; do not substitute the earlier Phase 2F intact-restart PASS for this result.

The existing runtime correctly rejected the metadata/cache mismatch. Fresh synthetic authentication could subsequently be established, but this is not intact-session preservation. A minimal reproduction must retain and inspect the disposable AOF/manifest, Redis load logs, timestamp/expiry encoding and volume lifecycle, then repeat on the selected supported server/client versions. **The cause is not established; no Redis defect or fix is claimed.**

Earlier attempts exposed strict certificate extension requirements and a flawed pool-exhaustion fixture. The ephemeral PKI now supplies SKI/AKI and key constraints; the pool test holds every slot rather than lowering a limit with idle sockets remaining. One earlier readiness probe returned 503 without an isolated cause; the final run passed that probe, but target readiness availability still needs sustained qualification. `lab-output.txt` includes normal Werkzeug stderr; Windows PowerShell marked that native stderr stream as an error, although the runner reached its final 59-assertion JSON and cleanup. The operational FAIL is preserved independently of that shell artifact.

## Capacity, retention and write measurements

Measured over TLS against the local service with 4 threads; these are microbenchmarks, not HTTP throughput or production capacity promises. The load used **local LMDB**, not the network witness; witness/quorum cost is not included.

| Metric | Measurement |
| --- | ---: |
| Credential/browser pairs | 500 |
| Additional iterations across login challenges, rate counters, recovery and email families | 50 |
| Independently expiring Redis records at measurement | 1,350 |
| Sum of Redis `MEMORY USAGE` for those records | 2,090,736 bytes (~1.99 MiB) |
| Local authority data-file size | 67,108,864 bytes (64 MiB; not RSS) |
| Token fixture | 1,500-character access token; 64-character refresh token |
| 200 credential reads | 200 successful / 0.5843 s / **342.28 operations/s** |
| Read writes | **0 MSET, 0 PEXPIREAT** |
| 200 authorized activity updates | 200 successful / 2.5054 s / **79.83 operations/s** |
| Activity writes | **0 MSET, 200 PEXPIREAT** |

Reads transferred 61,822 input / 946,839 output bytes; activity updates 102,258 input / 1,309,266 output bytes, including measured Redis protocol traffic. Activity still updates authoritative metadata durably; zero encrypted payload replacements is not zero total writes. No sustained-load percentiles, creation/refresh peak, full HTTP request mix, witness throughput, peak RSS, AOF growth/rewrite/replication cost or recovery-storm sizing is established. Do not extrapolate these rates to a production plan or compare directly with Phase 2F's different plaintext workload.

Each state family retains its Phase 2F logical deadlines and independent Redis key expiry. Credential idle expiry is 1,800 seconds bounded by 28,800 seconds absolute; authenticated browser lifetime cannot extend credential authority. Challenges, grants, verification/cooldown and rate records are separate, so an unrelated request does not rewrite or extend their payloads. Existing Phase 2F TTL tests remain prior evidence; G's workload and activity command counts verify the TLS path without re-running every expiry case. Production retention must include authority tombstones/receipts, journals, backups, logs and key retirement, not just Redis TTL.

The lab used **64 MiB maxmemory, noeviction, maxclients 64**, 16-slot client pools with one-second socket/connect timeouts, and fsync-always AOF. These are isolated limits, not approved production values. Existing default authority admission is 4,096 records/32 MiB accounted data per realm; transaction groups are bounded to eight keys. Startup must require an explicit workload budget rather than assuming enough RAM defeats those caps. Sum every worker's per-realm pools plus operator/readiness connections and reserve headroom; the lab's intentionally low cap is unsuitable for an unspecified worker count. `maxmemory` does not cap process RSS, persistence buffers or replication overhead. The monitoring sample was taken after destructive fault tests, so its 672,792-byte used-memory value is **not** the workload memory measurement.

## HTTPS and key-management qualification

The HTTPS jar received `__Host-rosago_user_session` at `/` and `__Secure-rosago_admin_session` at `/admin`, both Secure, HttpOnly, Lax and without Domain. Root-mounted routing remained active. The proxy rejected unknown Host and stripped/replaced supplied forwarding headers. User A stayed A while Admin routes used B, and CSRF tokens failed across realms. The root User cookie may travel to Admin paths; server-side realm selection supplies isolation. Cookie Path is not a security boundary against same-origin script or process compromise. Flask requires exact trust configuration for forwarded headers. [Flask ProxyFix](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/).

TLS Redis required both a certificate and per-role password. Wrong hostname, plaintext and missing certificate were denied. Redis TLS and ACLs are separate controls; the actual deployment must qualify both. [Redis TLS](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/), [Redis ACLs](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/).

Generated AES keys stayed in test process configuration, not source or archived output. The local experiment's unencrypted leaf-key files in a disposable directory do not qualify a production secret store. A real release requires workload-scoped secret delivery, protected CA/KMS/operator access, no app permission to restore authority snapshots/open generations, secret-redacted diagnostics and audited emergency access. Add the new decrypt key to every reader first, switch writers only after fleet compatibility, explicitly migrate or expire **all** records before retiring the old key, and prove backup/recovery compatibility. Ordinary reads/TTL activity do not reencrypt old payloads. Compromise requires gate closure, new epochs/key material and deliberate reauthentication, not an optimistic seamless key switch.

## Files and next decision

New executable lab files: `lab_support.py`, `witness_lab.py`, `https_lab.py`, `run_qualification.py`, and offline `verify_evidence.py`. New review artifacts: this report, `OPERATIONS.md`, `qualification-results.json`, `checkpoint-results.json`, `restart-diagnostic.json`, `verification-summary.json`, `full-test-results.xml`, `python-output.txt`, `lab-output.txt`, and redacted `startup-diagnostic.txt`. Generated bytecode is not a deliverable. All are confined to this directory; no runtime source, dependency, SQL or deployment file was changed.

The next proposed isolated scope is: investigate and fix/requalify restart persistence; select and integrate independently protected authority with a restore-safe freshness anchor; remove app management-command concessions; qualify actual hosting, secrets and sustained resource bounds; then rehearse cutover/rollback. Those require a new approval. **Production remains NO-GO; stop here pending approval.**
