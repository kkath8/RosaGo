# Phase 2H — Redis restart persistence investigation

**PASS for the isolated clean-restart correction. GO for further isolated qualification after approval; NO-GO for production provisioning, activation or deployment.** The previously unexplained Phase 2G loss is reproduced and its cause confirmed. No RosaGo runtime correction was necessary. The narrow infrastructure correction is a digest-pinned Redis version containing the upstream AOF replay fix, with the same restrictive ACLs, TLS and authority checks.

## Confirmed root cause

Redis **7.4.7 incorrectly rechecks ACL permissions during internal AOF `EXEC` replay**. The Phase 2G profile disables the default Redis user and supplies separate named operator/User/Admin identities. The internal replay client's transaction checks encounter the default user's lack of permissions. Historical writes that succeeded under the named application identity are present in AOF but their transaction effects are not restored. A nontransactional control write survives.

The isolated reproduction uses the actual unchanged `RedisRealm`/`RedisModel`, plus direct Redis controls, with no Flask worker or cleanup task running during restart. The incremental AOF contains `MULTI`, `MSET`, `PEXPIREAT` and `EXEC`; the separate explicit transaction control also disappears. Redis reports **five AOF-loading ACL errors** after a clean shutdown and successful incremental-file load. There is no `DEL`/`FLUSH` in the captured incremental command counts. The same authority digest, generation and future expiry remain after restart. This is **physical Redis record loss during replay**, not expiration or a present record rejected by the authority barrier.

The behavior matches Redis's acknowledged [issue #14541](https://github.com/redis/redis/issues/14541) and [upstream fix #14545](https://github.com/redis/redis/pull/14545). The [8.4 release notes](https://raw.githubusercontent.com/redis/redis/8.4/00-RELEASENOTES) identify that fix in 8.4.4. We tested 8.4.8; we do not infer that every other release/provider build contains the fix. The [7.4.7 transaction implementation](https://raw.githubusercontent.com/redis/redis/7.4.7/src/multi.c) and [8.4.8 implementation](https://raw.githubusercontent.com/redis/redis/8.4.8/src/multi.c) support the diagnosis.

This was not an LMDB rollback, admission eviction, application cleanup, elapsed 30-minute TTL, missing AOF configuration, or a replacement of the container/volume. The minimal test cleanly restarts the same owned container before any destructive fault injection. Both versions have AOF enabled, fsync-always, the same `/data`/append directory, default RDB-preamble setting, noeviction and TLS-only access. The old replay error can occur even while persistence reports last-write status `ok`; that status proves neither successful replay nor session validity.

## Minimal correction

[qualified-redis.json](qualified-redis.json) pins the isolated candidate to:

`redis:8.4.8@sha256:6805005a84497806df31105912c91415afe473da3c3d6732e74d112ec49254ac`

The final qualification explicitly checks the running version and uses this digest-pinned image. We did not grant permissions to the disabled default user, enable plaintext access, weaken realm ACLs, change publication/expiry logic, bypass validation, or turn off the production safeguard. Default ACL flags/command/key permissions are compared with the affected baseline; User access to Admin keys remains denied. The default user's parsed command/key permission lists are empty in both versions.

This is an **isolated infrastructure profile**, not a production deployment or a new production backend. Existing historical Phase 2F/2G helpers and reports are preserved; their 7.4.7 results remain historical evidence. Do not reuse their affected image profile for future persistence qualification. A real release must separately approve the server/provider build, major-version compatibility, patch maintenance and operational requirements. The application continues to refuse production activation.

## Before/after evidence

Evidence contains key-existence booleans, PTTL, ciphertext SHA-256, revision digest/generation/expiry, persistence status, AOF manifest/size/hash/command counts and validation categories. It contains no raw cookie, bearer/refresh token, ciphertext payload, password, keyring or private key. Raw AOF and arbitrary server logs were inspected in memory inside the isolated test and were not archived. Temporary containers/volumes and temporary PKI/LMDB directories were removed afterward.

