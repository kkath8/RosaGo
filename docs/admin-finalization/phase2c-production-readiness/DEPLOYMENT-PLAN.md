# Phase 2C — proposed infrastructure, rollout and rollback

**Design only. No infrastructure, environment values, startup guards or production state were changed.** The proposed names below are not settings the current Phase 2B implementation already supports, except ROSAGO_AUTH_MODE and existing Flask/Supabase inputs.

## Required infrastructure and configuration

| Input/capability | Proposed requirement |
| --- | --- |
| `ROSAGO_AUTH_MODE` | Explicit production in the deployment entrypoint; keep current refusal until the reviewed shared path is implemented and validated. Never use development to bypass it. |
| `ROSAGO_SESSION_BACKEND` | redis for the reviewed target; memory allowed only for explicit local testing. No automatic fallback. |
| `ROSAGO_SESSION_REDIS_USER_URL` | Secret rediss connection string for the User namespace/ACL identity. Never log or put in templates. |
| `ROSAGO_SESSION_REDIS_ADMIN_URL` | Separate least-privilege Admin ACL identity, possibly on the same service; required key boundaries validated in integration tests. |
| `ROSAGO_SESSION_NAMESPACE` | Fixed app/environment/protocol prefix; staging and production must not share keys. No request-controlled prefix. |
| `ROSAGO_USER_SESSION_EPOCH`, `ROSAGO_ADMIN_SESSION_EPOCH` | Stable, versioned values managed outside Redis and consistent across workers. Change only through controlled invalidation/recovery. Normal logout never changes an epoch. |
| `ROSAGO_SESSION_KEYRING` | Secret authenticated-encryption keyring with current key ID and approved decrypt-only predecessors. Generate/store in a secret manager after review; no actual keys generated here. |
| `FLASK_SECRET_KEY` | Retain the existing stable secret for other signing/UI-scope uses; identical across workers. Do not reuse as the token-encryption key. |
| `SUPABASE_URL`, existing publishable key | Existing project/issuer, unchanged. End-user bearer clients remain the authority. No service-role or Auth admin key is needed for session storage. |
| `ROSAGO_PUBLIC_ORIGIN` | Exact externally visible HTTPS origin, validated against trusted hosts and proxy topology; actual hostname not supplied in this review. |
| Trusted hosts/proxies | Explicit host allowlist and verified ProxyFix hop counts where needed. Ingress strips client-supplied forwarded headers; no direct public WSGI port. |
| Cookie policy | Startup-fixed secure User root cookie and Admin /admin cookie, host-only, HttpOnly, Lax; no insecure production override. |
| Lifetime policy | Initially 1,800-second idle and 28,800-second absolute normal sessions; 1,800-second pre-login/verification state; recovery remains 600 seconds or its tighter verified token deadline. |
| Limits/timeouts | Explicit bounded capacities, record sizes, pre-auth allocation/login/resend limits, pool size and total command/provider deadlines. Tune against the actual topology; no invented traffic sizing. |
| Durability/failover | No eviction of security state; durable writes and a proven promotion/restore gate. Primary-only authority access; no active-active eventual-consistency mode. |
| Monitoring | Storage errors, conflicts, busy/uncertain refreshes, login denials, expiry/revocation, memory, connections, latency and gate/epoch mismatch. No token/cookie/code/verifier payloads in telemetry. |

