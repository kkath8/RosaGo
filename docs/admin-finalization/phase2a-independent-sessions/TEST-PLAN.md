# Phase 2A — acceptance tests before implementation rollout

**Proposed tests only; no session changes or new tests were implemented/executed in Phase 2A.** Use synthetic offline Supabase transports by default. Browser tests use one real cookie jar/shared browser context with two tabs, not separate incognito contexts. Production access and business-data writes remain separately gated; Phase 1D is deferred.

## Same-browser identity and namespace matrix

| Scenario | Required result |
| --- | --- |
| User A signs in, then Admin B | User routes/profile/status remain A; Admin account/routes remain B. Two different provider session IDs/token sets and independent local handles. |
| Admin B signs in, then User A | Same result in reverse order; no Admin handle replacement or revocation. |
| Existing User A has Admin membership but no Admin cookie | `/admin` requires explicit Admin sign-in; no User-cookie authorization or implicit promotion. |
| Only Admin B signed in | User protected routes redirect to User login; `/auth/status` is unauthenticated. Public catalog stays public. |
| Both cookies sent manually to either realm | Only the designated namespace is consulted. Never use whichever record resolves. |
| Handle copied/swapped between cookies | Reject or unauthenticated; no cross-namespace lookup or credential fallback. |
| Invalid/oversized/duplicate/path-shadowed Admin cookies | Fail closed; no identity selection from cookie order. |
| Bare `/admin`, nested paths, `/administrator`, 404/405 and redirected responses | Correct boundary and save policy. Admin errors/flash never emit a User Set-Cookie header. Test URL/mount-prefix normalization explicitly. |
| Admin template/account/shared own-profile read | Shows B; no A identity/client/token in context or HTML. User template shows A. |

## Authentication, membership and fixation

Reuse normal password verification tests for wrong credentials, unconfirmed email, claims issuer/audience/role, password AMR, mismatched subjects/session IDs, expiry and provider failures. Admin membership must be checked with B's verified candidate client before browser authority is installed and on each protected request afterward. Denied/non-Admin or unavailable membership cannot alter A or grant Admin authority.

Test fresh unpredictable handles/CSRF on success, rejection of caller-chosen IDs, challenge replay, rollback after partial establishment, cookie serialization/delivery failure, and revocation before cookie cleanup. Captured old cookies and stale snapshots must never recreate authority. Do not log or render credentials during failures.

Membership removal must deny the next protected request without modifying User A. Admin logout must still be available without current membership. Local fixtures simulate removal; do not change production memberships to run the test.

## Independent logout and lifetime

- Logout A: only User handle revoked/cookie cleared; B's Admin authority, CSRF, expiry and flashes preserved.
- Logout B: only Admin web/auth handles revoked/cookie expired; A's User and recovery state preserved.
- Replaying a logged-out handle fails; opposite realm stays valid. Ordinary logout makes no provider global sign_out call.
- Inject clocks to expire idle/absolute User and Admin records independently. Activity in A must not extend B and vice versa; touch cannot extend absolute lifetime.
- Concurrent same-realm refresh consumes its refresh token once; different realms can refresh independently. Refresh cannot change user, realm or provider session ID. A refresh failure/busy response cannot revoke the other realm.
- Provider single-session/account-security invalidation is simulated explicitly, including the same-account case. Do not expect a locally isolated cookie to override provider revocation.

## CSRF, recovery and User regressions

| Token/purpose | Target | Expected |
| --- | --- | --- |
| User authenticated CSRF | Admin edit/logout | Rejected; neither realm changes |
| Admin authenticated CSRF | User mutation/logout | Rejected; neither realm changes |
| User pre-login token | Admin login | Rejected before password Auth call |
| Admin pre-login token | User login | Rejected before password Auth call |
| Recovery grant token/handle | Either normal login/mutation realm | Never grants authority |
| Expired, old-session, duplicated or missing token; wrong/missing Origin | Protected relevant forms | Rejected according to explicit route policy; no mutation |

Cover User logout forms created by JS as well as server templates, and correct-origin successful login/logout UX. Check browser cookie flags, no Domain, intended Path, expiry/deletion attributes, production HTTPS enforcement and explicit local-development names/settings.

Run all existing normal-auth store/coordinator/adapters/Flask/login/status tests, User profile/trip/login-continuation tests, PKCE callback/reset/grant replay tests and recovery frontend tests. Verify starting/resetting a User-owned recovery flow does not install or clear Admin authority; Admin login/logout does not consume User recovery state; resetting A's password does not locally erase different account B. Successful recovery still returns to User login without automatic Admin promotion.

## Actor attribution and business boundaries

With A and B active simultaneously, capture synthetic request-owned clients and require every Admin membership, directory, destination, photo authorization and mutation request to use B's bearer identity. User profile/trip requests must use A's. The wrapper RPC remains the audited public function; no client-supplied actor UUID or direct unlogged-inner call. Test interleaving to expose global-client contamination.

In an approved isolated database only, verify successful Admin actions create one audit row with actor B and the correct submitted fields/status; rejected User-A/nonmember/CSRF/stale requests create none. Local HTTP payload mocks alone cannot certify database audit insertion. Any production audit proof must use separately approved disposable test data and all preservation gates; this architecture phase does not authorize it.

## Race and backend contract tests

- Concurrent Admin/User login/logout and response ordering: no cross-cookie headers or cross-store mutation.
- Two Admin login attempts sharing one challenge: at most one establishment; stale completion cannot revive replaced handles.
- Logout vs refresh/web-state save/flash consumption: no resurrection, no lost revocation; ordinary responses do not reissue old cookies.
- In-flight mutation dispatched before logout: document possible completion as B; after revocation, new dispatch is refused. No false claim that logout cancels an in-flight database transaction.
- Same-realm late cookie deletion: fail closed with reauthentication if necessary, never cross-account authority; verify documented limitation.
- Shared-backend atomic CAS/reservation/release/generation fencing, worker crash, expired leases, token-rotation uncertainty, outage/failover and capacity/TTL cleanup.
- Two-worker load balancing with no sticky-session assumption; both realms resolve/revoke consistently. Test shared recovery state as well.
- Single-process development restart deliberately loses sessions; distributed backend timestamps must not rely on process-relative monotonic values.

## Acceptance and rollback gates

Require the complete simultaneous-login/independent-logout/browser-cookie matrix, normal User/recovery regressions, Admin CSRF/membership/actor tests and backend contract suite to pass before production rollout. Confirm topology and HTTPS settings match the mode actually tested. No acceptance based solely on manually seeing two account names.

During rollback rehearsals, old shared Admin sessions never become valid independent Admin sessions or vice versa. User behavior remains available where supported; otherwise report expected restart-related sign-outs. Any emergency Admin disablement must not route Admin through the old User cookie.
