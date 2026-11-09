# Phase 2C — independent session production readiness

**GO for Phase 2D implementation and isolated integration testing after approval. NO-GO for production deployment of the current memory-backed code. Keep the production startup safeguard intact.**

This is inspection and design only. No application code, dependencies, environment values, authentication settings, production sessions, database records, grants or policies were changed. No application/production endpoint, Redis server, Supabase account or SQL was exercised. No staging, commits or pushes occurred.

## 1. Evidence and present implementation

All application SHA-256 values in Phase 2B's saved verification summary still match. Its 1,091 Python tests, 1,371 subtests, 68 JavaScript tests and 17 browser checks are existing local evidence, not new production tests. This phase reviewed `session_realms.py`, `admin_session_flask.py`, `user_csrf.py`, normal-auth stores/coordinator/Flask integration, Admin authorization/routes, application cookie/login/logout/recovery routes, recovery and email-verification stores, and acceptance tests. No production hosting origin, proxy chain, worker count, traffic volume, Redis plan or budget was available for independent verification.

The realm boundary is sound in the inspected implementation:

- Exact `/admin` and `/admin/...` paths select only the Admin opaque-cookie adapter; the signed root User cookie is ignored there. Other paths use only User sessions. `/administrator` is not Admin.
- User handle lookup and establishment explicitly reject Admin browser sessions. Admin handle lookup rejects User mappings. Credential stores are separate instances. Admin service contexts require server-assigned realm=admin.
- Admin candidate membership is checked before session installation and on protected requests with the candidate/current Admin bearer token. The public audited mutation wrapper still derives its actor from `auth.uid()`; no browser-supplied actor field exists.
- Login challenges are single-use and purpose-bound. Logout, CSRF failures, expiration, recovery references and malformed/duplicate Admin cookies do not select the opposite realm.
- Request-owned SDK clients retain verified issuer/subject/provider-session binding and disable implicit persisted SDK sessions/automatic refresh. No global provider sign-out was introduced.

This establishes the inspected/local boundary, not a production penetration test. Browser cookie Path narrows delivery but is not an origin boundary against same-origin XSS.

## 2. Recommended architecture and backend decision

**Preferred implementation target: one dedicated, managed, single-writer Redis-compatible security-state service, with separate User/Admin namespaces and preferably separate least-privilege ACL identities.** Keep the existing Supabase Auth verification, normal authenticated JWT role, fresh database membership and audited RPC contracts. Redis becomes session authority storage, not a replacement identity provider.

The service must support bounded atomic operations, TLS with certificate verification, reliable persistence, primary-only authority reads, controllable recovery/failover, noeviction, monitoring and sufficient connection/memory headroom. Use a maintained, pinned synchronous redis-py client selected and tested during Phase 2D. No Redis dependency or service is installed here.

| Option | RosaGo fit | Decision |
| --- | --- | --- |
| Managed Redis with reviewed durability/failover controls | Native expiration and atomic state transitions fit auth, CSRF, recovery, signup throttles and multiworker coordination. Avoids adding credential-bearing tables or grants to the business database. Adds an infrastructure dependency and requires careful failover treatment. | Preferred implementation target, conditional on the capability gates below. No provider or paid plan selected. |
| Dedicated private PostgreSQL session tables | Transactional conditional updates/row locks are a viable alternative and can reduce separate-service count if the existing platform has adequate capacity. Requires a separately reviewed private schema, least-privilege server connection, pooling, encrypted credential columns and migrations. Never use the exposed public schema or modify Supabase `auth.sessions`. | Explicit fallback if a suitable Redis service/failover gate is unavailable; not an automatic runtime fallback. |
| Filesystem, SQLite, process dictionaries or sticky workers | Do not provide the required shared lifecycle, durable revocation and worker failover contract. | Not production options for this design. |
| Generic Flask-Session/default Redis session serialization alone | Does not implement cross-record login, provider refresh fencing, purpose-bound challenge consumption or business-response ambiguity handling. | Insufficient by itself. |

