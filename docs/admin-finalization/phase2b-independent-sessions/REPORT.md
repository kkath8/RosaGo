# Phase 2B — independent User and Admin sessions

**PASS — proceed to Phase 2C review. Local implementation and testing are complete. Production deployment is not approved or ready: shared-session infrastructure and HTTPS/topology review remain required.**

All production restrictions were preserved. No production requests, sign-ins, session changes, database connections/SQL execution, record writes, Auth setting changes, migration execution, feature-flag changes, infrastructure provisioning, staging, commits or pushes occurred. Existing unrelated worktree changes were retained. Phase 1D production writes remain deferred.

## Implemented session architecture

- `RealmSessionInterface` chooses Admin state only for exact `/admin` or `/admin/...` paths. All other paths delegate to the existing signed User cookie interface. Admin errors, redirects, flash messages and session clearing cannot write the User cookie; User responses do not issue or expire the Admin cookie.
- Admin uses a random 32-byte opaque browser handle, HttpOnly, SameSite=Lax, host-only, Path=/admin. Local HTTP uses `rosago_admin_session_dev`. The secure-cookie implementation uses `__Secure-rosago_admin_session` and Secure=true; its attributes are tested with an HTTPS test-client context. No JWT, email, role or refresh credential is stored in that cookie.
- Admin browser state and credential state live in separate server-side stores. Admin has its own NormalAuthStore/coordinator/adapters instance under `rosago_admin_auth`; User keeps `rosago_normal_auth`. Admin web state contains only an opaque auth-store reference, pre-login CSRF/timestamp and UI state.
- Successful Admin login verifies the password/claims through the existing adapter and checks database-backed membership with the candidate B token **before installing authority**. Every protected Admin request checks membership again. Nonmembers receive no authenticated Admin session. Admin mutations/reads use only `g.admin_auth`; User routes retain User-only `g.auth`.
- Server-assigned `AuthenticatedContext.realm` prevents User contexts from being accepted by Admin services. The context contains no new CSRF credential field; the existing context-secrecy contract is preserved. Request-owned Supabase clients keep A and B bearer tokens separate. Database audit UUID attribution remains the existing wrapper's `auth.uid()` behavior; no client actor parameter was added.
- Login rotates the Admin browser and auth handles. Partial rotation revokes new credentials/web state and preserves the old server/browser authority. Logout revokes only the selected realm before cookie removal. Admin logout remains possible after membership revocation. Neither logout performs provider global sign-out.
- Existing credential verification, 30-minute idle/8-hour absolute expiry, refresh reservations, generation checks and client cleanup are reused unchanged. NormalAuthStore itself is unchanged. Different realms do not touch each other's activity or refresh reservations.
- Admin browser writes use compare-and-swap. A stale write returns visible HTTP 409 with instructions to reload and verify the result; it cannot overwrite newer state or recreate a revoked record. Normal refresh/page responses do not continually reissue the stable Admin cookie.

## User CSRF and recovery behavior

User login now requires a User-purpose, single-use pre-login challenge and same-origin request. Admin login challenges are separate by purpose and server/browser state. Both have bounded process-local challenge storage and a local login-attempt limit of 20 per minute per realm/address. Failed or denied login does not replace the other realm's authority.

User logout now requires its own CSRF token and Origin. Static logout forms, settings forms and JS-generated logout forms are updated. Authenticated templates use an already authorized/copied User token. Public catalog rendering continues to make **no authentication lookup or cookie mutation** merely to draw navigation. When a public-page logout button needs a token, it obtains one on demand from the User-only, no-store `/auth/logout-token` endpoint. A recovery-only/anonymous logout uses a separate User pre-auth token and retains the existing User-session clearing policy.

Password reset, PKCE exchange/replay protection, recovery grant CSRF, email verification and profile/account-management behavior remain intact. Admin logout preserves User recovery grants. Recovery references cannot become Admin authority. Shared account recovery still returns to User login and does not automatically sign into Admin. Provider account-security invalidation may still affect sessions for that account; no production provider policy was inspected or relaxed in this implementation phase.

## Files changed in this phase

The following list describes Phase 2B work, not all preexisting changes shown by git status.

| Files | Changes |
| --- | --- |
| **New:** `session_realms.py` | Cookie/realm boundary, bounded Admin web store, CAS/revocation, single-use login challenges, local throttling and deployment guard. |
| **New:** `admin_session_flask.py` | Admin dependencies/context, candidate membership check, establishment, scoped logout and error handling. |
| **New:** `user_csrf.py` | User login/logout CSRF and safe token presentation. |
| `app.py` | Realm/Admin initialization, User login/logout CSRF enforcement, User-only token endpoint, safe logout-token rendering/error handling. |
| `normal_auth_flask.py`, `normal_auth_coordinator.py` | User-only realm guards and server-assigned context realm; existing algorithms retained. |
| `admin_auth.py`, `admin_routes.py` | Admin-only decorators, credentials, context, store/CSRF helpers and login/logout lifecycle. |
| `admin_authorization_service.py`, `admin_places_service.py` | Explicit Admin-realm context validation. |
| `templates/auth/login.html`, `templates/base.html`, `templates/partials/navigation.html`, `templates/user/settings.html`, `static/js/user-ui.js` | Real User login/logout CSRF in server and dynamic forms; public pages remain read-only. |
| `templates/admin/login.html`, `templates/admin/account.html` | Explain separate sign-in and Admin-only logout. |
| **New:** `tests/test_independent_sessions.py` | 27 focused identity, cookie, CSRF, recovery, race, membership, attribution-boundary and failure-injection tests. |
| Existing Admin tests, `tests/test_registration.py`, `tests/test_destination_environment.py` | Explicit Admin seeding/cookie paths/realm contexts instead of shared User-authority fixtures. |
| `tests/test_login.py`, `tests/test_login_dashboard_redirect.py`, `tests/test_functional_completion.py`, `tests/test_recovery_callback.py`, `tests/test_settings.py` | CSRF-aware legitimate login/logout submissions and updated security expectations. |
| This directory | Local browser fixture/runner, desktop/mobile screenshots, JUnit/log evidence and machine-readable summary. |

