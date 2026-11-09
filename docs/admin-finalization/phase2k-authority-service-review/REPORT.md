# Phase 2K — protected authority service qualification and recovery review

**NO-GO for production provisioning, activation or deployment.** An independently protected transactional authority can satisfy the model, but no such infrastructure is currently qualified. This review recorded **49 positive isolated checks and two security FAIL findings**, plus **96 passing regression functions and 39 subtests**. All eight production gates remain FAIL.

**Recommended next phase: approve a design comparison/prototype plan for one durable transactional session store plus enforced recovery invalidation, retaining Supabase Auth and independent User/Admin cookies.** This is an engineering recommendation for reducing capstone operational burden, not a change to the approved/current architecture. No alternative was implemented. Continuing the external-authority design is also possible, but needs the controls and evidence below.

Only this documentation/testing directory was added. No runtime, dependency, existing test, environment, SQL, production authentication/session/record, photo/audit contract or feature flag changed. **No SQL was executed, including locally.** Transactional SQL backends were evaluated from documentation/design only. No production Redis/authority/secret infrastructure was provisioned or connected. The startup safeguard remains unchanged. Nothing was staged, committed, pushed or deployed.

## Inspected implementation and trust boundary

The current `ProtectedRevisionAuthority` is a client-side contract, not a deployed protected service. It pins authority identity/incarnation/minimum sequence, checks request correlation, rejects decreasing observed sequences and invalid shapes, and returns typed unavailable/conflict errors. Its sequence floor is **process memory**; a fresh worker starts at the supplied binding's floor. It does not independently establish that its supplied floor is current, authenticate a transport by comparing identity strings, or prove the semantic freshness of a response with a valid nonce.

The current `TestMetadataService` uses fsynced LMDB transactions for metadata, but its identity, incarnation and sequence counter are generated/stored in process memory. The counter increment follows the metadata transaction rather than sharing a durable transaction. Construction configures an OPEN local descriptor with the same realm epochs. A restart therefore changes identity/control generation but does **not** by itself invalidate all old record references. It is intentionally a test fixture, not a candidate production service.

The default application shared-session factory still refuses to run without explicit protected-authority injection. Raw LMDB/witness objects are denied by default; historical counterexample tests explicitly select their unsafe local-only option. Production activation remains unconditionally refused. There is no new production transport or automatic binding-adoption path.

| Boundary | Proposed production requirement |
| --- | --- |
| App workers, Redis, local LMDB, legacy witness and their backups | Treat as one potentially restored domain. They cannot supply their own proof of current revocation. Redis stores encrypted payloads; local LMDB/witness are not production authorities. |
| Authoritative metadata database | Separate managed transactional primary/qualified quorum, durable commits and linearizable conditional updates. Persist record changes, revision and control state consistently. No authority reads from arbitrary stale replicas. |
| Recovery/freshness control | Independently controlled, current monotonic high-water/incarnation or equivalent enforceable restore fence, outside app/database snapshot restoration. New workers must obtain a current binding from this control, not from the restored authority itself. |
| Credentials and operations | App identities can perform only scoped record operations. They cannot restore snapshots, open recovery gates, rewind revisions, issue bindings or change epochs. Recovery, secret and database administration require separate permissions/audit. |
| Encryption | Credentials/PKCE/CSRF/browser state stay encrypted using the existing AEAD contexts. Key management is separate from state backup. Encryption authenticates old data; it does not say whether it was revoked later. |

An independence claim must specify who can restore each component, which snapshots include secrets/control state, and how both running and newly started workers reject a restored authority **before use**. A second database/project under the same unrestricted restore credentials is not automatically independent. All-admin compromise or restoration of every trust anchor cannot be solved by comparing old internal hashes; that remains outside any claimed guarantee unless separately protected hardware/control infrastructure is qualified.

## Isolated security qualification

