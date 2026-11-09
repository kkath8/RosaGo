# Phase 2E — infrastructure, failover, rollout and rollback plan

**Prepared only. No provisioning or connection was performed. Current production decision: NO-GO.** Implementation corrections and isolated qualification in REVIEW.md must precede production infrastructure approval. The procedures below are future approval gates, not commands or authorization to execute them.

## 1. Recommended target and eligibility

Keep one authoritative writer for the security-state service, separate User/Admin namespaces and preferably separate ACL identities. Never send authority lookups to read replicas or active-active eventually consistent services. Separate staging/production services or strictly isolated namespaces/identities; no shared cache eviction domain for unrelated product caching. No Redis Cluster until atomic transaction-group placement has been separately reviewed.

Select a provider only after it demonstrates either acknowledged-security-write durability under the accepted fault model, or the enforceable **pre-use promotion barrier** below. An asynchronous notification after automatic promotion is insufficient. Do not purchase a plan based only on dataset megabytes or a successful PING. Region, residency, operating responsibility, pricing, private connectivity and incident support remain unknown inputs.

Preferred qualification target is controlled promotion with transparent automatic failover disabled, pinned writer identity and an independent traffic/control gate. If a managed service cannot expose/fence the actual writer before serving a replacement, it is unsuitable for this option. Return for backend/provider review; do not silently substitute a database schema, weaken durability requirements, or enable memory mode.

## 2. Enforceable failover/epoch mechanism (proposed; not implemented)

This is an engineering design to qualify, not a Redis guarantee. Its claim is limited to the tested fault model: accidental process/storage failure, network partitions, controlled promotion and backup restore. It does not protect against a fully compromised application holding both realm keys, or a privileged operator bypassing all controls.

### Independent control state

Use a durable, linearizable control store **outside the Redis dataset, its snapshots and its failover domain**. It must support conditional generation changes and access-controlled operator updates. No provider/control-store product is selected here. Maintain an immutable generation descriptor with:

- State: BLOCKED, QUALIFYING or OPEN; only the control-plane operator may change it.
- Monotonically advanced deployment generation and independent, never-reused User/Admin epoch identifiers.
- Expected physical writer incarnation, protocol/operation-definition version and allowed current-epoch key patterns.
- Release/configuration compatibility descriptor, readiness approval and revocation/failover incident reference. Store key IDs, not encryption keys, in non-secret diagnostics.

The application cannot advance generations or epochs. Do not keep the only epoch value in Redis or generate a new random epoch on each worker startup. All workers must agree with the same descriptor; otherwise they remain unready.

### Non-bypassable data path

Every worker reaches Redis through an authenticated private gateway or equivalent provider-enforced barrier. Firewall/IAM rules prohibit application access around it. The gateway admits an operation only when the independent descriptor is OPEN, its generation/realm epoch match, and the actual upstream connection is pinned to the approved primary incarnation. It must reject unavailable/stale control state rather than cache OPEN authority across requests.

Incarnation verification must happen **before any authority result or transition is served**, including the first command after reconnect or a new worker starting. A process run ID plus physical primary identity/role can be part of qualification when direct pinned connections are available. A logical DNS name, certificate for a floating endpoint, or one INFO call at initial connection does not prove that an opaque provider proxy cannot reroute later commands. Transparent upstream switching must be disabled or protected by an equally strong provider pre-use barrier. If this cannot be demonstrated, the provider gate fails.

Application requests carry the admitted generation internally; every authority transition must still match it. Recheck admission before dispatching a new protected provider/database operation after a gate transition is possible. No stale worker may keep serving from an old positive authority snapshot. An already dispatched external operation cannot be recalled; drain/reconcile it and reject late storage completion from the old generation.

Redis app ACLs and gateway key allowlists permit only the current epoch's realm keys and a narrowly defined health prefix. Removing old-epoch permissions/fencing old workers prevents an old configuration from authenticating against a still-live old dataset. The gateway/control-plane path also enforces this; ACL changes alone are not the independent durable gate.

### Promotion / unknown restart / restore sequence