| Observation | Affected 7.4.7 | Corrected digest-pinned 8.4.8 |
| --- | --- | --- |
| Session exists before restart | Yes | Yes |
| PTTL before restart | 1,799,960 ms | 1,799,955 ms |
| Session exists after restart | **No** | **Yes** |
| PTTL after restart | **-2 (missing)** | **1,798,517 ms** |
| Physical ciphertext digest | Missing after restart | Identical before/after |
| Authority revision digest/generation/expiry | Unchanged, unexpired | Unchanged, unexpired |
| Validation after restart | `RevisionConflict`, fail closed | `VALID` |
| Direct nontransactional control survives | Yes | Yes |
| Explicit transactional control survives | **No** | **Yes** |
| AOF-loading ACL errors | **5** | **0** |

See [baseline.json](baseline.json), [qualified-comparison.json](qualified-comparison.json) and the initial tag-only [fixed-comparison.json](fixed-comparison.json). Ciphertexts differ between independent fixture runs because keys/nonces are random; the relevant equality is within each before/after pair. Credential generation 0 and revision digest/expiry are recorded without exposing record references; the authority descriptor is unchanged. Physically missing keys are queried through the independent operator client, not inferred from an application 503.

The final pinned run includes one minimal comparison restart and **three additional clean restarts** with both realms, all nine record families and actual concurrent worker processes. The 18 family records remain physically present and valid with identical ciphertext/revision digests and expiry timestamps, while PTTL decreases instead of being reset. Families are credentials, browser state, login/CSRF challenges, pending recovery, recovery grants, recovery replay markers, email verification, email cooldowns and rate limits.

Expiry is tested by shortening actual record deadlines and allowing real time to pass, without patching clocks. Expired records remain physically absent and invalid. Revoked encrypted records are deliberately replayed as physically present cache entries; the unchanged authority still rejects them through every restart. An older ciphertext under a currently live handle produces `RevisionConflict` while the current exact ciphertext validates. Those are intentionally different from the baseline's physically missing key.

## Test results

| Suite | Final result | Evidence |
| --- | --- | --- |
| Restart/replay/concurrent-process qualification | **51 checks PASS** | [qualification-results.json](qualification-results.json) |
| Existing focused real-Redis session/readiness tests | **67 functions + 21 subtests PASS** | [focused-output.txt](focused-output.txt), [focused-test-results.xml](focused-test-results.xml) |
| Complete Python `tests/` regression suite | **1,095 functions + 1,392 subtests PASS; 63 opt-in Redis cases skipped** | [python-output.txt](python-output.txt), [full-test-results.xml](full-test-results.xml) |
| JavaScript regression suite | **68 PASS, 0 FAIL** | [javascript-output.txt](javascript-output.txt) |
| Source/SQL preservation, test evidence | **PASS** | [verification-summary.json](verification-summary.json) |

The 63 opt-in cases skipped by the full suite were run in the focused suite, together with the four offline readiness tests and 21 subtests; these counts overlap and must not be summed as unique tests. The focused suite ran against a separate owned loopback-only plaintext Redis 8.4.8 fixture required by the existing local factory. The new restart qualification used TLS/mTLS and realm ACLs. Neither fixture was production infrastructure.

Two separate spawned processes concurrently read both User/Admin credentials after each of the three restart rounds, with opposite-realm handles rejected. A further pair competes for refresh: exactly one reservation owner succeeds. After revocation and deliberate old-ciphertext replay, fresh reader processes reject both realms. The existing focused suite also repeats cross-worker refresh, stale-response/login/logout, expiration, recovery, authorization/CSRF and synthetic Admin actor checks. This phase does not repeat the Phase 2F Chromium/mobile checks or an actual production provider/audit write; no UI or runtime code changed.

Three test-launch/fixture problems were corrected before final results: the initial default-ACL assertion expected a string whereas redis-py returns parsed permission lists; comparison now uses the captured baseline fields. Unscoped pytest discovery encountered a historical offline report script and stopped before running tests; the final full command explicitly targets `tests/`. That script made no network/SQL calls, and Git reports no content change to its existing report directory. The initial Node run was blocked by sandbox child-process permissions (`EPERM`); rerunning the same local tests with process permissions passed. These are not suppressed product failures. No final test failure remains in this scope.