The Phase 2J rollback harness was copied byte-for-byte under a unique module name in this directory so its spawned workers resolve the correct file; prior evidence was not overwritten. Its **27 checks** requalified Redis-only, LMDB-only, joint Redis/LMDB and legacy-witness rollback, actual stale TLS Redis replica promotion, Redis SIGKILL, independent revocation and worker concurrency with the external test process excluded from those rollback operations. See [qualification-results.json](qualification-results.json).

The added service experiment supplied a **test-only verified mTLS JSON endpoint** in front of the existing LMDB fixture, with User/Admin certificate roles, key-prefix authorization, bounded request/response handling and no request logs. Operator fault/snapshot methods were accessible only to the owned Manager test process, not the app HTTPS endpoint. The transport made one verified TLS connection per RPC; it is not a production server, pool or provider qualification. The backend and its snapshots remained on this host/user. No independently protected anchor was supplied.

The final service run produced **22 positive checks and two security FAIL findings**. See [service-qualification-results.json](service-qualification-results.json).

| Scenario | Result | Revocation, continuity and reauthentication assessment |
| --- | --- | --- |
| Redis-only old AOF recovery | Conditional PASS | Current external test metadata still denies the revoked ciphertext. Valid external state is assumed. |
| LMDB-only and joint Redis/LMDB rollback | Conditional PASS | Local-only proof rejected; current external metadata denies the replay. Revoked account/session needs a new sign-in. |
| All application-managed legacy stores/witness rolled back | Conditional PASS | External process excluded from rollback stays current. With no configured protected authority, normal factory stays closed. This is not all-trust-anchor protection. |
| Authority-only stale snapshot, old identity, **warm worker** | PASS for tested case | Warm worker observed a later sequence and rejects the lower one. Availability is denied, not silently recovered. |
| Same stale authority snapshot, old identity, **fresh worker with older pinned floor** | **FAIL** | Fresh nonce and valid mTLS do not stop a revoked session being accepted. The snapshot's sequence exceeds that worker's old floor. Redis still physically contains ciphertext left by failed cleanup. |
| Operator adopts a newly generated binding from an older authority snapshot without new realm epochs | **FAIL** | Old revoked record becomes accepted. New identity/control generation alone is not global session invalidation for a newly constructed client. This intentionally violates the proposed recovery policy. |
| Authority backend process unexpectedly terminated | PASS — fail closed | Proxy/HTTPS failure denies intact Redis credentials. No local-authority fallback. |
| Same metadata files reopened after backend process termination | Conditional PASS | Acknowledged revocation remains deleted in intact LMDB; old binding is denied. A test-operator-injected new binding can read intact live records. This does not justify adopting a binding from an uncertain snapshot. |
| Actual black-holed local TLS response / partition | PASS — fail closed | Client times out while backend remains healthy. Same binding resumes after partition heals; delayed response supplies no fallback authority. |
| User mTLS identity requests Admin metadata, including forged realm field with Admin key | PASS | Server rejects actual key scope as well as the declared realm. This is local policy evidence, not full endpoint hardening certification. |
| Concurrent refresh paused before CAS, followed by acknowledged revocation | PASS | Late refresh CAS fails; revoked record remains invalid. No provider operation is repeated. |
| Independent User/Admin revocation and restarted reader/refresh workers | Conditional PASS | Other realm stays valid; fresh workers share current external state; one refresh owner. |
| Recovery QUALIFYING → new never-used realm epochs → OPEN | Conditional PASS, reauthentication required | Both realms' restored handles become invalid under new key contexts. Fresh synthetic authentication works. The operator/freshness control is test-only. |
| Rollback of authority **and all external bootstrap/control state** | UNPROVEN/unsafe | No separately protected anchor is available. Production must remain closed. A local monotonic counter/journal is not sufficient. |

The two FAILs qualify the limits of the current contract; they do not indicate that the still-disabled production path was activated. They demonstrate why a restored service must not be permitted to authorize its own new binding, and why a per-worker observed floor is insufficient for cold workers. The tests did not execute SQL, real Supabase refreshes, membership changes or actual audit insertions.

## Proposed durable authority and recovery model

