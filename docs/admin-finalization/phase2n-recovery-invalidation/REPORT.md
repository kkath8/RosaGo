# Phase 2N — PostgreSQL Session Recovery Invalidation and Security Qualification

Date: 2026-11-05. Reference: [Phase 2M](../phase2m-postgresql-session-implementation/REPORT.md).

**NO-GO for activation or deployment.** Both Phase 2M failures are reproduced and conclusively characterized. An explicit closed-gate recovery drill safely invalidates sessions **when recovery is declared and independently enforced before accepting traffic**. It cannot make an undetected restore safe. No trustworthy production recovery boundary has been established. All eight production gates remain FAIL. The PostgreSQL adapter, existing implementation and startup safeguard remain unchanged and inactive for production.

## 1. Changes and evidence scope

Added files only, in this directory:

- `recovery_procedure.py`: isolated operator drill for closing, transactionally invalidating and reopening a test namespace. It accepts only the loopback `rosago_lab_m` fixture. It is not an application hook, automatic restore detector or production runbook executor.
- `qualify_recovery.py`: real backup/restore, recovery, replay, concurrency, worker-restart and key/configuration experiments, plus rerun of the existing PostgreSQL Flask/security suite.
- `verify_evidence.py`: offline preservation checks against prior source, SQL and Phase 2M artifact hashes.
- This report, `security-results.json`, `verification-summary.json`, `qualification-output.txt`, `initial-concurrency-output.txt`, `focused-output.txt` and `focused-test-results.xml`.

No existing files were edited. No new service, production migration, secret, environment setting or active adapter wiring was introduced. Production requests and SQL executions: zero. No staging, commits, pushes or deployment.

Final offline verification matches 22 prior source/test/dependency hashes, all three destination/photo/audit SQL contract hashes and all 26 recorded Phase 2M artifact hashes. The owned fixture list and temporary credential directory list are empty after cleanup. See `verification-summary.json`.

The drill reuses Phase 2M's owned disposable PostgreSQL 17.11 fixture, Docker name `rosago-phase2m-postgres`, phase label `2m`, published only on `127.0.0.1:16432`. Image: `postgres@sha256:653186fe15006c099d2fb3bc1d8461c1dee9d036c43f2e5fdaf4f22e5e601876`. Runtime uses the restricted application role; backup/restore/invalidation use the isolated operator role. Only the private fixture schema is dumped/restored. Passwords are generated locally, no DSN/key/token/dump is archived, and the fixture removes its verified container, anonymous volume and temporary credential directory. No production Supabase connection was made.

## 2. Root causes and authority trace

The validation path is:

1. The browser supplies an opaque realm-specific reference.
2. A worker hashes it into the configured namespace/realm/epoch key.
3. `RecoveryFence.check` requests a nonce-bound current proof matching the configured authority ID, incarnation and both realm epochs. It checks timestamp, state and an in-memory revision floor.
4. A SQL transaction checks the matching OPEN database gate, then record expiry, current tombstone and payload/version consistency.
5. AES-GCM decrypts using key ID and AAD binding the scope/reference; the encrypted expiry is checked.
6. A second recovery proof check occurs before the caller receives a successful result.

### Failure A: database-only rollback

The backup was taken while a session was valid. Logout later removed its payload and installed a terminal marker. Restoring the complete private schema restored the old payload, version row and OPEN gate, and removed the later marker. The unchanged test controller still asserted VERIFIED for that same epoch. The old key could decrypt the old ciphertext, and both physical and encrypted deadlines were still valid. Every local check therefore agreed on old authority. **The revoked reference resolved again.**

The controller was outside the database backup, but it had no knowledge or enforcement of the restore event. An independent process alone is not independently trustworthy freshness. A database-local high-water mark cannot protect against rollback of its own history.

### Failure B: database, deployment and controller rollback

The test restored the old database, old epoch/configuration and old encryption authority, then constructed a fresh worker with a predecessor-state controller. That controller produced a *new* nonce response with a current timestamp from old state. A new worker had no surviving revision floor. The restored gate and ciphertext matched its old binding. **The revoked reference resolved again.**

The source was stale in its knowledge, not stale in its response timestamp. Hashes, nonces and internal consistency do not prove historical freshness. If every input that distinguishes “still valid” from “subsequently revoked” is rolled back within the original expiry window, the application cannot distinguish those histories. Adding another database row, environment variable, file, signature or same-boundary witness does not supply the missing information.

## 3. Trust and rollback boundaries

