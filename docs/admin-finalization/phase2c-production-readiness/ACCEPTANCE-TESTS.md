# Phase 2C — required production acceptance plan

**Proposed tests only. No new tests or production operations were run in this review.** First implement the contracts and run fault tests in an isolated environment. Production account/session tests require separate release approval and already authorized accounts. Do not provision roles, change Auth policies or use a service-role key for end-user mutations.

## Prerequisites

Use one browser context/cookie jar with User A and a different existing Admin B in separate tabs. Configure at least two app workers, load-balance without stickiness and expose worker identity only through protected diagnostics. Use the actual reviewed HTTPS/proxy topology and a dedicated session namespace. Record protocol/epoch/key IDs without secrets. Take current read-only business-data checkpoints under an authorized operator when testing any business write.

| Gate | Required PASS evidence |
| --- | --- |
| 1. Shared backend and safeguard | Production startup rejects missing/invalid backend, TLS, realm namespace, schema/keyring/epoch and root/proxy configuration. No development/RAM fallback. Valid configuration passes only after required operations and durability gate are verified. |
| 2. Both login orders | A then B and B then A, one real browser jar across different workers: User profile/status remain A; Admin account/member requests remain B. Exact separate cookies, credentials and provider-session identities. |
| 3. Independent logout | Logout A on worker 1; B remains valid on worker 2, unchanged CSRF/deadlines. Reverse the test. Provider global sign-out is never called. Replayed old cookies cannot authenticate. |
| 4. Cookie boundary | Secure, HttpOnly, Lax, correct path, no Domain, correct prefix/deletion attributes. Root User cookie may be physically sent to /admin but is ignored. Copy/swapped/duplicated/malformed/legacy cookies grant nothing. /administrator, bare /admin, encoded boundaries, errors and redirects cannot change the other cookie. |
| 5. CSRF and Origin | User token rejected on Admin mutations/logout/login and vice versa. Missing, duplicated, expired, recovery-purpose and old-session tokens rejected. Dynamic/static/mobile logout forms work. Wrong Origin/Host/forwarded values denied; CDN/CORS cannot disclose token responses. |
| 6. Membership/identity | Valid password for nonmember denied before Admin installation. Membership service outage gives 503, not authority. Revoked membership denies next protected operation; logout still works. Do not change production memberships for this test; use existing denied account or isolated membership simulation. |
| 7. Independent expiry | Controlled-clock integration tests for idle/absolute/token expiry on each realm; other-realm traffic does not extend it. Busy/unavailable responses do not clear the other realm. Expired records remain invalid even if key GC is delayed. |
| 8. Refresh concurrency | Many same-session requests on separate workers issue one provider refresh. Different sessions proceed independently. Credential generation/subject/provider session cannot change incorrectly. Late refresh cannot undo logout. |
| 9. Worker crash and uncertainty | Crash before provider call, during refresh and after provider response/before commit. Expired lease does not start another possibly destructive refresh. Uncertain session requires sign-in; unrelated A/B sessions remain valid. Lost Redis acknowledgment reconciles receipts rather than reissuing provider calls. |
| 10. Rotation/revocation atomicity | Concurrent login/logout/challenge replay, stale browser save, OOM/wrong-type/script error and partial TTL/index failure: no orphan authenticated binding, parent resurrection or silent overwrite. Stale writes are explicit; late cookie responses fail closed without cross-realm effect. |
| 11. Backend outage | Protected requests fail 503 before business dispatch. No cookie clearing, replica/local snapshot authorization, token refresh replay or RAM fallback. Revocation is not reported complete without an acknowledged/reconciled result. |
| 12. Restart and failover | Ordinary compatible worker restarts preserve live sessions, deadlines, CSRF and transient auth flows. Promotion/restore with potentially stale data stays gated until epoch invalidation. Previously revoked sessions/challenges cannot return. Test real provider-equivalent fault behavior, not only mock locks. |
| 13. Recovery and verification | Start PKCE on worker 1, callback on worker 2, reset on worker 3; consume once. Wrong browser/realm/code/grant, replay and concurrent update denied. Signup verification/resend throttles survive worker changes. Admin login/logout leaves User recovery/verification references intact. Reset still returns to User login and never promotes to Admin. |
| 14. Account management | User profile, settings, login continuation, email verification and reset regressions pass under shared web state; private authority stays out of templates/logs. Native forms work with JS disabled where currently supported. Public catalog pages remain read-only/identity-neutral and must not touch auth credential authority just to render navigation. |
| 15. UI/browser | Desktop and mobile, both login orders and refresh/back/forward/multiple tabs. Navigation shows A on User and B on Admin. No browser token storage, horizontal overflow or shared-cookie flash contamination. New User-cookie cutover prompts deliberate reauthentication without account loss. |
| 16. Audit attribution | First verify isolated database actions use B's JWT and insert one B actor audit row with correct submitted fields/status. No actor comes from A, a cookie field or client JSON. Rejected CSRF/stale/nonmember requests produce no mutation/audit. |
| 17. Business preservation | Destination/Environment/photo/publication/weather tests pass against isolated fixtures. Session storage does not change RPC signatures, grants, policies or audit wrapper. For any later approved production write, compare all preexisting destination/photo/status/timestamp/audit and Storage checkpoints exactly. |
| 18. Rollback | Compatible previous shared release retains sessions, or maintenance/invalidation is explicit. No old shared-cookie Admin fallback, dev-mode bypass, restored credential authority, business-data rollback or deleted audit history. |

## Optional separately authorized production audit-write proof

The session acceptance plan does **not** resume Phase 1D. If a later approval explicitly authorizes its disposable Draft:

- Capture fresh all-status destination/audit/Storage checkpoints, create exactly one new Draft through Admin B and record its UUID; never use Chowking or another existing destination.
- Keep User A active in the same browser. Save only approved Environment changes on that new UUID; verify request credentials and actual audit actor B, submitted_fields and resulting Draft status.
- Keep it unpublished. Public API must exclude it and User detail must be unavailable. Positive public synchronization cannot be claimed from a Draft-only test.
- Archive only that new UUID under the approved cleanup scope; retain audit history and all Storage objects. Stop on ambiguous response, unexpected actor/mutation or any preservation mismatch. Do not retry a timed-out create blindly.

These production business writes require their own explicit approval, data access and cleanup plan; they are not prerequisites to writing/testing the shared adapter locally in Phase 2D.

## Evidence and stop rules

Record gate results with worker IDs, sanitized operation/receipt IDs, realm, epoch/schema/key IDs, public actor UUIDs where approved, before/after version/deadline evidence and redacted network headers. Never record passwords, raw cookies, JWTs/refresh tokens, OTPs, PKCE verifiers, encryption keys or Redis URLs with credentials.

Any cross-realm authority, state resurrection, duplicated provider refresh, unsupported durability gate, unexpected business mutation, missing/wrong audit actor or unreviewed production configuration is NO-GO for release. Real production rejection/expiry probes must use approved sessions only; crash/failover/security-policy fault injection belongs in isolated infrastructure, not live customer sessions.
