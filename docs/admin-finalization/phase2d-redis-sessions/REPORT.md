# Phase 2D — Redis independent sessions: implementation and local verification

**PASS / GO for Phase 2E independent readiness review. Production deployment remains NO-GO.** The production startup safeguard still unconditionally rejects `ROSAGO_AUTH_MODE=production`. This report does not approve its removal, production Redis provisioning, or production testing.

The authorized User server-side state extension is implemented. The local opt-in is `ROSAGO_AUTH_MODE=redis-local`; existing development tests retain their memory adapters. Redis mode never falls back to those adapters. Only numeric loopback Redis URLs are accepted by the local factory. No production credentials, sessions, SQL, destinations, feature flags, authentication settings, photos, or Storage objects were accessed or changed. Nothing was staged, committed, pushed, or deployed.

## Files changed in this phase

| Files | Change |
| --- | --- |
| `redis_session_store.py` (new) | Encrypted Redis documents, atomic CAS/receipts, separate realm adapters, distributed credential refresh reservations, shared challenges/throttles, recovery and verification adapters. |
| `redis_session_flask.py` (new) | Opaque User/Admin browser adapters, per-field UI CAS, atomic login/rotation/logout, HTTPS configuration validator. |
| `session_realms.py` | Explicit local Redis initialization, early unavailable-cookie response, invalid-cookie handling for both realms; production safeguard retained. |
| `normal_auth_flask.py`, `admin_session_flask.py` | Shared store selection and atomic lifecycle integration, with explicit opposite-realm helper rejection. |
| `normal_auth_coordinator.py` | Preserve refresh fences when a Redis commit/revocation outcome is uncertain; never release a possibly consumed refresh token for another worker. |
| `user_csrf.py`, `admin_routes.py` | Consume the correct login challenge and reserve its browser lineage before calling the provider. Destination mutation logic is unchanged. |
| `app.py` | Select shared recovery/email adapters; uncertain shared verification requires a new verification flow. |
| `email_verification.py` | Optional uncertainty flag retains the busy fence after an ambiguous provider result. Existing development behavior remains unchanged. |
| `requirements.txt` | Add pinned `redis==6.4.0`; existing `cryptography==50.0.2` supplies AES-GCM. Preserve the file's existing UTF-16 encoding. |
| `tests/test_redis_sessions.py` (new) | Opt-in real Redis, two-app, separate OS-process, concurrency, lifecycle, recovery, security and fault tests. |
| This directory | Report, local instructions, reproducible fault/browser fixtures, results, screenshots and verification fingerprints. |

Earlier worktree edits were preserved. A whole-worktree Git diff also includes earlier phases; it is not the change list for Phase 2D.

## Actual architecture and atomicity

The root-mounted path selects the realm: exact `/admin` or `/admin/...` accepts only Admin browser state; all other paths accept only User state. User and Admin use separate Redis keys, credentials, CSRF purposes, session epochs and configurable client/ACL identities. Cookies are never a source of identity, provider credentials, membership, or audit actor UUIDs.

Qualification cookie names are `rosago_user_session_dev` at `/` and `rosago_admin_session_dev` at `/admin`. The secure adapter uses `__Host-rosago_user_session` and `__Secure-rosago_admin_session`, respectively, with Secure, HttpOnly, SameSite=Lax and no Domain. IDs contain 256 bits of randomness. Mutable User state, including recovery references, settings and flashes, resides server-side. The old signed `session` cookie is ignored in Redis mode; it is not imported as authority.

**Implementation choice requiring Phase 2E review:** one encrypted, bounded aggregate per realm, rather than separate Redis keys for every record. Its key is `<namespace>:sessions:v1:<realm>:<external-epoch>`. Handles and nested identity/generation fields are inside authenticated encrypted JSON, never Redis key names. A pure Python transition reads/decrypts state and proposes a replacement. A short Lua script compares the exact ciphertext and makes one `SET ... EX 30000` authority commit. It rejects snapshots older than 250 ms and retries conflicting pure calculations at most 16 times. No provider operation runs in that loop. There are no secondary authority writes or post-write cleanup commands whose failure could leave a partially installed login.

This makes same-realm credential creation, browser rotation, replacement revocation and logout one atomic document replacement. Successful login requires the live parent version, a consumed purpose-bound challenge, the matching login-operation nonce, a 30-second operation deadline, and unexpired verified credentials. Revoking the parent defeats a late login completion. Logout removes the browser binding and credential authority together. Old browser saves cannot recreate deleted state or change a live credential binding.