1. Set BLOCKED through a conditional durable control-plane update. Deny new auth/recovery starts, authority reads/refreshes and protected business dispatch. Data-plane connection/incarnation faults also deny requests immediately; do not await a webhook.
2. Fence the old writer and all app paths to it. Drain requests or terminate workers that cannot acknowledge the barrier. Reconcile already dispatched provider/business writes without replay. A partitioned old primary must not remain a usable authority endpoint.
3. Perform the promotion/restore behind the closed barrier. Identify the actual new writer/process and its recovered state. Even a seemingly intact Redis-process restart is a new incarnation requiring explicit qualification; ordinary app-worker restart is different.
4. For possible data rollback, advance **both** realm epochs and the deployment generation in the independent control store. Scope to one realm only if isolation of the storage incident is proven. Never reuse a previous epoch or copy old credential/browser/recovery records into the new epoch. Old records may be left to expire under inaccessible keys.
5. Install current-epoch ACL/key rules, update all workers and rebuild pools against the expected writer. Old configuration/generation/connection must be rejected, not merely removed from the load balancer eventually. An old ciphertext transplanted to a new epoch must fail its authenticated context.
6. Enter QUALIFYING. Operators test using separate probe state/identities, with public auth still blocked: real writer identity, TLS, scripts, exact ACLs, clocks, persistence/noeviction, memory/connections, clean new-epoch authority and old-cookie/old-grant rejection.
7. Conditionally set OPEN only after every required worker reports the approved tuple and an independent reviewer approves incident recovery. A/B must sign in separately. Changing User epoch also restarts User recovery/verification; changing Admin epoch never promotes User authority.

For a provably intact reconnect to the **same** approved writer incarnation with no restore/rollback, qualification may preserve sessions under unchanged epochs. For an app-worker restart, compatible protocol/keys/epochs preserve sessions normally. Never infer integrity merely because Redis is reachable again. New incarnation without a proven durability path defaults to epoch invalidation.

AOF/replication/WAIT tuning can improve durability but does not replace this barrier. See the documented failure limits in [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/). No acceptance result currently proves this proposed mechanism; implementation plus adversarial staging rehearsal is mandatory.

## 3. Infrastructure and capacity requirements