This selection is an engineering inference from RosaGo's current interfaces, not a measured capacity or price recommendation. Hosting region, provider capabilities and budget must be reviewed before provisioning. PostgreSQL's [row-locking mechanisms](https://www.postgresql.org/docs/17/explicit-locking.html) support the fallback, but no SQL schema or execution is included in this phase.

### Mandatory Redis durability boundary

Lua provides serialized execution; it does not make Redis immune to persistence loss. Redis documents that asynchronous replicas can lose acknowledged writes during failover and that WAIT does not establish strong consistency. Losing a logout or challenge consumption can revive authority or replay a provider refresh, which is more serious than losing ordinary cached data. See [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).

Therefore require one of these **reviewed deployment capabilities**, before production is allowed:

1. A provider-documented durability/failover mode whose acknowledged security writes cannot roll back under the accepted fault model, verified through recovery tests; or
2. Controlled promotion/restore: authentication is gated closed before restored/promoted data is served, affected realm epochs are changed in a durable deployment control plane outside Redis, all workers adopt the new epochs, and all affected sessions must reauthenticate before reopening. No transparent promotion of potentially stale authority is allowed. The provider/gateway must make this enforceable, not merely send a notification after stale data has served requests.

If neither is enforceable, **do not deploy this Redis design**; review the transactional backend alternative and its own durability/failover guarantees. AOF fsync-every-write is preferred for security state where available, but does not alone prove safe replica promotion. Default every-second persistence can lose recent writes, as described in [Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/). Restoring a backup never reopens old auth epochs automatically. Do not store the only authoritative epoch/failover gate in the dataset that can itself roll back.

## 3. Production gaps requiring Phase 2D changes

| Finding | Production risk | Required mitigation |
| --- | --- | --- |
| All credential, web, login challenge and rate state is process-local | Worker switching/restarts lose sessions; independent workers can refresh the same token or bypass local throttle counters. | Shared adapters for both realms and all authentication-related transient stores. |
| Root User cookie still serializes mutable state | A delayed response can overwrite auth/recovery/preferences from a newer response. Moving only credential records to Redis leaves this race intact. | Move User browser state server-side behind a stable opaque cookie as described below. |
| Creation/rotation/logout span separate store calls | Distributed timeout/crash can leave orphan or inconsistently linked records; client-side compensating deletion can target a completed operation. | Atomic same-realm transition contracts with versions, parent lineage and receipts. |
| Existing refresh reservations have no distributed crash protocol | A naive expiring Redis lock can permit a second refresh while the first provider call is still running. | Refresh-in-progress state; lease expiry becomes uncertain/revoked, never automatic second refresh. |
| Recovery, verification and resend maps are also local | A callback may reach a worker without its PKCE verifier; retries can exchange codes or verify/send twice. | Shared, purpose-bound reservation/consume state and explicit ambiguous-provider-result handling. |
| `SESSION_COOKIE_SECURE=False` and no reviewed proxy/host policy | HTTP cookie exposure, wrong callback URLs, Origin failures or spoofed forwarded values. | Startup-fixed production cookies, HTTPS ingress, trusted hosts and exact proxy trust. |
| Memory web-save errors become 409/503 at response end | Session/flash failure can mask an already committed destination mutation and invite duplicate resubmission. | Separate auth-critical transitions from UI notification state; no automatic business retry; preserve/reconcile known committed outcomes. |
| Current adapter catches RuntimeError, not a defined shared-backend error contract | Redis outages could be mislabeled as logout, surface 500 or trigger unsafe fallback. | Typed unavailable/conflict/expired/uncertain results and fail-closed route handling. |
| Production mode blocks startup; default mode is development | Omitting deployment mode could run development settings on a public host. | Require explicit production mode in the deployment entrypoint and readiness tests. Preserve the existing block until the shared path passes gates. |
| Actual topology and origin are unknown | Root-path cookie rules/proxy trust cannot yet be certified. | Deployment manifest review is a release gate. No guessed proxy hop count. |

### Explicit proposed extension: User browser state

Phase 2B intentionally retained the signed User cookie. For robust multiworker production, recommend a versioned opaque server-side User browser session too, preserving User URLs, login/recovery UX and realm semantics. This is a **proposed Phase 2D scope extension requiring approval**, not an already implemented change.

Recommended production names: `__Host-rosago_user_session` at `/` and `__Secure-rosago_admin_session` at `/admin`. Both are host-only, Secure, HttpOnly, SameSite=Lax. Random browser IDs select realm-specific shared web state; that state references realm-specific credential records. No mutable auth reference, recovery reference or flash payload is rewritten into browser cookies on ordinary requests. Keep Flask's signing secret stable for its other uses, including existing personal UI scopes.

Unknown, malformed, duplicate, legacy or cross-realm cookies grant nothing. Do not silently import legacy `auth_session_id` into Admin or populate shared credential records from browser data. Initial cutover deliberately requires fresh authentication and restarts in-progress browser-bound recovery/verification flows. If preserving the existing signed User-cookie format is required instead, Phase 2D needs a different reviewed stale-response solution; simply changing NormalAuthStore to Redis is not sufficient.

## 4. Shared data and atomic lifecycle contract

Move all of the following to the reviewed backend: User/Admin credential records, User/Admin browser records, login challenges, login attempt/pre-auth allocation limits, recovery PKCE pending state and reservations, recovery grants/replay markers, pending email verification state/resend limits. Leave business destinations/photos/audit records in Supabase. Other process-local product features, such as assistant conversations, need their own scaling review; this proposal does not claim to make every application feature multiworker-ready.

Use fixed-schema JSON/bytes, not pickle or browser-deserialized Python objects. Bound record sizes and capacities. Encrypt access/refresh tokens, recovery access tokens and PKCE verifiers using application-side authenticated encryption with a secret keyring outside Redis. Bind credential ciphertext to realm, schema, realm epoch, handle digest, verified user/provider-session identity and credential generation. Redact tokens, raw cookies, passwords, keys, codes and verifier material from logging/tracing. Redis remains a trusted security-state dependency; encryption does not independently solve rollback of old valid records.

Key namespaces include deployment, protocol version, realm and externally managed epoch. Hash random handles before using them as key material. All keys involved in one atomic transition must be on one writer/shard. Start without Redis Cluster; a later cluster design must colocate each atomic group with appropriate hash tags and be reviewed. Never rely on Redis database numbers as the realm-security boundary.

Each authoritative record has immutable realm/schema/epoch/identity binding, state, credential generation, browser lineage generation, creation time, last authorized activity, absolute/idle deadlines and, if applicable, reservation owner nonce/deadline/operation ID. Expiration checks use shared server UTC time; do not serialize process-relative monotonic timestamps into the shared backend. Preserve 30-minute idle and 8-hour absolute semantics. Key TTL is garbage collection, not the sole authorization check.

| Operation | Atomic preconditions and result |
| --- | --- |
| Allocate pre-login state | Enforce realm/address capacity and rate policy; create unpredictable browser ID and challenge with 30-minute deadline. Browser input cannot choose an authenticated ID. |
| Begin login | Match browser lineage, current version, realm and challenge deadline; consume once and reserve one login operation. A concurrent submit cannot issue another provider call under the same challenge. |
| Finish login | After verified password credentials and, for Admin, current membership, recheck live parent lineage/version/login operation and candidate expiry; atomically activate new credential/browser records, invalidate replaced same-realm authority and record operation receipt. Logout/revocation of the parent while Auth was in flight rejects this commit. |
| Authenticate/touch | Require both browser binding and credential record active, matching realm/epoch/generation and unexpired deadlines. Atomically touch only the selected realm, never extending absolute expiry. No worker-local positive authority cache or replica read. |
| Reserve refresh | CAS active generation to refreshing with unique owner nonce/operation ID and a bounded deadline. Other requests return busy/retryable without a second refresh or logout of the other realm. |
| Commit refresh | Revalidate provider issuer/subject/session_id/expiry exactly as current code. CAS the same live record, epoch, generation and nonce; replace encrypted credentials, increment generation and store receipt. Revocation wins against late completion. |
| Refresh deadline/crash/ambiguous provider response | Transition to uncertain/revoked for that auth record and require fresh sign-in. Do not reuse a possibly consumed provider token when a lease expires. Healthy unrelated sessions remain independent. |
| Same-realm logout/revocation | Atomically invalidate the binding/credentials and outstanding login/refresh lineage, retaining a bounded tombstone or equivalent fence. Expire only that realm's cookie after acknowledged local revocation. |
| Browser UI state | Use per-field CAS or a separate versioned notification queue; never write back a stale whole session snapshot or modify an auth reference through generic session save. No cookie reissue for routine reads/flashes. |
| Recovery/verification | Atomically reserve/consume the correct purpose-bound record, enforce actor/provider-session binding and deadlines, and reject cross-worker replay. Provider writes/exchanges occur outside storage transactions and have explicit uncertain outcomes. |

Do not hold a distributed lock while making a network call. A lease/generation fence only prevents stale **storage commits**; it cannot stop an old worker from finishing a provider request. In particular, lease expiration must not make a consumed refresh token available to a new owner. Supabase's documented reuse exceptions are not a substitute for coordination. Preserve current provider validation and do not change project Auth settings to mask races. See [Supabase session/refresh semantics](https://supabase.com/docs/guides/auth/sessions).

### Atomicity and error handling

Use bounded, reviewed Lua/Redis Functions or conditional transactions for explicit operations, not a Redis lock around the existing series of Python dictionary calls. Validate all expected versions, record types, state, capacity, identity and expiry before authority writes. Redis scripts serialize execution, but Redis does not provide general SQL-style rollback after runtime command errors; see [transactions](https://redis.io/docs/latest/develop/using-commands/transactions/).

For related authoritative string documents, a validated script can make its commit using a single atomic MSET containing the new state, old-state tombstone and receipt, with logical deadlines already embedded. Subsequent TTL/secondary-index work is cleanup and must not change whether authority committed. MSET's all-key atomic semantics are documented [here](https://redis.io/docs/latest/commands/mset/). This is a design contract, not an implemented script; OOM, wrong-type, partial cleanup and durability fault tests are required. Never mark a partially prepared record authenticated, and never recreate an absent parent from a stale snapshot.

Use result categories such as APPLIED, ALREADY_APPLIED, CONFLICT, EXPIRED, REVOKED, BUSY, UNAVAILABLE and UNCERTAIN. Operation IDs/receipts make **storage** reconciliation safe after lost acknowledgments. Disable implicit retries for consuming or authority-changing commands; bounded idempotent retry/reconciliation must be explicit. The official [redis-py production guide](https://redis.io/docs/latest/develop/clients/redis-py/produsage/) documents client retries and timeouts, which must be deliberately configured rather than accepted blindly.

Redis failure before authority lookup means 503/retry, no provider refresh, no business dispatch and no clearing of either cookie. Do not fall back to RAM, accept a stale snapshot, or infer signed-out and replace authority on an outage. An ambiguous logout must not report success or revoke the opposite realm; close the affected request scope and reconcile the operation before another protected action. Public stateless catalog views may remain available through an explicit no-authority path; they must not obtain a memory-backed authentication fallback.

Redis and Supabase business writes are separate systems. Do not claim exactly-once destination creation from an auth operation receipt. A business response lost after commit must be investigated using its known destination/audit evidence before retrying. Benign flash conflicts must not turn a known successful mutation into a misleading invitation to resubmit. Logout cannot cancel an already-dispatched database request; new dispatch after acknowledged revocation is denied.

## 5. Cookies, HTTPS and root mounting

| Property | Production requirement |
| --- | --- |
| User cookie | Proposed `__Host-rosago_user_session`, opaque, Path=/, Domain omitted |
| Admin cookie | `__Secure-rosago_admin_session`, opaque, Path=/admin, Domain omitted |
| Both | Secure=true, HttpOnly=true, SameSite=Lax; browser-session cookies with server-enforced expiry |
| Duplicate/malformed values | Reject for both realms; never choose a cookie by order or parse the other cookie as fallback |
| Set/Delete | Same name/path/domain attributes; no cross-realm Set-Cookie; ordinary requests do not reissue stable handles |
| HTTP | Ingress redirects before app authentication; app not directly public over HTTP; no insecure production cookie fallback |
| Host/proxy | Explicit canonical public origin, Flask TRUSTED_HOSTS, exact trusted proxy hops if ProxyFix is needed; strip/overwrite untrusted forwarded headers at ingress |
| Caching | Auth, CSRF token, recovery, account and Admin responses private/no-store; credentials not exposed through cross-origin CORS; CDN bypass for these paths |

Lax is deliberate: an email/PKCE top-level GET callback must retain the browser-bound recovery state. Strict should not be substituted without recovery testing. It does not remove the need for synchronizer tokens and same-origin mutation checks. The User logout-token endpoint remains User-only, same-origin readable, no-store and not an authorization fallback. Cookie prefix rules are described in [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

The current code is **compatible with a dedicated root-mounted hostname**, subject to the other changes. Prefix support is not inherently required; retain the current rejection until the actual topology is confirmed. If hosting uses a prefix, both externally visible cookie paths, route matching, callbacks and hardcoded frontend URLs such as /logout and /auth/logout-token need coordinated changes/tests. Setting X-Forwarded-Prefix alone is insufficient. Configure ProxyFix only for verified proxy counts; [Flask's guidance](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/) warns that the forwarded values must be trusted correctly. [TRUSTED_HOSTS and cookie settings](https://flask.palletsprojects.com/en/stable/config/) must be fixed at startup.

## 6. Multiworker, restart and provider compatibility

All workers use the same protocol, realm epochs, encryption keyring and shared authority stores. Create connection pools after fork/per worker with a total connection budget. Health checks verify more than PING: expected primary/writer routing, script/version support, ACLs, persistence/noeviction configuration and external failover gate. Backend unavailability closes protected readiness without silently changing stores. Never read revocation state from replicas or a local positive cache.

An ordinary app-worker restart under the same compatible protocol/epochs must preserve valid sessions, deadlines, login challenges, PKCE grants and verification cooldowns. A backend crash, promotion or restore is a separate durability event, handled by the failover gate above. Expired or revoked sessions never return merely because another worker or backup has older state.

Keep current password-only verified normal sessions and recovery-only grants distinct. No auto-login from email verification or reset into either realm. Admin Forgot password may continue to the existing account-recovery flow and require separate Admin sign-in afterward. Preserve fixed error copy, replay protection, no credential/query logging, local logout behavior and no global provider sign-out. The installed Python SDK defaults sign_out to global; [Supabase's sign-out guidance](https://supabase.com/docs/guides/auth/signout) explains why scope must be explicit if provider revocation is added later.

Project single-session/password-security policies are unverified here and may invalidate the same account's sessions. Two distinct accounts A/B do not require weakening them. Review actual settings read-only before release; do not promise cookie separation overrides account-wide security actions.

## 7. Files affected by future implementation

Only this documentation directory is added in Phase 2C. Future Phase 2D work would affect:

- `session_realms.py`: injectable shared browser/challenge adapters for both realms, production cookie configuration, typed backend failures, CAS/notification separation and startup validation.
- `admin_session_flask.py`, `normal_auth_flask.py`: atomic realm lifecycle operations, independent revocation/rotation and compatible new User browser references.
- `normal_auth_store.py`, `normal_auth_coordinator.py`: store protocol plus shared implementation; distributed refresh/uncertain states; preserve claim checks and request-owned SDK clients.
- New storage/codec/lifecycle modules, such as `session_store.py`, `redis_session_store.py`, `session_crypto.py`, and bounded reviewed transition definitions. Names are proposals, not created code.
- `user_csrf.py`, `admin_routes.py`, `app.py`: shared purpose state, production config, backend-aware availability and proper post-mutation response semantics.
- `recovery_helpers.py`, `email_verification.py`: shared PKCE/grant/replay/verification/resend adapters with preserved purposes and provider uncertainty handling.
- User/Admin templates and `static/js/user-ui.js` only where cookie transition or configured URL/mount handling requires it; no new auth token storage in JS.
- `requirements.txt`, deployment entrypoint/configuration and tests: pinned client, multiworker/fault/restart/browser suites. No production service is provisioned by a code patch.

`admin_authorization_service.py` and Admin context guards should preserve their realm/member contract; changes, if any, are injection/validation only. No change is proposed to destination RPC signatures, migration 0014, photos, weather exposure, Admin memberships, audit schema/history or catalog publication policies. The Redis target needs no RosaGo SQL migration. A PostgreSQL fallback would require its own reviewed schema and credentials before any SQL authorization.

Infrastructure/configuration and release procedures are in [DEPLOYMENT-PLAN.md](DEPLOYMENT-PLAN.md); required acceptance gates are in [ACCEPTANCE-TESTS.md](ACCEPTANCE-TESTS.md).

## 8. Decision

**GO for Phase 2D implementation and isolated fault/integration testing of the specified contracts, after explicit approval.** Approval should include the proposed server-side User browser-state transition and initial reauthentication behavior. It does not authorize purchasing/provisioning Redis, accessing production sessions, changing provider settings, executing production SQL or deploying.

**Production remains NO-GO** until the shared adapters, failover/revocation capability gate, cookie/proxy topology, encryption/secrets, all auth-related state migration and acceptance tests are complete. If the Redis provider cannot meet the failover gate, return for explicit backend selection rather than silently switching designs or disabling the startup safeguard.