Browser saves compare changed fields against their original values and merge disjoint UI changes. Conflicting substantive changes return 409 without a cookie update. A cosmetic flash conflict preserves the business response and adds a notification-conflict header. A storage failure after a business write can still produce an uncertain response: reconcile the business outcome before retrying. This is not an exactly-once destination-write protocol.

Shared Redis TIME supplies lifecycle deadlines. Credential idle/absolute limits remain 1,800/28,800 seconds. Logical expiry is checked independently of Redis TTL. The 30,000-second aggregate TTL is garbage collection beyond the longest supported record lifetime. Challenges, recovery, verification cooldowns and login/allocation rate counters are shared. Capacities are bounded; plaintext documents are capped at 2 MB; receipts are capped at 4,096 and expire after 120 seconds. Read results do not create credential-bearing receipts.

Refresh reservation has a single nonce/generation owner and a 30-second deadline. Another worker gets busy, not another provider call. Expired reservations burn the affected auth record; they are never stolen to reuse a possibly consumed refresh token. Commit checks the owner, generation and identity/provider-session validation already enforced by the coordinator. Logout defeats late refresh commits. Unknown storage outcomes retain the fence and require reconciliation or reauthentication. An already dispatched provider/database request cannot be cancelled by logout.

Authority-changing operations keep encrypted operation receipts. A lost Redis acknowledgment is reconciled against the same operation; it never causes another provider call. If reconciliation cannot establish the result, the request fails closed. Read uncertainty also fails closed. Client command retries are explicitly disabled. There is no positive worker-local authority cache, replica authority path, or RAM fallback.

## Encryption and recovery behavior

AES-256-GCM uses a new 96-bit nonce for each document replacement. Authenticated context includes namespace, schema, realm, externally supplied epoch and key ID; the complete identity/generation-bearing document is authenticated together. Copying User ciphertext into Admin state, changing its context, or altering ciphertext fails closed. Credentials, PKCE verifiers, recovery grants, CSRF state and email addresses are encrypted at rest. Fixed-schema tagged JSON uses only explicitly allowed dataclasses; there is no pickle deserialization.

The keyring supports a current encryption key and decrypt-only predecessors. It is supplied through environment/secret injection, separate from `FLASK_SECRET_KEY`. All test encryption keys are generated in memory; none are saved in source, results, screenshots or configuration files. No session IDs, bearer credentials, keyring contents or recovery secrets are intentionally logged.

Shared PKCE and password-reset reservations are consumed conservatively on failure/uncertainty; request a new recovery link instead of replaying a potentially consumed operation. Unknown email-verification outcomes retain their busy fence and direct the user to restart registration/verification. Explicit known verification errors retain the established cooldown behavior. These stricter shared-mode retry rules are deliberate differences from memory development mode. Reset and verification never install User or Admin login authority.

## Local results

| Gate | Result and evidence |
| --- | --- |
| Real Redis integration | **PASS — 45 tests**, Redis 7.4.7 / redis-py 6.4.0; includes shared authority from a separately spawned Windows process and two independently constructed Flask apps. `redis-test-results.xml`. |
| Both login orders and independent logout | **PASS** across alternating app instances; old handles cannot authenticate after logout. |
| Expiration, revocation, refresh races | **PASS**: independent idle/absolute expiry, one refresh owner/provider call, expired-lease terminal behavior, late refresh rejection, unknown-commit fencing. |
| Stale browser/login requests | **PASS**: per-field merges, same-field conflict rejection, logout wins against in-flight login, revoked state cannot be recreated. |
| CSRF, realm authority, membership | **PASS**: cross-realm login/logout tokens rejected; swapped, duplicate, malformed and legacy cookies grant nothing; nonmember denied; fresh membership uses Admin bearer credentials. |
| Recovery and verification | **PASS**: cross-worker PKCE callback/reset, replay rejection, shared verification/resend state and Admin preservation. Existing recovery/account tests also pass. |
| Attribution | **PASS locally**: while A remains User, the Admin mutation carries B's bearer token and no client actor parameter; stored Admin identity is B. Actual production audit insertion remains untested and separately authorized. |
| Encryption/ACLs | **PASS**: ciphertext lacks plaintext credentials/handles, cross-realm tampering rejected, key rotation works, User ACL cannot access Admin keys. |
| Real server fault checks | **PASS — 4 checks**: actual stop/unavailability, intact AOF restart, revocation retained after controlled restart, real noeviction OOM leaves authority unchanged. `local-fault-results.json`. |
| Cookie/proxy components | **PASS locally**: secure host-only/prefix/path attributes, no routine cookie reissue, malformed/duplicate rejection, HTTPS origin/trusted-host/root validator and production startup rejection. Actual ingress topology remains unverified. |
| Python regression suite | **PASS — 1,091 tests + 1,371 subtests**. The 45 opt-in real Redis cases are run separately, not against an implicitly selected service. `full-test-results.xml`. |
| JavaScript regressions | **PASS — 68 tests**. |
| Desktop/mobile browser | **PASS — 17 real Chromium checks**, two tabs/one profile and two alternating Flask app instances sharing Redis. `browser-results.json` and six screenshots. These are not a deployed multi-process WSGI/proxy acceptance test. |
| Business contracts | **PASS locally**: destination/Environment/photo/audit/User regressions pass; migration 0014, photo contract and audit-wrapper SQL bytes match saved fingerprints. No business SQL or recommendation logic was changed. |