| Component | What can roll back / required protection |
| --- | --- |
| PostgreSQL records, versions, markers and gate | All can return together in a complete backup/PITR restore. SQL transactions prevent partial ordinary writes, not restoration of old committed history. |
| Render build/start configuration | A predecessor build can restore old adapter assumptions or omit checks. Only compatible builds may run after cutover; incompatible workers must lose traffic and DB/secret authority. |
| Service environment values | Old epochs, keyrings and DB credentials can return with a deployment rollback. They cannot be the sole freshness source. |
| Environment-group values and links | Current values alone do not guarantee current group attachment, absence of overrides or enforcement by an old build. |
| Encryption keys | An old ciphertext is authentic under its old key. Keeping that key for decryption preserves replay capability unless another current fence rejects it. |
| Worker memory/revision floor | Helps a surviving worker detect a decreased proof revision; disappears on restart. It is not a durable monotonic anchor. |
| Local test controller | Outside DB snapshots only; no protected storage, authenticated production transport, restore interlock or rollback-resistant revision history. |
| Time | Expiry eventually rejects old records with trustworthy clocks. It is not immediate revocation, does not detect an unexpired snapshot and is not a substitute for recovery fencing. |

Information that must remain trustworthy is **the current permitted deployment/recovery incarnation and admission state**, including whether uncertainty requires global invalidation, plus the authority to prevent old workers/configuration from serving. It must be outside the restore/rollback operation being protected and checked before use. A newly restored controller must remain closed unless its own current state can be established independently.

## 4. Implemented isolated recovery mitigation

The operator drill uses the existing simplified schema without changing the adapter:

1. Assume externally enforced maintenance and worker draining. Mark the test controller BLOCKED/UNCERTAIN first, then close the SQL gate. The mock controller does not enforce public traffic admission or stop dispatched business operations.
2. Allocate a new random incarnation and both realm epochs outside the database restore. Reject immediate predecessor reuse. A durable global never-reuse policy remains external and unimplemented.
3. In one SQL transaction, lock the expected BLOCKED predecessor gate, install the new values in QUALIFYING state, and delete the namespace's private records, markers and version rows. Reset pending recovery, verification, CSRF and rate state as part of this *global recovery*, not ordinary logout. No destination, audit, profile, photo or Auth table is touched.
4. Keep requests closed if the transaction fails. The synthetic interruption test confirms all deletions/gate changes roll back together and the predecessor stays BLOCKED.
5. After external qualification, open the matching SQL gate and only then mark the test controller OPEN/VERIFIED for the new binding. Old workers/configuration are rejected; new workers see old references as absent and require fresh independent logins.

This is conditional mitigation, not a production recovery service. It cannot detect an undeclared restore or prevent restoration of the entire old controller/configuration. It also cannot recall a request that already passed authorization and dispatched a mutation; actual drain/termination and credential/connection fencing must precede restore.

The in-flight read test pauses after reading SQL state, closes recovery authority, then resumes: its post-proof rejects the result. That is useful defense within the adapter's validation window, not a global guarantee against operations already returned to callers.

### Encryption/signing rotation assessment

Removing the old session decryption key caused restored ciphertext to fail closed. Switching the write key while retaining the old decrypt key did **not** invalidate it. Therefore ordinary gradual key rotation is not recovery invalidation. A hard key retirement can force reauthentication only if all old workers stop, predecessor keys cannot reappear through secret/config rollback, and old authority cannot remain reachable. Those controls are not provided here.

These PostgreSQL cookies are opaque; rotating Flask's signing secret alone does not invalidate their server-side references. Changing Supabase JWT signing keys is a different, broad Auth operation and was neither performed nor proposed as the session-store fix.

## 5. Security test results

Evidence: [security-results.json](security-results.json), [focused-output.txt](focused-output.txt), [focused-test-results.xml](focused-test-results.xml).

**Final recovery qualification: 30 assertions satisfied, including four assertions that deliberately demonstrate unsafe configurations. This is not 30 secure production gates.** Two primary unsafe rollback scenarios remain. Additional counterexamples show retained-key rotation and loss of the per-worker revision floor do not solve them.

