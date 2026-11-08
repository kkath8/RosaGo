# Phase 2T Stage 2A — Existing-Account Login Verification Preparation

Prepared **2026-11-06, Asia/Manila**. Reference: [Stage 2 live test plan](../phase2t-stage2-live-test-plan/REPORT.md).

**GO for preparation and isolated verification. NO-GO for live login/logout until explicit, scoped approval.** The owner confirms that one dedicated User and one dedicated Admin account already exist and are available. No new account or credential change is needed by the implemented password-login flow. Actual password validity, email confirmation and hosted Admin membership remain live acceptance checks; account availability alone does not prove them.

No real credential was requested, inspected, copied, recorded or hardcoded. No provider request, live sign-in/sign-out, email, account modification, database/Storage write or Gemini call occurred in this phase.

## 1. Verified login-route configuration

Reviewed `app.py`, `admin_routes.py`, `normal_auth_coordinator.py`, `user_csrf.py`, both login templates and their browser scripts.

| Route | Verified flow | Expected success / rejection |
| --- | --- | --- |
| `GET /login` | Renders User form with `method=post`, action `/login`, hidden User CSRF, email and masked current-password field. | Anonymous form 200. An existing authenticated User may be redirected to their User page. |
| `POST /login` | Exact-origin, purpose-bound CSRF and realm/IP login-attempt controls precede credential verification. Calls User adapter `password_login`, then installs only verified credentials in User authority. | 303 to `/` for the plain login flow; the public homepage may then display User context. Open protected `/user` to confirm identity. Only a validated `add_place` slug can select the existing continuation; do not use it for this test. |
| `GET /admin/login` | Renders a separate POST form, action `/admin/login`, Admin CSRF and masked password. User login does not bypass it. | Anonymous form 200; existing valid Admin authority/membership redirects to `/admin`. |
| `POST /admin/login` | Strict single-valued `csrf_token`, `email`, `password` fields; exact Origin, challenge expiry/single use, Admin/IP attempt limit. Password verification then `verify_admin_candidate` calls current-caller `rosago_is_admin` **before** Admin authority is installed. | 303 to `/admin` if allowed. Nonmember 403 installs no Admin authority; service/membership lookup failure 503 fails closed. |
| `POST /logout` | User CSRF; development local credential record revoked, User browser session cleared. | 303 login redirect; Admin authority preserved. No provider-global sign-out. |
| `POST /admin/logout` | Authenticated Admin realm and its CSRF; local Admin credential and web-state records revoked, Admin cookie deleted. | 303 to Admin login; User authority preserved. No provider-global sign-out. |

Both password adapters use fresh HTTP/SDK clients with `persist_session=False`, `auto_refresh_token=False`, no redirects/environment proxy and a 20-second operation timeout. They check provider session/user consistency, validated claims/issuer/session ID/expiry and confirmed email before returning verified credentials. Protected requests can still explicitly refresh a token when necessary; disabling SDK auto-refresh does not forbid that application behavior.

`login.js` validates fields and allows the native form POST to Flask; it does not authenticate directly against Supabase or save credentials in browser storage. `admin.js` supplies UI/password-visibility behavior; Admin authentication is also a native Flask form POST. Both pages have Show controls: **leave passwords masked and never click Show during the rehearsal**. Do not use Forgot password or Create account links.

Fresh synthetic form checks returned 200 for both pages, correct POST actions, CSRF fields and password masking. No actual-config POST or live form submission was performed.

## 2. Active session architecture and boundaries

The offline configuration check read only the nonsecret `ROSAGO_AUTH_MODE` assignment and process override; it did not parse API keys or account variables. The mode remains absent, selecting **development**. Experimental mode is not selected. Source inspection confirms that this mode chooses the following architecture; the fresh synthetic startup independently exercised the same development branch. The real-config startup in Stage 1 is prior evidence, not a new real-credential app import here.

