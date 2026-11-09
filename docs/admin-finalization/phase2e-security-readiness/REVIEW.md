# Phase 2E — Redis session production readiness and security review

**NO-GO for production Redis provisioning, activation or deployment with the current build. GO for the next corrective implementation and isolated qualification phase, subject to explicit approval.** A provider capability/budget investigation and configuration design may continue without provisioning or connecting production. The Phase 2D PASS meant readiness for this review; it did not certify a production release.

Only this documentation directory was added during Phase 2E. No application, dependency, environment, secret, session, authentication setting, feature flag, SQL or production record was changed. No Redis service was started, provisioned or contacted, and no SQL was executed. Nothing was staged, committed, pushed or deployed. The production startup safeguard remains intact.

## Evidence and scope

All 12 source/dependency/test fingerprints recorded in Phase 2D still match. Migration 0014, the deployed destination-photo contract source and audit-wrapper SQL match the saved byte fingerprints. Prior saved results are 45 real Redis tests; 1,091 Python functions plus 1,371 subtests; 68 JavaScript tests; 17 Chromium checks; and four local server fault checks. Those are **previous local evidence**, not rerun tests or production certification in Phase 2E.

This review inspected the actual adapters, lifecycle functions, credential coordinator/store, CSRF, recovery/verification integration, Admin membership and actor boundary, configuration, tests and Phase 2C/2D reports. New calculations/probes use throwaway Python dictionaries and synthetic token lengths, without importing the Flask application or opening a network connection. Results and fingerprints are in [review-evidence.json](review-evidence.json); [offline_review.py](offline_review.py) reproduces them.

The production host, proxy chain, Redis provider/plan, traffic forecast, worker topology and secret-manager deployment are not available as verified inputs. Their absence is a failed production gate, not evidence of a production vulnerability or permission to guess values.

## Production readiness gates

PASS below applies only to the stated source/local-evidence scope. FAIL means a required production capability is missing or unverified; it does not imply the prior local tests failed.

| Gate | Result | Evidence / outstanding condition |
| --- | --- | --- |
| G01. Reviewed baseline integrity | **PASS** | Phase 2D recorded implementation/test hashes and saved SQL fingerprints match current bytes. |
| G02. Realm namespaces and opaque authority | **PASS** | Namespace/schema/realm/epoch in Redis key and encryption context; 256-bit opaque handles. User/Admin lookup helpers reject the opposite browser realm. Legacy and swapped cookies grant nothing in local evidence. |
| G03. Secure cookie construction | **PASS** | Secure adapter supplies host-only `__Host-rosago_user_session`, Path=/, and `__Secure-rosago_admin_session`, Path=/admin; HttpOnly and Lax. No routine handle reissue. This is construction evidence, not active production configuration. |
| G04. HTTPS / hosts / proxy deployment | **FAIL** | The validator is not wired into startup, ProxyFix/trusted hosts/origin are not configured, and the actual topology is unverified. Local initialization uses `secure=False`; `app.py` also sets `SESSION_COOKIE_SECURE=False`. Neither setting is acceptable as production wiring. |
| G05. Authenticated encryption implementation | **PASS** | AES-256-GCM; random 12-byte nonce; namespace/schema/realm/epoch/key-ID context; whole-document identity/generation integrity; no pickle. Local tamper/key-transition tests exist. AEAD does not establish freshness or prevent rollback. |
| G06. Key lifecycle and production secret controls | **FAIL** | No reviewed secret manager, access policy, all-worker staged key rotation, retirement/compromise procedure or operational qualification exists. These are necessary beyond the tested codec. |
| G07. Atomic creation / rotation / revocation | **PASS** | On one unchanged authoritative writer, one conditional SET replaces the entire realm. Parent/challenge/version/login-operation guards and generic auth-binding protection are present. No provider call occurs in the CAS retry loop. |
| G08. Refresh / expiry / stale-request fencing | **PASS** | Single reservation owner/generation; uncertain or expired refresh burns authority; logout defeats late commit; no RAM authority cache. Deadlines use Redis TIME and logical checks. This assumes trusted, bounded clocks and no dataset rollback; see G14/G18. |
| G09. User A / Admin B, CSRF and recovery | **PASS** | Source and saved local tests preserve separate identity/logout/CSRF, cross-worker PKCE/reset/verification and replay rejection. Conservative shared-mode failures require a new recovery/verification flow. |
| G10. Membership and Admin actor attribution | **PASS** | Fresh database-backed `rosago_is_admin` checks use B's scoped client. The audited destination RPC still derives actor from `auth.uid()`; no client actor parameter was added. Actual production audit insertion is unverified and not authorized here. |
| G11. Request-time Redis outage denial | **PASS** | Typed unavailable handling denies authority before normal request dispatch, retains cookies and never falls back to memory. An already scoped/dispatched provider or database operation cannot be recalled. |
| G12. Startup / readiness / failover enforcement | **FAIL** | Production correctly refuses startup, but there is no production backend/configuration path, writer-incarnation/control-plane gate, or operational readiness contract. Defaulting missing `ROSAGO_AUTH_MODE` to development must be prevented by the production entrypoint. |
| G13. Actual multiworker hosting and restart acceptance | **FAIL** | Saved tests cover two app instances, a separate OS-process storage probe and intact local AOF restart. They do not qualify the real WSGI server, proxy, worker fork/pool lifecycle or rolling deployment. |
| G14. Durable revocation through failover / restore | **FAIL** | Nothing prevents reconnecting to older valid ciphertext under the same epochs if a future production endpoint promotes/restores stale data. Local AOF restart is not a failover proof. The proposed enforceable gate is not implemented. |
| G15. Memory, retention and control-operation admission | **FAIL** | A shared 2 MB plaintext ceiling, 4,096-receipt ceiling and per-family pruning can deny healthy users and even logout. Expired unused families may remain encrypted indefinitely while other traffic refreshes the realm TTL. See measurements below. |
| G16. Throughput and write amplification | **FAIL** | Browser open, anonymous/static traffic and several nominal reads perform whole-realm encrypt/CAS/SET. Same-realm requests contend and generate AOF/replication traffic. No representative load/latency qualification exists. |
| G17. Redis operational configuration | **FAIL** | Production TLS, exact ACLs, noeviction, persistence/failover policy, connection/memory headroom, version/security maintenance and redacted monitoring are unverified. |
| G18. Clock and resource fault bounds | **FAIL** | The Lua freshness test rejects only positive age over 250 ms, not negative age after clock regression. Material clock steps, request deadlines and serialization contention need a defined policy and tests. |
| G19. Destination / Environment / photo / SQL preservation | **PASS** | Saved local business regressions and unchanged SQL bytes support compatibility. This phase did not inspect or mutate live records; it does not recertify production record counts or an actual audit insert. |
| G20. Cutover / rollback / full acceptance rehearsal | **FAIL** | Plans are prepared here; actual staging rehearsal and production release approval remain outstanding. No qualified shared-store rollback release is established. |