If retaining the current Redis-plus-authority design, use a private authority API backed by a managed transactional database. One durable transaction must validate realm/generation/expected revisions, enforce quotas/deadlines, update the bounded record group and its revision/control metadata, then acknowledge only after the required durability boundary. Keep bearer credentials in encrypted payload storage. LMDB should remain solely a lab implementation, not an extra production authority tier.

Database transactions are necessary but do not prevent restoring an old consistent database. Require either a protected, current revision/root checkpoint outside the restoration domain, or an enforced recovery policy that closes authorization before any uncertain writer/snapshot can serve it. Current independent control must reject an authority whose durable checkpoint is older than required. Revision state cannot simply live in RAM or be restored with the records it authenticates. A real design must specify atomicity/acknowledgment ordering across any database/control-plane boundary and how interrupted operations stay closed; that protocol is not implemented or qualified here.

PostgreSQL documents synchronous local WAL commit versus asynchronous acknowledgments that can lose recent transactions. Its replication documentation also distinguishes asynchronous shipping from synchronous replication. These are backend design inputs, not proof of a selected hosted plan's failover behavior. [PostgreSQL commit durability](https://www.postgresql.org/docs/current/wal-async-commit.html), [PostgreSQL replication](https://www.postgresql.org/docs/current/warm-standby.html).

### Enforceable recovery procedure

1. Independently block protected dispatch before restore, uncertain promotion or binding replacement. Fence old workers; keep only explicitly stateless maintenance/public routes available. A PING or successful TLS handshake is not authority readiness.
2. Drain/reconcile already dispatched provider/database work. Revocation cannot recall an issued JWT or undo a business mutation already sent. Do not automatically replay timed-out writes.
3. Establish a known writer and trustworthy control state. If the revision checkpoint cannot be proved current, **invalidate all sessions**, using new never-reused User/Admin epochs or a new namespace as well as a new controlled incarnation. Changing only server identity/generation was demonstrated insufficient.
4. Pin the new binding and epochs from independently controlled current configuration. Do not import old handles or allow the recovered service to self-approve. Existing/cold workers must reject old epochs; in-progress CSRF/recovery/verification flows restart.
5. QUALIFYING remains closed. Verify durable backend/transport/permissions, then OPEN only after operator approval and acceptance evidence. Require fresh independent User/Admin sign-in. If the independent controller is unavailable or may be stale, remain closed.

This procedure was rehearsed only through test controls. It needs enforcement at every service bootstrap, restore path and routing/promotion point; a voluntary checklist or post-failover webhook does not guarantee detection before use. Backup restoration is not rollback-safe just because the backup is encrypted. Retain restore evidence and audit history; never repair session failures by restoring destination data or deleting business audit records.

## TLS, authorization, secrets and readiness requirements

Require private endpoints, verified CA/hostname, TLS 1.2 or higher, short-lived workload credentials or mTLS certificates, explicit namespace/realm/key permissions and separate operator recovery identities. Authenticate the peer rather than accepting echoed identity strings. Block undocumented endpoints, enforce body/time/rate/connection limits and redact cookies, raw references, tokens, verifiers, keys and payloads from logs.

Production secret delivery must protect AES keyrings, database credentials, trust roots, workload private keys and current control bindings. App roles must not read backup administration keys or edit the current recovery fence. Review rotation, predecessor decrypt retention, compromise invalidation and recovery access. The lab's one-day CA/private-key files and Manager IPC are not a production secret-management or service design.

Startup/readiness must require the **current independently authorized** binding, healthy durable writer, expected epochs/protocol/key IDs, scope permissions, trusted hosts/HTTPS/proxy configuration and bounded operations. Liveness can be separate from auth readiness. Return 503 or stop startup on unknown freshness, partition, clock/descriptor mismatch, quota/resource failure or pending recovery. Never read from a stale replica, bootstrap from local snapshots or choose memory mode because the service is unavailable. The unchanged startup safeguard continues to refuse production activation.

Monitor sequence/control mismatch, failed admissions, refresh conflicts/uncertainty, cold-start/binding attempts, commit/fsync errors, backend/replica lag, TLS/credential expiry, disk, quota, connection pressure, tail latency and partition events. Deliver/acknowledge real alerts in a later isolated target-platform rehearsal. No SLA or alerting system was qualified here.