## What persistence qualification proves

The fixed image correctly replays acknowledged, unexpired records on **clean restarts of this same isolated container and intact volume**, with preserved metadata, keyring and epochs. It preserves encrypted records, per-record deadlines and realm authority while maintaining rejection of expired, revoked and stale records. The test inspects physical storage independently from the validation barrier.

It does **not** demonstrate host power-loss recovery, kill-at-arbitrary-write safety, fsync/controller/storage honesty, truncated/corrupted AOF recovery, independent-authority availability, split brain, replica promotion, older backups, correlated Redis/authority rollback, cross-host quorum durability or actual hosting acceptance. The lab retains `aof-load-truncated=yes` from the comparison baseline; torn-tail recovery policy still needs separate review and testing. Redis describes multipart AOF and its truncated-load behavior in its [persistence documentation](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).

Clean restart is not failover durability. AOF, Lua atomicity and replication acknowledgments do not supply a restore-safe independent freshness anchor. The existing failure-closed recovery contract remains required: block dispatch, fence/drain old workers, reconcile uncertain provider/business operations, advance externally protected generations/epochs when freshness cannot be established, and require deliberate reauthentication. Do not rewind LMDB to match a restored Redis dataset or silently import old authority.

## Remaining production gates and recommendation

The local restart subcondition of **G13/G17 is now PASS on the pinned isolated candidate**. Both production gates remain FAIL until actual hosting/persistence/operations are qualified. All eight broader production gates remain open:

| Gate | Production result / remaining evidence |
| --- | --- |
| G04 | **FAIL** — real HTTPS/domain/proxy/private worker ingress and browser acceptance. |
| G06 | **FAIL** — secret-manager/IAM/KMS, fleet key rotation, retirement and compromise recovery. |
| G12 | **FAIL** — reviewed production factory/entrypoint, external authority and operator readiness integration; safeguard remains closed. |
| G13 | **FAIL** — actual target WSGI/process lifecycle, rolling compatibility and full restart/recovery acceptance. Local AOF replay blocker resolved. |
| G14 | **FAIL** — protected independent authority/freshness anchor and correlated-rollback/failover qualification. Current authority remains local LMDB. |
| G17 | **FAIL** — selected provider/version approval, TLS/ACL operator separation, durable volumes, monitoring/alerts, resource/failover qualification. Local replay blocker resolved. |
| G18 | **FAIL** — fleet clock/resource/watchdog and sustained fault/performance bounds. |
| G20 | **FAIL** — target-platform cutover, maintenance/rollback release and recovery rehearsal. |

**GO for a separately approved next isolated qualification phase. NO-GO for production.** Preserve the Phase 2G operating recovery plan and restrictions. No production service/account/session/record/Storage object/feature flag was accessed or changed. No SQL was executed; no safeguard was disabled; nothing was staged, committed, pushed or deployed. Stop pending approval.

## Exact files added in Phase 2H

Only this directory was added; earlier uncommitted application work is preserved:

- `investigate.py` — minimal physical/AOF/authority reproduction and sanitized diagnostics.
- `qualification.py` — repeated restart, all-family expiry/replay and concurrent-process checks.
- `qualified-redis.json` — the minimal corrected isolated image pin and scope.
- `verify_evidence.py` — offline source/SQL/test fingerprint verification.
- `REPORT.md` — this report.
- `baseline.json`, `fixed-comparison.json`, `qualified-comparison.json`, `qualification-results.json`, `verification-summary.json` — sanitized evidence.
- `focused-output.txt`, `focused-test-results.xml`, `python-output.txt`, `full-test-results.xml`, `javascript-output.txt` — final regression outputs.

Generated Python bytecode is not a deliverable. No dependency, application, SQL, production deployment or prior evidence file was changed. The downloaded official Docker image remains in the local image cache; no test container, test listener or persistent test volume remains.
