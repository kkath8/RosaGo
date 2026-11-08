# Phase 2T Stage 2B — Controlled Live User Login Verification

Started **2026-11-06, Asia/Manila**. Reference: [Stage 2A preparation](../phase2t-stage2a-login-preparation/REPORT.md).

**Result: INDETERMINATE — stopped after an execution/evidence mismatch.** The owner explicitly confirmed clicking Log In once. That consumes the entire authorized attempt, even though the controlled wrapper did not observe the submission. Live authentication, session continuity and Admin denial cannot be marked PASS. No retry is authorized.

## Observed result and immediate stop

1. The controlled process reported READY and `netstat` showed a listener on `127.0.0.1:5000`. Its saved startup configuration matched the approved development architecture.
2. The dedicated Edge InPrivate launch was requested. A separate anonymous HEAD request to `/login` returned HTTP 200; no credentials were supplied by the probe.
3. The owner then confirmed: **“I submitted Log In once.”** No credentials or tokens accompanied that confirmation.
4. The saved wrapper evidence still contained zero route observations, zero login submissions and zero provider password requests. A read of its status-only control route returned **HTTP 404**, instead of the wrapper's expected JSON 200. The actual server/process/browser path serving the owner's submission therefore could not be established from the available evidence. The underlying cause is not proven; do not assume the login failed or that no provider session was created.
5. No further protected-route probes, sign-ins, sign-outs, retries or credential inspection were performed. A persistent owner-attempt-consumed record and stop marker were created, and the wrapper now refuses restart if either exists. The owned verification process exited normally; `server_closed=true` is recorded. No listener on `127.0.0.1:5000` was found at the final local check. No unrelated server/browser was terminated.

See [owner-attempt-consumed.json](owner-attempt-consumed.json) for the controlling attempt ledger. **Its owner-confirmed consumed attempt takes precedence over the wrapper's zero counter.** The wrapper counter describes only what that instrumented process saw, not all requests the browser may have sent. The owner subsequently reported **“The RosaGo homepage or User page loaded.”** Record that as owner-observed navigation success; it does not independently establish authenticated identity, session continuity, HTTP status or Admin denial.

## Authorization and setup

The owner authorized exactly one manual login through the existing localhost User form, no Admin account or credential automation. The owner separately confirmed that the current configuration and dedicated User account belong to the isolated nonproduction test project.

No process was listening on port 5000 at initial inspection. A controlled wrapper started the unchanged Flask application on `127.0.0.1:5000`, one process, debug/reloader off. Actual startup confirms:

- Existing development mode; `RealmSessionInterface`.
- Distinct User/Admin `NormalAuthStore` instances.
- No `rosago_shared_sessions` extension; no Redis/PostgreSQL authority adapter activation.
- Production startup safeguard unchanged; mode is checked before importing the application.

The wrapper permits one owner-initiated User `POST /login` and one provider password-session request, consuming each allowance before processing. Attempt consumption is saved without request fields; restart refuses a second attempt. No password, token, API key, cookie value, identity or provider body is inspected or recorded by the probe. The existing application handles its own normal private configuration/credential processing and process-memory session state.

The only allowed provider operations are the one password-session request, Auth user/JWKS validation reads and selected places/profile/trip reads. All Admin login/logout, account/password/mail actions, RPC/table/Storage writes, Gemini calls and other provider traffic are denied. Unexpected provider or authorization errors stop further application/provider activity. Dashboard weather/notices are deliberately outside the selected read scope and blocked without invoking providers.

A dedicated Edge InPrivate launch was requested with login and status-only verification tabs. The owner enters credentials directly, leaves the password masked and clicks Log In once. No browser automation, screenshot, request tracing, credential-field inspection or cookie extraction is used.

## Intended verification and actual results

The intended status-only tab would check protected `/user` twice in the same browser cookie jar and check `/admin` and `/admin/account` without credentials. It reads HTTP statuses only, never page bodies, passwords, cookies or tokens. The normal post-login homepage must also return 200. Admin routes must redirect to Admin login, never grant access. **Those checks were not observed and were not rerun after the mismatch.**

| Check | Current result |
| --- | --- |
| Actual approved localhost startup | PASS |
| Experimental adapters inactive | PASS |
| One-attempt boundary policy | Five offline tests passed |
| Manual User login | Owner confirms one submission; HTTP/provider result INDETERMINATE; allowance consumed |
| Homepage/dashboard | Owner reports homepage or User page loaded; post-submit HTTP status/authentication NOT independently VERIFIED. Anonymous login-page HEAD was 200. |
| Two protected User reads / session continuity | NOT VERIFIED; no further checks after stop |
| Ordinary User cannot access protected Admin routes | NOT VERIFIED live; isolated coverage exists |
| Status-only control route | 404; expected wrapper 200, triggering stop |
| Admin login / logout | Not initiated by this stage |
| Emails, password/account changes, business/Storage writes, Gemini | No such request initiated or observed by the probe; cannot attest to unobserved backend behavior |

Evidence: [live-results.json](live-results.json); enforcement in [live_user_probe.py](live_user_probe.py); synthetic policy checks in [test_boundary_offline.py](test_boundary_offline.py). Initial offline fixture file writes hit sandbox temporary-directory restrictions; tests were changed to mock persistence while asserting the consumed-attempt payload. All five policy tests then passed without network or real credentials.

## Side effects and limits

The controlled wrapper observed no provider traffic. **This does not prove the owner's submission had no provider side effects.** An accepted sign-in may have created session/refresh state, updated sign-in/security metadata and produced provider Auth logs. None of those were queried after the stop. No RosaGo destination audit insertion or business mutation was initiated by the probe. No production/backend integrity or before/after data comparison is claimed; hosted internal hooks/logs and the unobserved submission path remain unknown.

The intended first session was expected to be fresh; automatic refresh was outside this bounded wrapper. An attempted refresh would be denied and stop the run. The owned server was closed through its stop marker before its maximum 20-minute window. No logout, provider revocation, password restoration or account cleanup was performed. No credentials, tokens, raw provider responses or browser contents were inspected or saved; the private window is not inspected or closed automatically because its actual use could not be verified. Close the dedicated InPrivate window manually without submitting another login.

## Decision

**User login verification: INDETERMINATE. Next Admin login test: NO-GO.** Before any further live stage, establish a consistent browser-to-controlled-server path using anonymous, non-side-effecting checks and review execution controls. Any new User attempt requires fresh explicit authorization; the owner-confirmed attempt cannot be reset because the wrapper missed it. Admin login needs its own separate approval. Closing the owned server discards its process-local authority; any later simultaneous-session rehearsal must account for a newly approved User login if required. Do not assume an unobserved provider session was revoked.

No deployment, staging, commit, push, existing runtime-source edit, SQL write, startup-safeguard change or experimental adapter activation occurred. **Stopped after the single owner-confirmed submission; no further live verification is authorized.**