| Scenario | Observed security outcome |
| --- | --- |
| Ordinary logout and revoked reference replay | Rejected. |
| User logout while Admin remains signed in | Admin remains valid; separate realm authority. |
| Admin logout while User remains signed in | User remains valid. |
| Concurrent refresh/logout across two processes | Revocation confirmed using bounded fresh-CAS retries in the drill; subsequent User resolve rejected, Admin preserved. |
| New worker processes with unchanged current state | Both realms remain valid and consistent; no global reset on ordinary restart. |
| Missing recovery provider | Rejected at configuration/contract boundary. |
| Unavailable, old-timestamp or UNKNOWN proof | Fail closed. |
| PostgreSQL-only complete rollback, undeclared | **UNSAFE: revoked session returns.** |
| Old ciphertext with old key removed | Rejected. |
| Rotation retains predecessor decrypt key | **UNSAFE as invalidation: restored session still resolves.** |
| Read overlaps recovery closure | Post-proof rejects the read. |
| Explicit BLOCKED recovery mode | Old authority rejected. |
| Interruption inside invalidation transaction | Rollback preserves original private state and BLOCKED gate; requests remain closed. |
| Immediate epoch reuse attempt | Rejected; global historic reuse protection remains unimplemented. |
| Committed invalidation | All namespace records/markers/versions cleared atomically, gate remains QUALIFYING. |
| New binding opens after declared recovery | Old worker rejected; all old references absent; mandatory reauthentication. |
| Fresh independent logins after recovery, multiple processes | Both current realms resolve consistently. |
| Database recovery epoch rolls back | Current controller/worker rejects the old gate. |
| Old environment/binding with current controller | Rejected, even when an old DB gate matches that environment. |
| Complete DB and environment rollback, controller current | Rejected. |
| Complete DB/environment/controller rollback, fresh worker | **UNSAFE: revoked session returns.** |
| Proof revision decreases, original worker survives | Rejected. |
| Worker restarts with lowered controller revision | **UNSAFE as durable freshness: no surviving revision floor.** |

The final existing PostgreSQL/Flask regression run passed **39 tests and 21 subtests in 31.22 seconds**. It covers login orders, independent logout/expiry, CSRF isolation, PKCE recovery/reset, email verification, unauthorized Admin denial, mocked fresh membership and B's mutation attribution contract, browser CAS/rotation, expiry, capacity and fault bounds. Storage cases are also inherited by the Flask fixture; counts overlap and are not unique security requirements. Provider and business calls are mocked, not live Supabase acceptance. Full Python, JavaScript and browser suites were not repeated in this phase because all runtime, adapter and test files are unchanged; their Phase 2M results are historical evidence only.

Restart/redeployment experiments construct fresh store-worker processes with current or predecessor bindings. They do not deploy to Render or prove hosted Flask process supervision. The Flask regression fixture uses two application instances; separate-process tests qualify backend consistency, not the full hosted request stack.

The initial raw concurrent `PgModel.revoke` experiment raised `RevisionConflict` when refresh won its comparison window. This is not acknowledged logout or restored revoked authority. The drill now retries only local revocation from a fresh snapshot, at most three times; it never retries a provider refresh. The final run passed. The existing adapter/shared logout path was not changed and still needs explicit bounded-conflict/error UX qualification before activation. Exhausted retries or unknown commits must produce unavailable, never a claimed successful logout. The initial sanitized trace is retained in `initial-concurrency-output.txt`.

The final two-process race required one fresh-CAS retry before confirmed revocation. That retry exists only in the drill, not the application's logout implementation.

Declared invalidation/open drill time was **0.0454 seconds**, excluding human verification, traffic fencing, worker draining, restore and real secret delivery. This is not a production recovery-time objective or hosted performance measurement.

## 6. Practical deployment decision

### Simplest acceptable target

Keep one PostgreSQL session store. Prefer **mandatory global reauthentication through an independently enforced maintenance/cutover procedure** to adding another always-running custom authority service. This is sufficient only for an explicitly controlled restore model where every restore/promotion/config rollback is prevented from serving until current recovery state is established. No such enforcement has been demonstrated on RosaGo's hosting.

Minimum required controls are a separately protected recovery record/secret and release authorization, denied-by-default maintenance entry, ownership of all restore/redeploy paths, old-worker and old-credential retirement, verified never-reused epochs, and a compatible closed-mode rollback build. Reading an offline record once at startup is insufficient if the DB can subsequently be restored under live traffic. A small operator-controlled workflow could avoid another service **if** it can enforce all those boundaries. If recovery can be silent or outside that workflow, a genuinely independent current authority/control plane or different managed-session service with qualified recovery semantics is necessary. It must still be independently justified; merely moving data to another database/provider is not proof.

### Render