Initial OS-process tests encountered sandbox denial of Windows IPC; the same tests passed with authorized local process access. A browser-fixture weather request initially hit the outbound-network guard; the fixture was corrected and rerun successfully. These are resolved local test issues. No unresolved local test failures are reported.

## Remaining production dependencies and limitations

1. **Keep the startup safeguard.** The local factory intentionally rejects non-loopback Redis. Production TLS/ACL routing, deployment entrypoint selection, readiness and proxy integration still require separate implementation review/approval. Do not use development or redis-local mode on the public deployment.
2. Select a private, primary-only Redis service with TLS verification, noeviction, adequate memory/connections, persistence, monitoring and reviewed data residency. Supply separate least-privilege realm identities where supported. App identities need only the reviewed GET/SET/EVAL/TIME/key permissions; local operator fault tests use privileges the app must not have.
3. **Preserve the failover gate.** Lua serialization and an intact local AOF restart do not guarantee durable revocation across replica promotion, restore or data loss. An enforceable external traffic gate and durable epoch change outside Redis, or a separately proven durability mode, remain mandatory. Restoring an older valid ciphertext is not detected by AEAD. No transparent promotion is approved.
4. Review the aggregate design against expected load. Whole-realm CAS serializes unrelated same-realm activity; the size/receipt/allocation bounds and pool budget can cause explicit 503 responses. Measure load, latency and fault behavior before release; review per-record sharding/transaction groups if these bounds are unsuitable. This local implementation is not a capacity certification.
5. Review exact public HTTPS origin, trusted hosts, proxy hop count, header stripping, root mount, CDN bypass and production Secure-cookie initialization against the real hosting topology. No ProxyFix trust count has been guessed or enabled. The helper validator is not proof of ingress security.
6. Provision stable namespace, compatible schema, independently controlled User/Admin epochs, secret-manager keyring/current key ID, shared Flask signing key and per-worker connection pools. Key/epoch incompatibility deliberately requires reauthentication. Host clock synchronization remains necessary for provider JWT expiry checks.
7. Initial cutover requires separate User/Admin sign-in and may restart in-progress recovery/verification. Do not migrate legacy cookie authority or run old memory workers alongside shared workers. An obsolete delayed Set-Cookie or logout response can leave that browser realm pointing at a dead handle or without a cookie; it cannot resurrect revoked server authority, but can require deliberate reload/sign-in. This browser response-order limitation remains a release-review consideration.
8. Qualify the actual multi-process WSGI server, reverse proxy, pool/fork lifecycle, production provider policies, failover/restore controls and rollback in staging. Other process-local product stores (for example assistant conversations) are outside this auth change and retain their own multiworker limitations.
9. Live A/B accounts, provider failover and actual audit-row insertion remain unverified. Production destination writes still require the separately approved disposable Draft scope and preservation checkpoints; Phase 1D remains deferred.

Phase 2E should review these deviations and dependencies before authorizing any production activation. A compatible shared-store rollback, or explicit maintenance plus epoch invalidation, is required. Never roll back to shared-cookie Admin authority, memory fallback, restored revoked sessions, or business-data restoration.