Full path lists and tested application SHA-256 values are in [verification-summary.json](verification-summary.json). Credential-store implementation, recovery helper/transport, profile service, dependencies and migration/photo/audit SQL fingerprints were checked unchanged against saved evidence. Existing Environment/photo/User feature changes already in the worktree were retained.

## Final validation results

| Validation | Final result |
| --- | --- |
| Full Python suite | **1,091 passed; 1,371 subtests passed; zero failures/errors/skips** |
| JavaScript suite, 10 existing test files | **68 passed; zero failures/skips** |
| Real Chromium, two tabs in one temporary profile | **17 checks passed** |
| Desktop/mobile widths | **1440×960 and 390×844**; no horizontal overflow in checked pages |
| Source compilation and git diff whitespace check | **PASS** |
| Migration 0014/photo contract/audit-wrapper source preservation | **PASS — unchanged** |

The Python command was `.venv/Scripts/python.exe -m pytest -q tests -p no:cacheprovider --tb=short --junitxml=docs/admin-finalization/phase2b-independent-sessions/full-test-results.xml`. JUnit counts include subtests: 2,462 total entries versus 1,091 test functions. Evidence: [full-test-results.xml](full-test-results.xml) and `full-test-output.txt`.

JavaScript ran with `node --test --test-isolation=none` over the ten existing test files. Default Node child-process isolation was blocked by the local sandbox; running in one process avoided that spawn restriction. No test assertion was disabled. Evidence: `javascript-test-output.txt`.

Browser checks used real Chromium CDP, one temporary profile/two tabs, and a loopback-only Flask fixture with synthetic accounts and MockTransport. Outbound socket connections were blocked in the fixture. They covered User A then Admin B at desktop width, Admin B then User A at mobile width, actual native login/logout forms, independent logout, correct identities, mobile User dialog and Admin menu/Escape behavior. Evidence: [browser-results.json](browser-results.json), six screenshots and the reproducible `browser_fixture.py` / `browser_checks.mjs`. The isolated browser/server were stopped and its temporary profile removed afterward.

### Failures found and corrected

Early runs caught old shared-session fixture expectations, an unnecessary public-page authentication lookup/cookie write, a CSRF value temporarily added to the generic context, an altered nested-auth g footprint, fault-injection compatibility around session proxies, and empty navigation logout tokens when authority was intentionally hidden before rendering. These were corrected in code or, for obsolete shared-session assumptions, explicit fixture/assertion changes. Original context-secrecy and public-page no-auth/no-cookie assertions were retained and pass. Final full-suite results above are clean; earlier diagnostic logs are retained separately for traceability.

Candidate transport/cleanup failures are sanitized to 503 without installing authority or leaking provider details. Partial session-rotation and stale-save fault tests verify that existing authority is not silently replaced or resurrected. Existing Environment, photo, destination, audit, account-management, recovery and navigation regressions pass in the full suite.

## Production dependencies and design differences

1. **Memory stores are local/single-process only.** They are thread-safe but neither durable nor shared among workers. No distributed infrastructure or dependency was introduced. Restart still loses sessions and recovery state. Sticky sessions are not a durability/revocation solution.
2. **Explicit production mode refuses startup.** `ROSAGO_AUTH_MODE=production` fails until a reviewed shared backend is supplied. Deployment must explicitly select production mode, not omit it to fall back to development. The secure Admin cookie implementation/attributes are ready and locally tested, but production app startup, TLS/proxy/host policy and Secure User cookies still require the separate deployment work. Current default development mode intentionally supports local HTTP.
3. **Root-mounted app only in this implementation.** Non-root APPLICATION_ROOT or SCRIPT_NAME is rejected rather than silently losing cookie delivery. A prefixed deployment needs separately tested cookie/path configuration.
4. **Consolidated modules.** Admin browser storage lives in `session_realms.py`, rather than an additional `admin_session_store.py`. Credential storage/coordinator code is reused through separate instances, not duplicated.
5. **Local rate limiting is not distributed protection.** Review capacity, proxy-derived addresses, shared rate limits, encrypted credential storage, atomic leases/CAS and crash recovery before production. The shared-backend environment names proposed in Phase 2A are not implemented/provisioned here.
6. **Same-realm response races fail closed.** CAS conflicts are explicit 409 responses. A delayed browser cookie issuance/deletion may require reauthentication in that realm; it cannot revive revoked authority or clear the other realm. Logout cannot cancel an already-dispatched database request, and mutations are never automatically retried.
7. **Database/provider integration remains simulated.** Admin B's request credentials/UUID and actor-free audited RPC payload are verified locally, and audit UI attribution tests pass. Actual Supabase provider sign-ins and database audit insertion were not performed. Those require separately authorized integration testing; this phase does not resume Phase 1D.

No RosaGo schema change, SQL function change or Supabase Auth policy change was necessary for the local implementation. A production backend, coordinated rollout without mixed shared-session/independent-session workers, HTTPS cookie configuration and explicit reauthentication strategy remain review gates. Existing old User/shared handles are never promoted into the new Admin namespace.

**Recommendation: PASS for proceeding to Phase 2C review. Do not deploy this process-local implementation as production session infrastructure. Stopped after local implementation and testing.**