Render documents that rollback reuses predecessor build/start-command and service environment values. Environment-group values remain current, but group attachment can change or disappear; old builds may also contain stale build-time values. Thus “put the epoch/key in an environment group” is not a complete rollback barrier. Actual precedence, compatible-build allowlisting, secret retirement, worker termination and recovery admission need testing. [Render rollback behavior](https://render.com/docs/rollbacks).

Render Free has idle spin-down and an ephemeral filesystem, and Render advises using it for preview/testing rather than production. Local files/test controllers are unsuitable recovery authorities. Sleeping cannot extend session deadlines, and each worker needs its own bounded post-fork DB pool. No Render service was contacted or deployed. [Render Free limitations](https://render.com/docs/free).

### Supabase PostgreSQL and Auth

Supabase can host ordinary transactional session tables privately; actual custom-role TLS/pooler/grant/schema exposure and capacity remain unqualified. Use the appropriate direct/session/transaction pooler with bounded application pools; transaction mode requires avoiding session-scoped assumptions and prepared statements. The inactive adapter already uses transaction locks/SET LOCAL and disables automatic preparation, but no hosted compatibility claim follows from local tests. [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).

Supabase PITR restores earlier database state. Its restore downtime is not a session invalidation handshake: automatic reconnection after recovery can still see stale sessions. Its documented daily-backup handling of custom-role passwords is not a general rollback defense for all SQL imports or all recovery paths. No provider-level pre-open restore interlock was qualified. [Supabase backup and restore documentation](https://supabase.com/docs/guides/platform/backups).

Existing Supabase Auth remains the credential issuer. Access tokens can remain usable until expiry after sign-out, and refresh reuse rules are not an application rollback detector. Checking `auth.sessions` can strengthen selected provider-revocation checks, but if that state is restored with the same project it is not an independent freshness anchor. Global provider sign-out could also affect account sessions outside the selected realm. No Auth settings, provider sessions or signing keys were changed. [Supabase session behavior](https://supabase.com/docs/guides/auth/sessions).

### Low-cost capstone recommendation

There is no justified secure production boundary in the current evidence. Recommend a **restricted, disposable demonstration using isolated synthetic accounts/data and no production Admin authority**, with explicit maintenance and fresh logins for every uncertain recovery. This is a scope restriction, not a claim that the two rollback vulnerabilities are fixed. Any hosted demonstration still requires separate approval and ingress/secret review; the current adapter stays inactive.

For production, choose either enforceable managed recovery/cutover controls around the single PostgreSQL design, or a separately reviewed managed session authority outside the database/deployment rollback boundary. If neither can be afforded or operated, do not activate production authentication under the stronger rollback-resistance requirement. More same-boundary witnesses are not a useful next step.

## 7. Updated eight production gates

| Gate | Status | Remaining evidence |
| --- | --- | --- |
| G04 HTTPS/hosts/proxy | **FAIL** | No qualified Render ingress, hosts, proxy trust or hosted cookie acceptance. |
| G06 Keys/secrets | **FAIL** | No protected delivery/retirement or demonstrated prevention of predecessor key/config restoration. |
| G12 Startup/readiness | **FAIL** | Safeguard preserved; no active neutral PostgreSQL wiring, enforceable recovery-mode launcher or trusted production proof source. |
| G13 Multiworker/recovery | **FAIL** | Local workers/drill pass; hosted worker drain, rolling deploy, reconnect and sleep/recovery controls unqualified. |
| G14 Durable revocation | **FAIL** | Ordinary transactional revocation works; both undeclared/all-boundary rollback scenarios remain unsafe. |
| G17 Operations | **FAIL** | No enforceable restore ownership/interlock, actual capacity/cleanup/TLS/role/monitoring qualification. |
| G18 Faults/SLOs | **FAIL** | Local proofs and concurrency tests only; unknown-commit UX, hosted faults, protected-controller behavior and resource/recovery SLOs unresolved. |
| G20 Rollout/rollback | **FAIL** | No qualified environment/build rollback policy, old-worker retirement or production recovery rehearsal. |

## 8. Final recommendation

**Phase 2N qualification complete; NO-GO for activation or production deployment.** The two vulnerabilities are characterized, not repaired by a new trustworthy infrastructure boundary. Conditional global invalidation is demonstrated; autonomous detection and rollback resistance remain unproven. No new always-running authority service was added. Any next work should make a concrete hosting/threat-boundary decision before further production implementation.

All existing User/Admin, CSRF, recovery, destination, Environment, photo and audit implementations remain unchanged. Stop pending approval.