| Layer | User | Admin |
| --- | --- | --- |
| Browser cookie | `session`, path `/`; Flask-signed client-side state containing opaque auth handle and local flow/CSRF state, not provider credentials | `rosago_admin_session_dev`, path `/admin`; opaque reference to separate server-side web state |
| Local credential namespace | `app.extensions['rosago_normal_auth']`; its own `NormalAuthStore` and record map | `app.extensions['rosago_admin_auth']`; a different `NormalAuthStore` and record map |
| Authenticated context realm | `user` | `admin` |
| Web state | User signed-session interface | `AdminWebStore` with compare-and-swap updates and rotated browser handle |
| Cookie attributes | HttpOnly, SameSite=Lax; Secure false for existing local HTTP mode | HttpOnly, SameSite=Lax; Secure false for existing local HTTP mode |

These are separate **in-memory namespaces/store instances**, not Redis/PostgreSQL namespaces. `RealmSessionInterface` selects Admin state only for `/admin` and `/admin/...`; other paths use User state. Although the User cookie's `/` path means a browser can send it on Admin requests, the Admin authority reader does not accept it. Cookie-path separation alone is not the authorization mechanism.

Fresh synthetic runtime checks confirm different credential stores/maps, distinct realm tags and cookie names/paths, no `rosago_shared_sessions` extension, and debug false. Redis helper imports in shared code do not mean Redis is active: the development branch does not select its shared interface. No Redis, record-session or PostgreSQL experimental backend was activated. The production startup refusal remains in place and is covered by the independent-session tests.

The existing application necessarily retains provider access/refresh credentials **only in server process memory** for its authenticated-session operation; they are not in the cookies or test evidence. Future approval must acknowledge that existing runtime behavior. The operator/agent must never extract, display, persist, copy or log those credentials. Passwords are entered by the owner into the masked form only and are not retained in the local auth store.

Local idle lifetime is 30 minutes and absolute lifetime eight hours, with independent expiry/revocation. One process, one browser profile and no reloader/restart are required; process restart loses auth/pending state. This architecture is not a production or multi-worker approval.

## 3. Fresh offline verification

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe docs/admin-finalization/phase2t-stage2a-login-preparation/verify_offline.py
```

**99 isolated Python tests passed, zero failures/errors/skips**, covering User/Admin login, redirect behavior, independent sessions, Admin authorization, SDK adapters and Flask auth integration. The exact modules/timing are in [isolated-results.json](isolated-results.json). Evidence includes both login orders, independent logout/expiry/revocation, cookie/CSRF separation, fixation defenses, nonmember rejection and production startup refusal.

The reused test runner removes real environment credentials, disables dotenv loading and blocks socket/DNS/send operations; providers use mocked clients/transports. A separate synthetic fixture inspects only form structure and session class/namespace metadata. No actual account credentials are available to either test scope. Outer network guard attempts and real provider requests: **zero**.

[preparation-results.json](preparation-results.json) records the nonsecret mode classification, synthetic architecture/forms and preservation of **274 existing files** in the selected runtime/test/template/script/prior-report scope. No raw page, cookie, CSRF value, test output or credential was saved.

One initial harness metadata probe referred to `coordinator.realm`; source inspection showed the internal field is `_realm`. The new preparation harness was corrected and rerun successfully; no application or existing test changed. This was an evidence-probe error, not an authentication failure.

## 4. Account and execution prerequisites

Use the existing dedicated accounts as `USER-A` and `ADMIN-B`. Their availability is now owner-confirmed; do not ask to create replacements. Before execution, the owner privately confirms:

- Distinct identities in the same named **isolated nonproduction** Supabase target, verified email for each, existing B membership and no A membership. Use aliases in shared evidence; do not enumerate accounts or record their passwords/IDs/tokens here.
- Current credentials are available for direct masked entry. **No password reset, email verification, account repair, Admin role grant or provisioning is required or allowed by this preparation.** If a credential fails later, stop rather than change it.
- The backend containing these accounts satisfies the Stage 2 isolation requirement. Dedicated accounts alone do not establish that the configured project is nonproduction. If they exist only in production, the inherited plan remains NO-GO until the target scope is resolved explicitly; no destination/photo writes are authorized in any case.
- The approved login pathway has no unapproved custom hooks, emails or business-data writes. Potential provider session/sign-in metadata/security logs are explicitly permitted before live execution. No signup/recovery callback or SMTP rehearsal is needed to test existing email/password login; those broader Stage 2 gates can remain unselected.
- A loopback-only, single-process server with development mode, debug/reloader off; reviewed action/egress controls permitting only approved auth forms, Auth validation/necessary refresh and named read-only database/RPC calls. Block signup/recover/resend/password update, business mutation RPCs, audit insertion, Storage operations and all Google API calls. No live sender or enforcement harness is claimed ready by this report.

After approval and target/control confirmation, the launch command would be:

```powershell
.\.venv\Scripts\python.exe -m flask --app app --no-debug run --host 127.0.0.1 --port 5000 --no-reload
```

This ordinary command does not itself enforce an operation allowlist. It was not run in this phase. Use the exact origin `http://127.0.0.1:5000`; do not switch to `localhost`, another port or profile.