## Actual architecture and security findings

`redis_session_store.py:91` implements ciphertext CAS with one SET and a 30,000-second TTL. `RedisRealm.transact` reads/decrypts the complete aggregate, samples Redis TIME, applies a pure calculation, optionally records a 120-second receipt, encrypts and calls EVAL. It retries at most 16 conflicting calculations. There are no partial authoritative secondary writes. Lost mutation acknowledgments are reconciled against the same receipt; uncertain results fail closed and do not repeat a provider call. This is a sound **single-writer atomicity boundary**, not a durability protocol.

`redis_session_flask.py:162` atomically installs new credentials/browser state, revokes the old same-realm credentials and removes the parent. Begin-login reserves one consumed browser-bound challenge with a 30-second operation deadline. Generic save cannot install or replace a live auth binding; per-field CAS merges disjoint UI updates. `shared_logout` removes browser and credential state together. Expiration is logical, not delegated solely to TTL. Refresh coordination retains provider identity/session validation and never steals an expired reservation to replay a possibly consumed refresh token.

The security boundary is server routing and store selection, not cookie Path alone. The root User cookie may be delivered to /admin and is ignored there. HttpOnly and separate paths do not isolate accounts from a compromise of the shared origin or application process. Admin membership is still checked freshly with Admin authority. Local logout does not perform Supabase global sign-out. Provider account-wide/session policies still require read-only release review; cookie independence does not override them. [Supabase documents its session and refresh behavior](https://supabase.com/docs/guides/auth/sessions).

Revocation here concerns RosaGo browser-session authority. It does not globally invalidate an already issued Supabase JWT or cancel an in-flight request. Provider token revocation and account-wide security actions are separate controls; no provider settings were changed in this phase.

AES-GCM appropriately authenticates the whole payload, including its nested identity/generation data. AAD binds namespace, schema, realm, epoch and key ID. Phase 2C's proposed per-record handle/identity/generation AAD was replaced with whole-document binding; that difference is acceptable cryptographically within an intact authenticated aggregate, but offers no freshness protection against replaying an entire older valid aggregate. [The cryptography documentation describes AEAD and nonce requirements](https://cryptography.io/en/latest/hazmat/primitives/aead/).

### R1 — failover revocation is not enforced (release blocker)

An acknowledged logout removes authority only from the current writer's dataset. A promoted lagging replica or restored snapshot can still contain the old live record and a valid encrypted payload. The application has no writer-incarnation/epoch gate to prevent accepting it. Redis explicitly states that asynchronous replication and even WAIT do not guarantee that acknowledged writes survive failover. [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).

`appendfsync always`, replicas and encrypted receipts improve particular failure cases; none replaces an enforceable promotion/restore barrier. [Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/) also distinguishes intact restart from truncated or older recovery. The proposed enforcement and its fault model are in [DEPLOYMENT-PLAN.md](DEPLOYMENT-PLAN.md). No transparent provider promotion is acceptable without a proven pre-use fence.

### R2 — aggregate bounds, retention and admission need correction (release blocker)

An offline serialization calculation used 1,500-character synthetic access tokens, 64-character refresh tokens, fixed-length identities and one small browser binding per credential record. It stored **no receipts, challenges, recovery, email verification, rate counters or meaningful User preferences**:

| Concurrent credential/browser pairs in one realm | Serialized plaintext bytes | Fits 2 MB cap |
| --- | ---: | --- |
| 100 | 219,743 | Yes |
| 500 | 1,098,143 | Yes |
| 800 | 1,756,943 | Yes |
| 1,000 | 2,196,143 | No |

Only 910 pairs fit this narrowly specified scenario. This is not an actual capacity forecast: different token lengths and mutable state change the result; the 49-destination count says nothing about concurrent sessions. The nominal 4,096-record limits do not promise 4,096 usable sessions. More Redis RAM cannot bypass the application cap.

4,096 simple boolean-result receipts alone consume 270,370 plaintext bytes in the synthetic calculation. With 120-second retention, the receipt limit permits only about 34.1 receipt-bearing operations/second sustained per realm under ideal steady assumptions; this is not 34.1 HTTP requests/second. One request may create multiple receipts. At the limit, new receipt-bearing operations, including logout, are rejected before commit until space expires. Richer results can hit the byte cap earlier.

Pruning is per family. The offline probe created an email pending entry, advanced synthetic time beyond expiry, then ran an auth-family prune: the email record remained. Ongoing unrelated requests reset the whole key TTL, so that expired record need not disappear after 30,000 seconds. Logical authorization still rejects expired records when consulted, but retention and available aggregate space are not globally bounded by the TTL claim. Correct the interpretation in Phase 2D's report: TTL exceeds maximum record lifetime but **does not ensure timely per-record garbage collection in an active realm**.

Require aggregate-wide safe deadline reclamation or independently expiring records; per-record/payload/receipt bounds; admission budgeting; and reserved ability to revoke/finalize existing authority at saturation. Never free space by discarding unexpired replay fences or uncertain reservations. A session rotation should account for the replaced parent's space, rather than needlessly fail merely because the pre-rotation record-count limit is full.

### R3 — every browser read becomes a realm-wide write (release blocker)

`SharedSessionInterface.open_session` always calls web.read, including no-cookie and static requests. `RedisModel` disables result receipts for reads but still calls `transact`, encrypts and SETs. Even a no-op lookup changes ciphertext. Every same-realm request therefore competes with other users and can require multiple full-document retries. CSS/image fan-out adds writes unrelated to authentication.

At the 2 MB plaintext bound, encoded ciphertext is at most approximately 2.667 MB. A successful GET + EVAL attempt moves about three ciphertext bodies bidirectionally: approximately 8 MB, excluding protocol/TIME overhead and retries. Ten successful full-size replacements/second imply roughly **2.30 TB/day of SET value payload** before AOF rewrite/compaction effects; this is a calculation, not a measured disk-consumption forecast. Persistence, replication and retries further determine cost and latency. The two stored values' small total size is misleading as a service-sizing metric.

Remove auth-store access from genuinely stateless/static routes without granting fallback authority. Design primary-only non-mutating lookups where appropriate and keep final authorization/refresh transitions atomic. Prefer bounded per-record/transaction-group state unless measured workload and admission controls justify an aggregate exception. Do not solve this by accepting replica/local-cache authority or skipping revocation checks.

### R4 — production configuration and health path are absent (release blocker)

`session_realms.py:206` correctly raises for production. The only Redis factory accepts numeric loopback `redis://` connections. That is a good local restriction, not production TLS support. `validate_https_configuration` is a pure helper; it is never called by application startup. `ROSAGO_PUBLIC_ORIGIN`, `ROSAGO_SESSION_BACKEND`, trusted proxy hops and a production gate/health integration are not implemented deployment inputs. A missing mode currently defaults to development; the production launcher must reject that.

Keep the guard unchanged in this phase. A later authorized implementation must provide a validated production path behind the still-closed release gate, with per-worker pools, exact HTTPS/host/proxy checks and operational readiness. [Flask warns that forwarded headers can be spoofed unless proxy trust is configured correctly](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/); its [configuration documentation](https://flask.palletsprojects.com/en/stable/config/) defines trusted hosts and cookie controls.

### R5 — clock/resource assumptions and incomplete deployment tests

Redis TIME avoids cross-worker monotonic-clock serialization, but is a wall clock. The CAS age condition does not reject negative age. Define accepted skew and enforce material-regression handling; a large clock rollback must gate authentication and trigger investigation/epoch invalidation rather than extend authority silently. Coordinate provider-JWT checks with synchronized worker clocks. Treat the 250 ms snapshot budget and 30-second operation/refresh deadlines as qualification inputs, not measured production SLOs.

The existing complete business regression suite uses development adapters. Only the explicit Redis tests and browser fixture exercise the new shared path. Before release, run relevant account/settings/recovery/destination/photo/Environment regressions with shared adapters and the real target proxy/WSGI topology. The separate-process storage probe is not a full multi-process HTTP deployment test. Test ACL denial inside scripts as well as direct GET; the saved cross-realm ACL test stops at the direct GET denial.

Delayed obsolete Set-Cookie or logout responses can still replace/clear the browser's newer cookie. Server authority is not resurrected, but the affected realm can require deliberate sign-in. Keep this disclosed, never silently import stale cookie authority, and test both response orders. Storage failure after an already committed business mutation still requires reconciliation, not automatic resubmission.

## Required corrections before production qualification

| ID | Required work | Expected affected files/components |
| --- | --- | --- |
| C1 | Implement and qualify an external durable failover/control-plane gate with pinned writer incarnation and epoch fencing. A webhook after promotion is insufficient. | New deployment/gateway/control-plane integration; store/startup/request boundary. |
| C2 | Resolve R2/R3: bounded transaction groups or justified aggregate design; safe all-family expiry cleanup, size/admission/control-operation reserves and stateless/static bypass. | `redis_session_store.py`, `redis_session_flask.py`, store protocols and shared-mode tests. |
| C3 | Implement production config validation, verified TLS, per-realm ACL routing, explicit entrypoint mode, safe worker pool initialization and readiness. Keep release safeguard closed until separately approved. | `session_realms.py`, Redis factory, `app.py`, deployment entrypoint/configuration, new health support. |
| C4 | Wire canonical origin/trusted hosts/exact proxy hops, production secure adapter configuration and cache/HTTPS rules. | Startup/WSGI/ingress configuration; cookie acceptance tests. |
| C5 | Define schema/key compatibility, two-stage key distribution/rotation, retirement and compromise handling through a secret manager. | Deployment secret integration, crypto configuration validation and rotation tests/runbook. |
| C6 | Bound clock regressions, serialization/command/provider deadlines, capacity/denial behavior and redacted observability. | Store/coordinator/configuration/monitoring and fault tests. |
| C7 | Qualify actual multi-process workers, shared-mode User/business regressions, saturation/restart/failover/restore/rollback and delayed-response behavior. | Tests and isolated staging harness; no production business writes by default. |

## Differences from the approved Phase 2C design

| Phase 2C contract | Phase 2D reality | Disposition |
| --- | --- | --- |
| Separate mutable User browser state | Implemented opaque server-side User cookie/state. | Approved extension met. |
| Bounded record lifecycle with identity/generation AAD | One encrypted aggregate per realm; nested identity/generation authenticated together, no per-handle Redis key. | Cryptographic binding is sound in its scope; aggregate capacity/retention/write cost not approved for production. |
| Atomic related authority records / receipts | One conditional SET rather than MSET across record documents. | Atomic single-writer grouping is valid; no SQL-style rollback claim is needed after its one commit. |
| Separate lifecycle/result categories | Generic adapters return legacy booleans/None or typed unavailable; no complete public operation-status protocol. | Maintain explicit uncertain/busy/conflict behavior; formalize typed contracts during correction. |
| Shared recovery and verification with uncertain outcomes | Shared stores; conservative grant/code consumption and verification busy fence. | Safe stricter retry behavior; deliberate flow restart must remain visible. |
| All bounded expiry state reclaimed | Only consulted family prunes; aggregate TTL refreshed by other families. | Correction required, not an accepted production deviation. |
| Controlled durable failover/epoch readiness | Environment epochs exist, enforcement does not. | Blocking gap. |
| Production TLS/secure startup/host/proxy policy | Testable secure adapter and pure helper; no production factory or wiring. | Deliberately withheld activation; implementation qualification still required. |
| Qualified multiworker deployment | Local two-instance/browser and OS-store tests. | Useful evidence, insufficient for deployment approval. |

Infrastructure, key/epoch controls and procedures are in [DEPLOYMENT-PLAN.md](DEPLOYMENT-PLAN.md). Required acceptance gates are in [ACCEPTANCE-TESTS.md](ACCEPTANCE-TESTS.md).

**Decision:** approve corrective work and isolated qualification as the next step if desired. Do not provision/connect production Redis or authorize deployment on the basis of Phase 2D's local PASS. No readiness FAIL is waived by this review, and the production startup safeguard must remain active.