| Area | Required production condition |
| --- | --- |
| Transport | Private allowlisted access; rediss/TLS with CA and hostname verification, no verification-disable query/config overrides. TLS also protects relevant replication/gateway paths. [Redis TLS](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/). |
| ACLs | Dedicated realm identities restricted to exact current-epoch key patterns; reviewed GET/SET/EVAL/TIME operations and minimal handshake/health support. No app CONFIG, ACL administration, FLUSH, restore, backup or promotion privileges. Test nested script key/command denial. [Redis ACLs](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/). |
| Eviction | `noeviction`, independently verified by a privileged operator/agent; no silent LRU/LFU eviction of authority/replay state. OOM must fail closed. [Redis eviction behavior](https://redis.io/docs/latest/develop/reference/eviction/). |
| Persistence | Reviewed AOF/durable-write mode, disk health, rewrite/replication buffers and backup retention. Prefer fsync-every-write where supported/qualified; do not allow a truncated/older recovery to reopen old epochs automatically. Local appendfsync=always tests prove only their tested restart case. |
| Memory | Size dataset, connection buffers, replication/AOF/rewrite overhead, fragmentation, encrypted serialization copies and app-worker RSS. Qualify admission/control reserves before choosing a plan; more server RAM cannot fix the 2 MB application cap. |
| Connections | Current default maximum is `32 × workers` for two pools of 16, plus gateway/health/operator connections. Four workers imply 128 app connections; compatible rollout surge may double that. Provider limits, worker concurrency and pool saturation behavior must be tested. Pools are created/reset per worker after fork; no inherited live connections. |
| Time | Synchronized worker/gateway/Redis clocks; bounded skew and handling for material clock regression. Provider expiry and Redis lifecycle clocks have distinct validation points. |
| Monitoring | Redacted metrics and alerting independent of the auth outage; operator access to writer/persistence/memory configuration without granting those privileges to app identities. |

Current aggregate sizing is a failed gate. Upper-bound active values are about 5.33 MB for two realm keys, but each full-size CAS can carry about 8 MB of bidirectional ciphertext. With four workers and 128 pooled connections, queued command arguments alone can be hundreds of MB at worst-case document size; buffers, copies and persistence matter more than the two key values. These are engineering bounds, not a Redis MEMORY USAGE measurement or a recommended instance SKU.

Forecast separate counts and payload maxima for active credentials/browser state, guest/pre-login state, challenges, 120-second operation receipts, refresh reservations, 600-second recovery/grants/replay markers, 1,800-second email verification and minute rate counters. Include unsuccessful and bot traffic, static asset fan-out, bursts, multiple tabs and rolling-worker overlap. Do not use destination record count as a session-volume estimate.

Before plan selection, remove or explicitly qualify aggregate write amplification and stale-family retention. Measure the chosen design at expected load and a documented burst margin, including saturation. Define per-operation growth limits, global reclamation and reserved revocation/finalization capacity. Establish alert/admission thresholds from those bounds; arbitrary percentages alone do not guarantee a logout can commit.

Required metrics include: size/receipt occupancy and reclaimed expiry counts per realm; CAS conflicts/retries/latency; 409/503/busy/uncertain counts; command/provider deadlines; pool exhaustion; writer/control-generation mismatch; gate state; TLS/ACL failures; key-version usage; worker readiness; memory/RSS/evictions/OOM; persistence/fsync/rewrite/disk errors and replication state. Do not use raw handles, users, tokens or recovery secrets as metric labels. Disable credential-bearing access-log queries, SDK/Redis wire debug, APM local-variable capture and secret-manager payload logging. Alerts must function while the app cannot authenticate an operator.

## 4. Environment and key management

These are the required **future production contract**, not all currently supported inputs:

| Input | Status and requirement |
| --- | --- |
| `ROSAGO_AUTH_MODE` | Existing; production remains blocked. Production entrypoint must require explicit production and reject omission/development/redis-local. |
| `ROSAGO_SESSION_BACKEND` | Proposed; validate redis with no fallback. Not currently consumed. |
| `ROSAGO_SESSION_REDIS_USER_URL`, `ROSAGO_SESSION_REDIS_ADMIN_URL` | Existing local names; future production factory must require verified TLS and the approved gated writer/ACL identities. Secrets; never log URLs. |
| `ROSAGO_SESSION_NAMESPACE` | Existing; fixed environment/protocol scope, never request supplied; no staging/prod collision. |
| `ROSAGO_USER_SESSION_EPOCH`, `ROSAGO_ADMIN_SESSION_EPOCH` | Existing inputs; must match the durable independent descriptor. Environment strings alone do not implement a failover barrier. |
| `ROSAGO_SESSION_KEYRING` | Existing secret JSON current key ID and key-ID-to-base64-32-byte-key map. Supply via reviewed secret manager injection, not source, screenshots or shared `.env` files. |
| `FLASK_SECRET_KEY` | Existing separate stable shared signing secret for other features; never reuse it as the AES key. |
| `ROSAGO_PUBLIC_ORIGIN` | Proposed; validate exact canonical HTTPS origin, callback authority and trusted host. Not currently wired. |
| Trusted hosts / proxy settings | Proposed deployment contract with verified hop counts per header, root mount, no direct public WSGI listener, ingress strips client forwarded headers. No guessed defaults. |
| Control-plane descriptor/gateway identity | Proposed new integration; durable generation, expected writer incarnation and epochs; short-lived app access credential and trusted control-plane endpoint. Final variable names require implementation review. |
| Existing Supabase URL / publishable key | Preserve existing issuer/key and verified user-scoped clients. No service-role key, SQL migration or provider-setting change is required by this session design. |

Encryption keys are generated through an approved cryptographic source and stored in a secret manager, accessible only to the required runtime/operator identities. Keep environments separate and audit secret access. Plan delivery during worker startup/restart, not per-request secret retrieval that could log credentials or fragment configuration.

Routine rotation has three controlled stages: (1) all workers can decrypt old/new keys while still encrypting with old; (2) after proving reader compatibility everywhere, switch current encryption to new; (3) after all old writers are gone, live documents are safely reencrypted or expired, and backup/forensic retention policy is satisfied, retire old decrypt material. Missing-key workers must remain unready. Do not remove a key merely eight hours after rotation starts if supported data/backups still need it. A compromised encryption key requires gated incident handling and epoch invalidation/reauthentication; routine reencrypt alone does not undo possible token exposure.

## 5. Startup, health and HTTPS requirements

Keep today's unconditional production refusal until separate release approval. The next implementation can build and test a production configuration path under an isolated qualification harness; it must not use a development-mode override to ship it.

Validate missing/invalid secrets, distinct realm routing, expected schema/epochs/gate generation, canonical HTTPS origin, trusted hosts, root mount, TLS, cookie flags, proxy policy and pool budget before accepting auth traffic. The secure adapter's flag must be fixed at startup; Flask's cookie flag alone does not configure this custom adapter. Host-only cookies must omit Domain. Preserve Lax for top-level email/PKCE callback compatibility. No identity tokens in JavaScript storage.

Separate process liveness from protected readiness. Readiness must require both realms, current gate/writer tuple, compatible crypto/schema, bounded authoritative command/probe support and verified operator configuration status. PING alone is insufficient. A dedicated short-lived non-authority probe prefix may test commands without creating sessions or repeatedly rewriting all live authority; its ACL/design must be reviewed. Operator validation of CONFIG/INFO/persistence belongs to a separate agent, not broad app privileges.

During Redis/control-plane unavailability, readiness is false and protected requests return a fixed 503 before new authority/provider/business work. Retain cookies; do not infer logout, read a replica, switch epoch, or fall back to RAM automatically. Same-incarnation reconnect can recover only through the qualified gate. Storage failure after a dispatched business write is an uncertain business outcome, requiring reconciliation before retry. Genuinely stateless pages/assets may remain available only through an explicitly authority-free path; current Redis mode globally blocks them too.

## 6. Controlled provisioning and rollout (future approvals)

1. Approve the corrective implementation scope; retain startup refusal. Resolve R1–R5 and pass isolated tests in ACCEPTANCE-TESTS.md. Select the provider/topology only after pre-use fencing, cost/capacity, private networking and operating responsibilities are documented.
2. Obtain separate authorization for infrastructure provisioning, budget, region/residency and secret operations. Prepare reviewed declarative configuration with no actual secret values in source. Configure a staging service first; no production connection is authorized by this review.
3. Qualify at least two actual WSGI workers without stickiness, the intended proxy, isolated provider accounts, gate/control plane, TLS and ACLs. Rehearse replica promotion/old snapshot restore, worker restart, saturation, key rotation and rollback. Preserve all test evidence without credentials.
4. Only after approval, provision the production service/gateway/control store with public auth gate BLOCKED, current epochs/ACLs, secret-manager inputs and monitoring. Keep the application release safeguard until its separate final activation gate is explicitly approved. Operator-only qualification must not use or mutate existing production session/destination records.
5. Announce one-time independent sign-in and recovery/verification restart. Drain existing auth/provider operations. Do not mix memory/legacy shared-cookie workers with new shared-store workers, copy old auth handles, or change destination/Environment/photo flags.
6. Coordinate the compatible release/configuration to all workers behind maintenance. Verify root HTTPS/host/proxy/cache rules, current tuple, both realms and allowed operations. Approve release activation separately; never rename development mode to bypass the guard.
7. Open limited acceptance with explicitly authorized A/B accounts. Test account/session behavior only. Live audit-row proof needs a separately approved disposable Draft, checkpoints and cleanup; this phase does not resume Phase 1D.
8. Expand only after the acceptance gates pass and metrics remain within the qualified envelope. Stop on cross-realm authority, stale resurrection, unexplained actor, unsupported writer change, ambiguous business mutation, saturation or secret leakage.

## 7. Rollback and incident stop

Set the independent gate BLOCKED; deny new transitions and protected dispatch, drain/fence old workers and reconcile in-flight provider/business outcomes. Prefer a previously qualified independent/shared-store-compatible release with matching schema, epochs and readable keyring. Reopen only after readiness and acceptance smoke checks.

No such qualified production rollback release is established yet. If none exists at rollout time, the safe rollback is maintenance (and separately supported stateless catalog access), not the old shared-cookie Admin or memory backend. Advance affected epochs if authority must be invalidated. Communicate independent sign-in and recovery restart. A storage rollback or uncertain shared dataset normally requires both epochs to advance.

Retain decrypt-only keys as required by the approved reader/retention policy. Never flush an unrelated Redis namespace, delete audit history, restore destinations/photos, or globally sign out provider accounts as a routine deployment rollback. Keep production gated until the known writer, all current workers, stale-cookie rejection, independent A/B login/logout and correct Admin authority are verified. Record any lost/uncertain response and avoid automatic retry of a destination creation or provider write.