## 5. Manual same-browser sequence — not executed

Use one **disposable browser profile** with separate User/Admin tabs sharing its cookie jar. Do not use a personal profile, password-save prompt, clipboard credentials, Show buttons, screen recording, HAR/network capture, request tracing or cookie-value inspection. The owner types existing passwords directly. Record only step IDs, aliases/realm match, status category and time; do not record secret fields or entire pages.

Budgets are inherited, not additive: first-login permission is **one A submission only**; the full login/isolation sequence below is **three total password submissions** (A once, B twice) and **three rendered local logout submissions**. The parent plan's fourth login slot remains unused/reserved; this preparation does not reallocate it. A failed or ambiguous submission consumes its slot. Do not repeat the sequence or test the reverse order live without a revised budget.

| Step | Manual operation after its approval | Expected result |
| --- | --- | --- |
| L0 | Open `/login` and `/admin/login` anonymously. Optionally visit protected `/user` and `/admin` once. | Forms 200; protected routes redirect to the appropriate login (normally 302), never reveal protected identity/data. Creates only local anonymous flow state; no sign-in. |
| L1 — first live login | Submit A once via `/login`; follow normal homepage redirect and open `/user` once. | Login 303 via `/`; protected User page 200 with A identity privately confirmed. User cookie/store contains A authority. Admin remains unsigned-in. |
| D1 — User-only denial | Before B signs in, visit `/admin` and `/admin/account` once; do not submit A to the Admin form. | Redirect to Admin login, no protected Admin content. `/user` still identifies A. This checks that ordinary User authority cannot enter Admin routes without another live sign-in. |
| L2 — simultaneous login | In the same profile open `/admin/login`, submit B once, follow `/admin`, then open `/admin/account` and revisit `/user` once each. | Admin current-caller membership passes; login 303, dashboard/account 200 with B; User stays A. A dashboard 503 is a demonstration failure even if authentication succeeded. |
| O1 — Admin logout | Submit the rendered Admin logout form once; visit `/admin` and `/user` once. | Admin redirects to login and loses local B authority; A remains authenticated. No provider-global sign-out. |
| L3 — restore B for the second logout direction | Open fresh `/admin/login` form and submit B once more (third password submission overall). | B restored; A unchanged. Do not reuse an old challenge or POST from browser history. |
| O2 — User logout | Submit the rendered User logout form once; visit `/user` and `/admin/account` once. | User requires login; Admin remains B. User local flow state is cleared; do not run registration/recovery concurrently. |
| D2 — Admin-only boundary | With only B's Admin session present, visit `/user` once. | It still requires User login; Admin cookie is not promoted into User authority. |
| O3 — final Admin logout | Submit B's rendered Admin logout form once, then check both protected roots once. | Both realms require login. This ends local authentication; provider sessions may still exist. |