The service should be private/restricted to the application, in a suitable region with reviewed data residency and latency. Use TLS certificate/hostname verification, credentials with key/command restrictions and a separate operator identity for management. Application identities must not have configuration/flush/backup administration rights. Configure noeviction and enough headroom; capacity failure must deny new state safely, not evict a revocation fence. Redis documents [ACL restrictions](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/) and [eviction policy behavior](https://redis.io/docs/latest/develop/reference/eviction/).

The implementation must pin supported Redis/client versions and required commands, load/check the reviewed operation definitions, validate namespace/realm mismatch, and explicitly disable unsafe consuming-command retries. Connection pools are worker-local resources over shared records, not inherited open sockets. A successful PING alone is not production readiness.

## Controlled initial rollout

1. **Implementation approval:** approve the Redis contracts, User opaque-browser-state extension, expected one-time reauthentication and test scope. Phase 2D may implement/test locally or against an approved isolated service; production provisioning remains separate.
2. **Infrastructure approval:** select a provider/plan after checking TLS, ACLs, script/atomic-operation compatibility, region, cost, connection limits, persistence and enforceable failover gates. If the gate is unsupported, stop and review the database-backend alternative.
3. **Staging qualification:** use at least two workers without stickiness, the actual reverse proxy, isolated Supabase/test identities and dedicated storage namespace. Pass all ACCEPTANCE-TESTS.md gates, including restart and promotion/restore simulations.
4. **Release review:** confirm root-mounted public topology, production variables/secrets, real provider policy compatibility and rollback version. Preserve the startup safeguard until configuration-backed readiness can prove the shared path. Do not change destination or Environment flags as part of authentication release.
5. **Communicate the initial sign-out:** existing memory-backed handles cannot survive a worker replacement and must not be copied blindly. Users/Admins sign in separately after cutover. In-progress login/PKCE/reset/verification browser state may need a new link/code/flow; provide the existing fixed recovery guidance and safe resend/restart path. Do not delete or recreate Auth accounts.
6. **Maintenance/drain:** stop new authentication/recovery starts during the agreed window; drain in-flight requests/provider writes. Do not keep mixed old shared-session/memory workers and new independent/shared-store workers serving authentication. Short-lived recovery/verification flows can be drained where practical, but no seamless migration is promised.
7. **Coordinated cutover:** deploy the complete compatible release to all auth-serving workers with new protocol/epochs and namespaces. Ignore legacy User/shared-Admin/development cookies as authority. Only a User response may expire the legacy root User cookie; Admin responses never clear it. Retain the Flask signing secret and device-side preferences where possible. Server-side User browser preferences may reset unless a separately reviewed non-authority migration is supplied.
8. **Readiness and limited acceptance:** verify TLS/cookie/proxy behavior and approved real A/B sign-ins without changing memberships or provider settings. Run no business-data mutation by default. A later Admin audit-write proof requires a separately approved disposable Draft and preservation checkpoints; Phase 1D remains deferred.
9. **Observe before expansion:** monitor realm-specific login/refresh/revocation and backend errors, with no global logout or token/credential logging. Stop on unexpected actor, state resurrection, cross-cookie writes or ambiguous data mutation.

After a successful shared-store cutover, ordinary compatible rolling app restarts should retain valid sessions and recovery state under unchanged epochs. Incompatible schema/crypto transitions need an explicit reader-compatibility plan or a planned reauthentication boundary; never dual-write authoritative state into RAM.

## Controlled failover/restore

Do not transparently resume authentication on possibly older Redis data. Gate auth traffic, establish a known writer and durability status, rotate affected realm epochs through the external deployment control plane, update all workers, discard old-epoch authority and reopen only after checks. User/Admin realm epochs can be changed independently for a scoped incident; a shared storage rollback may require both.

A server restart with a provably intact authoritative dataset can preserve sessions under the approved mode. Unknown data loss is a different event and requires forced reauthentication. Snapshot restoration must not revive logouts, consumed PKCE challenges, refresh leases or signup verification state. Do not restore the business database to repair a session-store failure.

## Rollback

1. Stop new auth transitions and drain/reconcile in-flight provider calls and business writes. Never automatically replay a timed-out destination request.
2. Prefer rollback to a previously qualified **independent-session/shared-store-compatible** release that accepts the current protocol/epochs/crypto keys. Preserve records and cookie names when reader compatibility is proven.
3. If no compatible release exists, close Admin/auth functionality with a maintenance response; keep explicitly stateless public catalog pages available where safe. Do not roll back to the old shared-cookie Admin authorization path. Never use development/memory mode as a production recovery switch.
4. If a realm must be invalidated, advance its external epoch and require reauthentication. Explain that invalidating User epoch also invalidates User-owned recovery/verification state. Do not invalidate the other realm for an ordinary per-session logout.
5. Retain shared storage and decrypt-only key versions for any still-supported sessions until their bounded expiry. Do not flush global Redis, delete audit records, restore destination data, or remove unrelated app namespaces.
6. Reopen only after independent login/logout, stale-handle, backend-readiness and cookie tests pass. Record any forced sign-outs and account-recovery restarts. The current memory-only code is not a valid production rollback target.

No rollout, rollback, connection or command in this document was executed.