## Latency and write amplification

Final measurement: 100 synthetic operations per batch, four threads, one protected client lock per realm, a fresh verified mTLS connection per authority RPC, local Manager/LMDB backend and loopback TLS Redis. These are **credential-store operations**, not full Flask requests or production throughput. The first exploratory batch was slower; final figures below are from the added server key-scope probe run.

| Measurement | Credential lookup | Authorized activity update |
| --- | ---: | ---: |
| Completed operations | 100/100 | 100/100 |
| Batch seconds | 5.1752 | 9.4029 |
| Operations/second | 19.32 | 10.64 |
| Client operation p50 / p95 | 192.387 / 310.229 ms | 369.128 / 466.552 ms |
| Authority calls | 300 descriptors + 200 reads | 600 descriptors + 200 reads + 100 commits |
| Authority RPCs per operation | **5** | **9** |
| LMDB transaction-ID delta | **0** | **100** |
| Redis encrypted MSET delta | **0** | **0** |
| Redis PEXPIREAT delta | **0** | **100** |
| JSON request / response bytes | 170,576 / 231,046 | 386,509 / 366,746 |

The intact authority-process restart/setup took **1.2111 seconds** to create the replacement test service; this is not end-to-end recovery RTO. Partition denial took **0.4183 seconds** with a 0.4-second transport timeout. The test does not establish host power-loss durability, cross-host latency, pooled TLS performance, backend HA, peak RSS, physical disk bytes/fsync amplification or a sustained SLO. JSON byte counts exclude TLS, HTTP, Redis and Manager framing.

Reads no longer rewrite encrypted state, but the current interface makes many authority round trips. An HTTP request may read browser state, resolve credentials, update activity and check Admin membership, so its cost can exceed either row. The client RPC lock serializes calls per adapter; multiple workers do not remove backend/network costs. For scale illustration, 100,000 credential lookups imply 500,000 authority RPCs under this path; 100,000 activity updates imply 900,000 RPCs and 100,000 metadata commits. These are arithmetic workload examples, not RosaGo traffic forecasts or Redis billable-command counts.

If continuing this design, qualify connection reuse, bounded pools and a smaller consistent authorization operation/API. Any batching must retain fresh revocation checks, generation fencing and conditional commit semantics. No performance redesign was implemented in this phase.

## Cost and operational comparison

USD public list pricing checked **2026-11-05**, before tax/egress/overages; no purchase, account/billing inspection or region quote was made. Current RosaGo plan, hosting, traffic and budget are unknown. Destination count is not a concurrency forecast. Free quotas and marketing availability claims do not prove required restore/permission guarantees.

| Architecture | Security and A/B compatibility | Hosting/maintenance | Cost assessment |
| --- | --- | --- | --- |
| Current Redis cache + external metadata API/database + protected recovery control | Compatible with opaque independent cookies if authority stays current. Still needs external restore fencing and all eight gates. LMDB should not be another production tier. | Highest: cache, service API, durable database, control plane, TLS/keys, cross-store publication, monitoring and compatible releases. | Add Redis, authority compute/database, backup, secrets/control and observability to existing app/Auth costs. No defensible complete quote yet. |
| **One durable transactional session database + recovery invalidation** | Recommended next design candidate. Store encrypted credentials, browser state, CSRF/recovery/rates and revocation/version state in one atomic store, with separate realm namespaces/cookies and fresh membership checks. Still requires restore-safe external recovery control. | Lower: one session store plus existing app/Auth; no Redis/LMDB/custom metadata-cache publication tier. Pooling, bounded TTL cleanup, refresh CAS, encryption and restore tests remain required. | Could use already funded managed capacity within quotas, or one paid database. Incremental software/provider cost may be low, but cannot assume $0 recovery/operations. |
| Supabase Auth/provider sessions + isolated server integration | Can preserve distinct A/B accounts; provider does not automatically separate same-origin SDK/browser storage or fix stale mutable cookie responses. Immediate local revocation still needs a reliable online session check or opaque server-side binding. | Lower identity-service burden; provider-session/introspection semantics and server-side mutable state/recovery/CSRF still need design. | Existing Auth MAU allowance may cover the workload. Replacing providers adds migration/testing and uncertain extra charges; no migration is recommended now. |
| Signed-cookie/JWT-only shortcut or one unprotected local store | Does not satisfy strict immediate revocation/rollback safety and stale-response requirements. | Superficially simpler, but fails the required guarantees. | Not an acceptable cost-saving alternative. |