Approval for L1 does **not** authorize L2, L3 or any logout. If the operator stops after L1, separately approved early cleanup may submit **one User local logout** instead of continuing; do not charge that cleanup as permission for another login. Closing the owned browser/server without a provider sign-out is the fallback local cleanup. An interrupted sequence cannot be restarted with a fresh budget implicitly.

### Authorization checks retained offline

`admin_required` wraps the Admin session requirement and checks fresh `rosago_is_admin` membership for the verified current caller on each protected request; it never trusts a caller-supplied role or the User cookie. `verify_admin_candidate` rejects nonmember credentials before installing Admin authority. Lookup errors are 503; authenticated nonmembers are 403; absent Admin authority redirects to its login.

Fresh isolated tests verify these cases and that B logged in through the User realm alone still does not gain an Admin session. A live attempt to submit A's correct credentials to `/admin/login` would nevertheless create a provider password-auth session before membership denial. It is **excluded** by the inherited zero-negative-probe allowance; request a separate explicit account/attempt budget if that live test is wanted. Do not modify membership, expire/revoke tokens intentionally, forge cookies/CSRF or try guessed passwords as part of this run.

After B legitimately signs in in the shared profile, `/admin` showing B while `/user` shows A is the expected independent-session behavior. It is not evidence that A acquired B's role. Assess the current realm/alias, not the last tab or account typed.

## 6. Expected side effects and cleanup limits

| Operation | Expected effects / limits |
| --- | --- |
| Password sign-in A/B | Supabase session/refresh state, last-sign-in or related security metadata/logs according to hosted configuration; local credential/web-state/cookie creation/rotation. Password and identity fields need not change. Exact hosted metadata is not inspected here. |
| Validation/protected reads | Auth user/claims/JWKS validation; application may explicitly refresh if needed, rotating provider session credentials/state. Do not deliberately force expiry/refresh. Read A's profile/upcoming trips/public catalog through `/`/`/user`; read B's membership, profile, dashboard catalog/counts and `rosago_admin_operational_overview`. |
| Local logout | Revoke only the chosen development credential namespace and its browser state. Does not normally call provider `sign_out` or delete accounts; provider sessions may survive. Local logout therefore still needs explicit execution permission here. |
| Application audit | No destination mutation/audit-insertion path is expected from these login/read/local-logout handlers. Supabase Auth security/audit logs may be generated independently. Do not equate provider Auth logs with RosaGo destination audit records or promise zero provider logging. |
| Hosted custom behavior | Undocumented hooks or email notifications are not assumed safe. Owner must identify them before execution; if they would send mail or modify business data, exclude the test until separately resolved/authorized. |

Existing A/B credentials can be used **as they are**: `sign_in_with_password` is not signup or password update. No destination/profile edits, publication changes, photo uploads, account creation, email requests or Gemini actions are part of this sequence. Read-only RPCs can be HTTP POST; any future egress guard must classify the exact RPC, not permit every database POST.

For approved cleanup, use only the rendered local logout forms in the selected sequence. Close the disposable browser and stop the owned loopback process when no continuation is authorized. No extra login merely to obtain a logout form. Provider metadata/logs and issued sessions are not rolled back by closing Flask; let sessions expire under owner policy. Provider revocation/global sign-out, account deletion, password restoration, membership repair or hosted cleanup each require separate specific permission.

## 7. Stop conditions

Stop the sequence immediately; retain only a sanitized category and mark remaining steps NOT RUN if any of these occur:

- Wrong target, nondevelopment mode, shared/experimental adapter selected, public bind, reloader/restart, missing enforcement controls or credentials exposed in logs/browser output.
- Invalid/unconfirmed credentials, 400/401/403/409/429/5xx, timeout, ambiguous success or unexpected redirect during a positive login/logout step. The intentional anonymous denial redirects in L0/D1/D2 are expected, not failures. No automatic retry, browser resubmit, password reset or email action.
- A replaced by B in the User realm, B replaced by A in the Admin realm, one logout terminates the other realm, missing cookie/store isolation, or stale/revoked local authority remains accepted.
- Ordinary User-only or Admin-only authority crosses into the other protected realm, membership is bypassed, or a protected page exposes unexpected personal/production data. End further access; do not probe additional routes or fix permissions during testing.
- Any unexpected database/business/profile/audit insertion, destination/photo modification, account mutation, mail/hook action, Google request or request-budget overrun. Stop the owned process to prevent further activity; do not attempt automatic database rollback or deletion.

If a submission times out, count it as consumed and do not infer it failed before the provider acted. Recheck/cleanup must stay within an approved scope; do not repeat the password POST. If logout itself fails, stop and close the owned local process/profile; do not invoke global provider sign-out as a fallback.

## 8. Exact approval for the first live login

Nothing is presently authorized beyond preparation. A minimal first-login authorization must explicitly cover:

- [ ] Existing **USER-A**, owner-entered unchanged credential, same privately confirmed isolated project as the existing B account; no account provisioning or repair.
- [ ] Loopback `http://127.0.0.1:5000`, single process, development architecture, no reloader/experimental adapters; target/action/egress controls reviewed before use.
- [ ] **Exactly one `POST /login` submission for A**, no automatic retry, with its necessary provider password-session issuance, validation and possible refresh/sign-in metadata/security-log effects; existing process-memory credential handling only, no extraction/persistent recording.
- [ ] Follow the normal redirect and permit the specific read-only `/`, `/user` and D1 protected-Admin denial checks, including A's own profile/upcoming-trip/public-catalog reads and necessary authentication validation. No Admin credential submission, mutation RPC, business write, mail or Gemini request.
- [ ] Choose ending: **pause before B login**; optionally authorize exactly one rendered **local User logout** to end the first test. Without logout permission, close owned local browser/server state; no provider sign-out. Local cleanup does not revoke the provider session.
- [ ] Stop on the conditions above, count ambiguity as the one consumed attempt and retain only alias/status/time evidence. No credentials in screenshots, traces, logs or artifacts.

Suggested approval text, with a nonsecret owner-confirmed target alias filled in:

> Authorize L1 and D1 only for existing USER-A in isolated target [alias], at 127.0.0.1:5000, with one password-login submission, necessary Auth validation/session/metadata effects and the named read-only page checks. Keep all credential entry private and masked. No retry, Admin login, account/email/password/business-data change or Gemini call. [Also authorize one rendered local User logout to finish / Stop after the read checks and close owned local browser/server state.] This authorization expires after this attempt/test window.

This is a template, not granted permission. Simultaneous A/B login needs a further explicit **L2** approval for one B submission and its protected read/RPC/session effects. Both logout directions additionally need **O1/L3/O2/O3** approval: one further B submission plus three local logouts, within the shared three-login sequence. A blanket “proceed with preparation” grants none of these live operations.

## 9. Recommendation

**GO for reviewing this preparation and the 99 passing isolated tests.** Route/form configuration, effective development selection and separate User/Admin namespaces are supported by source/configuration checks and synthetic runtime evidence. Existing dedicated accounts remove the need to create accounts or change credentials.

**NO-GO for the first live login now**, pending the exact scoped authorization, isolated target confirmation and ready execution controls. **NO-GO for simultaneous live sessions/logout until their additional steps are approved.** Real credential validity and hosted membership remain unverified; prior endpoint health is not account authentication evidence.

New files only in this phase directory: this report, offline harness and sanitized evidence. Existing runtime/configuration/tests and prior reports were not changed; no live server/browser was launched. No live sign-in/sign-out, email/password/account operation, database/Storage write, Google call, experimental adapter activation, startup-safeguard change, deployment, staging, commit or push. **Preparation complete; stop pending explicit approval.**
