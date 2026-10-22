# Phase 2C-2C-5 — Coordinated normal-auth activation

Phase 2C-2C-5 connects Flask authentication routes to server-side normal-session
storage and coordinated credential refresh. This document describes the
architecture, security boundaries, and development limitations. The
implementation is not production-ready distributed authentication storage.

## Architecture and authority

- App initialization registers the normal-auth store, adapters, and coordinator.
  Dependencies are reused across requests within that Flask app; separate app
  instances have separate stores.
- Normal authority follows this path: Flask session cookie -> opaque
  `auth_session_id` -> `NormalAuthStore` -> `NormalAuthCoordinator` -> scoped
  `AuthenticatedContext`. Cookie `user_id` and `user_email` values never grant
  normal access.
- `NormalAuthStore` retains verified identity, access and refresh tokens,
  provider session ID, generation, lifecycle timestamps, and a CSRF secret on
  the server. Handles use 256 bits of randomness. The normal-auth cookie holds
  only the opaque reference, not credentials, claims, or SDK session objects.
- Local sessions have a 30-minute idle timeout and an eight-hour absolute
  timeout. Access-token expiry is separate so the coordinator can refresh
  credentials without extending the absolute session lifetime.
- `/user` executes within the coordinator context and renders its verified
  email. `/auth/status` and auth-page redirects use the same authority checks.
  Request-owned clients close when the operation ends, and `g.auth` is cleaned
  up or restored to an enclosing context.

## Login and refresh

- Password login verifies provider identity, claims, password authentication
  method, and expiry before creating server-side authority. It uses an isolated
  public-key client with SDK persistence and automatic refresh disabled.
- The exact returned access token is supplied to both claims and user
  verification. Confirmed identity, matching user IDs and subject, exact issuer,
  authenticated audience and role, and a nonblank provider session ID are
  required. AMR must contain only password methods with integer timestamps
  excluding booleans. The minimum valid response/claim expiry is used and
  rechecked before session creation.
- Successful replacement revokes the previous normal session. Failed session
  mutation revokes the new handle and attempts to restore the previous keys.
- Refresh begins within the configured expiry window, 60 seconds by default.
  Exclusive, generation-bound reservations prevent duplicate refreshes;
  provider work runs outside the store lock. Refreshed credentials are explicitly
  verified and atomically replaced without changing the user or provider session
  binding. A stale refresh cannot resurrect revoked authority.
- Invalid or ambiguous refresh outcomes fail closed. Busy reservations and
  unavailable client construction return temporary 503 responses while retaining
  the candidate handle. Invalid local authority is cleared.
- Handled authentication errors use fixed public messages without provider
  exception details. Application and teardown exceptions propagate rather than
  being relabeled as authentication failures; control-flow signals retain their
  normal propagation behavior.

## Logout and recovery separation

- POST logout revokes local authority before clearing the browser session,
  including recovery keys. It requires neither refresh nor an authenticated DB
  client and makes no provider/global signout call. Other browser sessions remain
  independent.
- `pending_recovery_id` and `password_recovery_id` never grant normal authority.
  Recovery callbacks require recovery AMR and issue only recovery grants; normal
  password login rejects recovery or mixed AMR. Recovery operations do not replace
  normal identity or supply tokens to the normal-auth store.
- Recovery replay protections and grant-bound password-reset CSRF checks remain
  separate from normal authentication. Clearing recovery cookie keys on logout
  does not revoke their server-side recovery records or grants.

## Checkpoint validation

At the Phase 2C-2C checkpoint, the backend suite passed 176 tests using
`.venv\Scripts\python.exe -m unittest discover -s tests`, and `git diff --check`
passed. This is the checkpoint validation result, not a guaranteed current
project-wide test count.

Coverage includes login verification, legacy/recovery authority rejection,
session replacement and rollback, refresh reservations and credential rotation,
revocation during refresh, route behavior, browser isolation, cookie secrecy,
and recovery regressions. Authentication tests use synthetic credentials and
offline transports with network guards. They do not establish live provider
compatibility; no live Supabase sign-in was performed for this checkpoint.

## Development and production-readiness limitations

- Storage is process-local and development-only. Restarting loses sessions;
  separate workers do not share records or refresh reservations. Multi-worker
  deployment requires shared storage with atomic distributed coordination.
- Reservations do not independently expire. A stalled refresh owner can keep a
  session busy until lifecycle expiry or revocation; whole-process failure loses
  the store. Capacity is unbounded, and pruning scans records under the lock.
- Successful status and auth-page checks advance idle activity. Future background
  polling could keep a session active until its absolute timeout.
- Session creation rollback covers mutations during the request, not later
  cookie serialization or delivery. Login currently preserves an existing
  permanent-cookie flag; the intended cookie-lifetime policy needs explicit
  follow-up. Server-side idle and absolute limits still apply.
- Local logout does not revoke provider sessions or recall an already-issued
  context or in-flight request. Provider revocation is not checked on every
  fresh local resolution. Recovery-record revocation on logout also requires
  an explicit deployment policy.
- Login and logout lack explicit CSRF-token/Origin checks. POST-only logout and
  `SameSite=Lax` are partial mitigations, not complete CSRF protection. Add normal
  login/logout CSRF protection before deployment or authenticated write features;
  the stored normal-session CSRF secret is not yet wired into these routes.
  Password reset already uses its separate grant-bound CSRF protection.
- Deployment requires HTTPS and Secure-cookie configuration, non-debug error
  handling, and resolution of the storage, capacity, lifecycle, and CSRF limits
  above.
- Live Supabase integration validation remains required: confirmed-user login,
  actual claims/AMR shape, refresh rotation, user-client authorization, logout,
  and browser cookie behavior must be checked against the configured project.