Supabase currently lists Free at $0 with inactivity pausing; Pro starts at **$25/month with the first project included**, and additional projects start at **$10/month**. Paid plans include $10 compute credit; independent organizations are billed separately, so a second separately administered organization is not simply the additional-project price. These are pricing references, not a determination that the plan's IAM/recovery guarantees suffice. [Supabase pricing](https://supabase.com/pricing), [organization billing](https://supabase.com/docs/guides/platform/billing-on-supabase).

Supabase documents daily backups for paid projects, including seven-day Pro retention; Free users need their own backup exports. Backups improve recovery capability, not revocation freshness after restore. No export/restore command was executed. [Supabase backups](https://supabase.com/docs/guides/platform/backups).

As a separate managed Postgres price reference, Neon lists Free quotas and Launch usage pricing of **$0.106/CU-hour plus $0.35/GB-month storage**. Its advertised typical $15/month is not a guaranteed bill. Scale-to-zero can add cold-start latency; keepalives/health checks and frequent session traffic can affect active usage. This vendor was not contacted through a project API, provisioned or qualified. [Neon pricing](https://neon.com/pricing), [compute lifecycle](https://neon.com/docs/introduction/compute-lifecycle).

For Redis cost context only, Upstash lists Free **500,000 commands/month** and pay-as-you-go **$0.20/100,000 commands**. The advertised production add-on is **+$200/month/database**. Neither a low list price nor that add-on certifies compatibility with RosaGo's exact commands, TLS/ACL model or restore fence; no provider was selected. Estimate with actual billed commands, storage/egress and operations rather than counting only MSET. [Upstash pricing](https://upstash.com/pricing/redis).

### Managed authentication limitations

Supabase supports multiple sessions and identifies them with a `session_id` JWT claim, so distinct User A/Admin B identity sessions are conceptually compatible. Its documentation notes that checking current `auth.sessions` presence is relevant to preventing use after sign-out. Offline JWT validity alone is insufficient; no query/API for that was implemented or executed here. [Supabase session model](https://supabase.com/docs/guides/auth/sessions).

Supabase sign-out scopes also matter: `global` is the default in relevant SDKs, while `local` targets the current provider session. Issued access tokens can remain valid until expiry. An alternative must preserve independent realm logout and audited Admin B credentials without an accidental global sign-out or service-role substitution. No provider settings changed. [Supabase sign-out](https://supabase.com/docs/guides/auth/signout).

Provider-only identity storage cannot simply replace mutable User browser state, CSRF challenges, shared recovery/rate limits and local revocation guarantees. A reviewed backend-for-frontend using separate HttpOnly cookies and one transactional server-side state store is the more direct simplification for the already approved server-side browser-state requirement. This is a proposal requiring separate approval.

## Minimum practical capstone infrastructure and recommendation

Minimum practical candidate: existing HTTPS Flask hosting, existing Supabase Auth/business APIs, **one managed transactional session store**, independent recovery/deployment control that is not restored with that store, secure key delivery and a named operator who can handle downtime/restore/alerts. Separate User `/` and Admin `/admin` opaque HttpOnly cookies, realm CSRF, scoped provider clients and fresh database membership/actor checks remain. Keep session-storage credentials away from business-data mutation/audit attribution.

Prefer deliberate maintenance and mandatory reauthentication after uncertain recovery over operating an unqualified custom HA authority stack. This does not weaken revocation requirements: it trades availability for fail-closed security. If the provider cannot guarantee intact acknowledged state on automatic failover, recovery/promotion must be gated before authority is served. If that cannot be enforced or funded, production authentication remains NO-GO; local demonstration is the safe scope.

A hosting environment variable or secret-manager alias is not automatically monotonic: it must be independently controlled, not reverted with app deployments/backups, and prevent reopening old epochs. If arbitrary restoration of every control state is in scope, a genuinely independent protected anchor is still mandatory. No cheap single-database design alone can solve that indistinguishability problem. The current information is insufficient to approve a provider, budget, uptime target or maintenance owner.

For this student project, the current multi-service proposal is **not yet demonstrably maintainable**. It is technically possible under the defined external guarantees, but its small-workload cost/latency and recovery complexity are not justified by available traffic/SLO evidence. A single-store design with explicit recovery invalidation is a more realistic candidate to review next; no architecture switch should occur without approval and a concrete preservation/test plan.

## Regression, integrity and remaining gates

Fresh focused regression: **96 functions and 39 subtests PASS**, covering protected-interface/session tests, CSRF/recovery, membership, User/Admin isolation and synthetic audit actor contracts. See [focused-output.txt](focused-output.txt), [focused-test-results.xml](focused-test-results.xml). Actual production membership/audit writes were not exercised. Full Python (1,105 functions/1,402 subtests), JavaScript (68) and browser evidence from earlier phases were **not rerun in this review**. Current 17 Phase 2J source/test/dependency fingerprints and all three SQL byte fingerprints match; [verification-summary.json](verification-summary.json).

| Gate | Updated production result |
| --- | --- |
| G04 — HTTPS/hosts/proxy | **FAIL** — local service mTLS/scope checks pass; actual app/service topology, DNS/cert lifecycle/private ingress/browser acceptance unqualified. |
| G06 — secrets/key lifecycle | **FAIL** — ephemeral lab credentials do not qualify secret manager, IAM, rotation, retirement or compromise recovery. |
| G12 — startup/readiness | **FAIL** — default closure retained; no independently current bootstrap/control plane or approved production backend/transport. |
| G13 — multiworker/recovery | **FAIL** — local process/crash tests pass conditionally; target WSGI/rolling recovery and production persistence not qualified. |
| G14 — durable revocation | **FAIL, demonstrated** — stale authority cold-bootstrap and new-binding/no-epoch recovery restore revoked authority under unsafe control procedures. |
| G17 — service/Redis operations | **FAIL** — no selected qualified transactional provider, enforceable restore/promotion gate, alerting, capacity or operator separation. |
| G18 — clock/resource/SLO bounds | **FAIL** — local deadlines and measurements exist; real cross-host time/resource limits, cold starts, pooling and sustained tails remain unknown. |
| G20 — rollout/rollback | **FAIL** — no approved alternative, target release/rollback pair, protected recovery rehearsal or production acceptance. |

**GO for a separately approved architecture decision and isolated design/prototype phase. NO-GO for production provisioning/deployment. Stop pending approval.**

## Files and experiment notes

Only this directory was added: `REPORT.md`, `service_lab.py`, `qualify_service.py`, `app_rollback_qualification.py` (unchanged source copy of the reviewed Phase 2J harness), `verify_evidence.py`, `qualification-results.json`, `service-qualification-results.json`, `verification-summary.json`, focused test output/XML. Generated bytecode is not a deliverable.

The initial attempt to import the old harness under its generic module name collided with a Phase 2G module when Windows spawned a process. The owned hung process was identified/stopped; its ID/label/loopback-verified container/network were removed. The unique copied module resolved this harness issue. The final service run additionally checks server-side forged key scope; reported metrics are from that run. Neither event changed runtime architecture or broadened app privileges.

Owned containers/volumes/network, Manager/TLS listeners and temporary keys/snapshots were cleaned up. Evidence contains only synthetic operation results, aggregate sizes/timing and scenario booleans, not raw cookies, tokens, private keys or production credentials. The cached official Redis image was reused. No production infrastructure or settings were touched.
