# Phase 2T — Controlled Localhost Integration Verification, Stage 1

Verified **2026-11-06, Asia/Manila**. Reference: [Phase 2S preparation and approval requirements](../phase2s-live-demo-preparation/REPORT.md).

**Stage 1 complete: GO for the controlled read-only localhost scope and clearly labeled isolated authentication/Gemini demonstrations. NO-GO for claiming complete live authentication, inbox delivery, password recovery or Gemini generation.** Public Supabase Auth configuration reads succeeded; local routes and isolated regressions were checked without account operations. Stage 2 remains subject to the separate permissions below. This report does not authorize live operations.

## 1. Verification scope and evidence

New evidence:

- [verification-results.json](verification-results.json): actual-configuration startup, local anonymous route results, session/cookie attributes, bounded public Auth reads and preservation checks.
- [isolated-results.json](isolated-results.json): fresh isolated regressions and redacted configuration assessment.
- [frontend-results.json](frontend-results.json): registration, verification and recovery script checks.
- [verify_stage1.py](verify_stage1.py): reproducible Stage 1 harness; uses the Phase 2S runner with its output directory redirected here, preserving prior evidence.

Actual application pages were exercised **in-process through Flask's test client**, with origin `http://127.0.0.1:5000`, existing configuration and provider networking blocked. No listening server or real browser was launched; these results do not establish a fresh browser/TCP demonstration. The only external application-provider requests were exactly two GETs to the configured Supabase public Auth `health` and `settings` endpoints. No database/Storage endpoint, Auth management API, account lookup, live sign-in, email endpoint or Google API was called.

The Auth reader rejects privileged key shapes using `PublicPlacesClient`'s existing public configuration validation. It uses a 10-second HTTPX operation timeout, no retries/redirects/environment proxy and a 64 KB response bound. Only status codes and three public booleans were retained. Project hostname, credentials, provider bodies and cookie values were not archived.

Reproduce only the authorized Stage 1 checks:

```powershell
.\.venv\Scripts\python.exe docs/admin-finalization/phase2t-controlled-verification/verify_stage1.py
node tests/test_registration_frontend.js
node tests/test_verification_frontend.js
node tests/test_recovery_frontend.js
```

The main command repeats two public Auth reads. `--refresh-regressions` reuses saved local/Auth observations and runs only fresh offline regressions; it does not refresh live observations. No live-operation sender was added.

## 2. Flask routes, redirects and session configuration

Actual configuration loaded successfully with debug disabled, `RealmSessionInterface`, distinct User and Admin `NormalAuthStore` instances, and no shared-session extension. `ROSAGO_AUTH_MODE` remains absent, selecting the existing development mode. Neither an adapter nor a different mode was selected to make this check pass.

| Anonymous GET | Observed status | Assessment |
| --- | --- | --- |
| `/login` | 200 | User login form renders. |
| `/admin/login` | 200 | Separate Admin login form renders. |
| `/register` | 200 | Registration form renders; no signup submitted. |
| `/verify-email` | 200 | Verification page renders without creating a pending account flow. |
| `/forgot-password` | 200 | Recovery request form renders; no email submitted. |
| `/auth/callback` | 200 | Informational page only; no verification/login authority. |
| `/auth/reset-callback` | 400 | Missing code rejected before provider access. |
| `/reset-password` | 403 | Missing recovery grant rejected. |
| `/verify-email/resend` | 405 | GET cannot send a verification message. |
| `/logout`, `/admin/logout` | 405 | Logout is POST-only. |
| `/auth/status` | 200 | Anonymous status endpoint available. |

The inspected route map registers GET/POST for login, registration, verification, forgot-password and reset-password forms; GET-only callbacks; POST-only resend/logout actions. Flask also supplies HEAD/OPTIONS as applicable. Those methods are recorded in the evidence. No POST was sent using actual provider configuration. Synthetic POST contracts were tested separately.

Both anonymous cookies were present with HttpOnly and SameSite=Lax: User `session` at `/`; Admin `rosago_admin_session_dev` at `/admin`. Secure is false in this existing HTTP development configuration; this is limited to localhost. Cookie attributes and separate stores are not proof of live authenticated A/B sessions.

Source review and isolated tests confirm password login validates provider session/user/claims and confirmed email before establishing local authority. Admin additionally checks `rosago_is_admin` for the authenticated current caller. Cross-realm authority, CSRF, expiry and local logout isolation remain enforced. The production startup refusal is exercised by the isolated independent-session suite; it was not disabled. Process-local authority/pending flows are lost on restart and must not be demonstrated with multiple workers or a reloader.

### Redirect checks without mail

| Flow | Exact source destination / requirement | Stage 1 conclusion |
| --- | --- | --- |
| Signup completion | `http://127.0.0.1:5000/auth/callback` | Destination exists; callback does not prove email confirmation or authenticate. |
| Recovery | `http://127.0.0.1:5000/auth/reset-callback` | Destination exists and fails closed without a code. Transport contract includes S256 challenge and `redirect_to`. |
| OTP confirmation | Registration redirects to `/verify-email`; numeric code entered there | Mocked signup/OTP/resend contracts pass; actual message/template unverified. |
| Successful recovery exchange | 303 to `/reset-password` after same-browser pending PKCE/user/claims checks | Tested with synthetic credentials only. |

Do not substitute port 5099 from Phase 2R or switch between `localhost` and `127.0.0.1`. A callback URL existing locally does not establish that the hosted redirect allowlist accepts it. No confirmation link/code was followed against Supabase.

## 3. Existing Supabase Auth and environment assessment

Fresh public read results:

| Check | Result |
| --- | --- |
| `GET /auth/v1/health` | HTTP 200. |
| `GET /auth/v1/settings` | HTTP 200. |
| Email provider | Enabled. |
| Signup disabled | False: signup allowed by public configuration. |
| Automatic email confirmation | False: email confirmation required. |

These establish endpoint reachability and public settings only. Hosted Site URL/redirect allowlist, Confirm signup/Recovery templates, SMTP sender credentials/domain, delivery eligibility, recipient restrictions, rate limits, account email confirmation, Admin membership and authenticated RPC/RLS behavior remain unverified. No privileged configuration access was used, and no hosted setting was saved. An owner must review these settings read-only before Stage 2; the Stage 1 request does not provide a management connection or authorize configuration changes.

Fresh redacted environment checks:

| Variable / classification | Result |
| --- | --- |
| `SUPABASE_URL` | Present; HTTPS origin shape accepted. |
| `SUPABASE_KEY` | Present; public-key shape accepted before public reads. Provider reads succeeded; this does not qualify every privilege/endpoint. |
| `FLASK_SECRET_KEY` | Present; at least 32 characters. Entropy not measured. |
| `ROSAGO_AUTH_MODE` | Absent; development default. |
| `GEMINI_API_KEY` | Present; header/model configuration syntax accepted. Not authenticated with Google. |
| `GEMINI_MODEL` | Absent; effective code default `gemini-3.5-flash-lite`. |

No secret value was printed. Hosted Supabase Auth handles mail; missing local SMTP variables are not themselves evidence of a defect. The Storage secret is unrelated to these authentication checks and was not used. No assertion is made that the configured backend is disposable/nonproduction: the owner must identify the Stage 2 target explicitly.

## 4. Gemini request handling and fallback

No Gemini API operation occurred: no model listing, token count, generation or authenticated Google probe.

Reviewed current `gemini_service.py` and protected AI callers in `app.py`:

- Fixed `v1beta/models/{model}:generateContent` POST endpoint; key confined to `x-goog-api-key`; model validator rejects path/query syntax. The default name is syntax-valid; its existence, availability, schema support and entitlement for this project remain unverified.
- Request contains `systemInstruction`, a user `contents` part carrying JSON task/context, JSON MIME type and `responseJsonSchema`; temperature 0.2, one candidate, **1,800 output tokens** in the application path. No tools/database authority.
- Encoded request capped at 64,000 bytes and streamed response at 256,000 bytes. Bytes do not establish a token/spending limit.
- HTTPX timeout 12 seconds per operation/inactivity interval; redirects and environment proxies disabled. No overall elapsed-time deadline. Process-local two-second pacing across AI calls is not a project quota or cost cap. No automatic retry or generation on GET.
- One STOP candidate required; malformed, oversized, duplicate-key, refused/truncated output, unknown IDs and invalid task fields fail validation. Thought text/signatures are excluded. Provider errors, timeout/network failures and 429 return unavailable without disclosing provider text or credentials.
- Protected POSTs check authentication/origin/CSRF. Failed explanation leaves deterministic recommendations/preview usable; failed chat shows a fixed unavailable state and does not save a successful answer. Advisory output is not proof of factual correctness.

The Phase 2S [minimal smoke payload](../phase2s-live-demo-preparation/gemini-smoke-request.json) remains prepared and unexecuted. Its **128-output-token** allowance is incompatible with clicking the current application's **1,800-token** AI action under the same permission. A provider smoke test and full in-app acceptance need separate budgets.

## 5. Regression results

Fresh isolated run: **214 Python tests passed, zero failures/errors/skips** across the 13 Phase 2S modules plus normal-auth SDK adapter, Admin authorization and strong-password policy modules. Exact timing/module list are in `isolated-results.json`.

Coverage includes both User/Admin login orders, independent local logout/expiry/revocation, cross-realm CSRF/cookie rejection, membership denial, fixation, recovery isolation, password-update identity/grant contracts, safe diagnostics, Gemini structured requests, timeout/quota/refusal/invalid-output fallback and protected AI route behavior. Mocked mutation-attribution/password-update tests write only fixtures; no real account or business data is changed.

Tests execute with real credentials removed, dotenv disabled, development mode selected and socket/DNS/send operations blocked. Gemini uses MockTransport and Auth SDK boundaries use synthetic fixtures. Local actual-configuration GET checks and isolated regressions each recorded **zero blocked-network attempts**. The rendered recovery regression launches its reviewed offline Node fixture with synthetic page data.

Frontend checks passed: **9 registration tests**, **3 verification countdown tests**, and the recovery password-validation/visibility fixture. These do not substitute for an inbox or live browser test.

Harness correction: the first combined run globally muted logging during the public/local review and inadvertently kept it muted for diagnostic assertions, producing 26 assertion failures (including subtests) and one error. Logging state is now restored before regressions; the offline-only rerun passes. No application/test behavior was changed to obtain that result and no public request was retried because of it.

Preservation check compared **360 existing files**, including runtime Python, requirements, `.env`, tests, templates, static assets, migrations and Phase 2R/2S evidence: all unchanged. Only aggregate preservation results are saved; no secret-file digest is disclosed. Generated Python cache files are excluded. No server/browser was left running by this phase.

## 6. Remaining blockers and application issues

| Item | Classification | Required next action |
| --- | --- | --- |
| Authorized isolated backend, existing User A/Admin B and mailbox not identified | Stage 2 prerequisite | Owner supplies private target/account aliases and permission scopes. No credentials in reports/chat. |
| Live password/session acceptance and current-caller Admin membership/RPC untested | Acceptance gap | Controlled approved sign-ins and protected reads; no role assignment. |
| Hosted allowlist, templates, SMTP and actual inbox delivery unverified | Configuration/acceptance gap | Owner read-only settings review, then separately approved email/OTP/recovery checks. No assumed SMTP defect. |
| Recovery/email form success cannot prove delivery | Intentional generic response | Confirm inbox receipt independently; never keep resending after uncertainty. |
| `/forgot-password` lacks route-level CSRF/origin validation and local resend throttling | Existing application hardening gap | Add controls in a separately scoped code change before broader exposure; provider limits alone are insufficient local controls. No abuse/load probe performed. |
| Hard-coded 5000 callback origin | Demonstration constraint | Keep exact origin and same browser; centralize validated configuration in a future change if other origins are needed. |
| Process-local session/recovery/email state | Local architecture constraint | One process, no reloader/restart during flows; do not activate experimental adapters. |
| Gemini model/key/project eligibility and cost controls unknown | Acceptance/approval blocker | Owner establishes exact model and enforceable no-charge/bounded paid scope. |
| Gemini lacks total deadline and configurable output-token ceiling | Existing limitation | Future reviewed hard deadline/token configuration; Stage 2 smoke sender must enforce its smaller budget separately. |

No fresh route/session regression or conclusive hosted Auth/Gemini configuration defect was found. Unknown hosted settings and untested entitlement must not be reported as confirmed provider failures. Stage 1 did not change runtime code or attempt fixes outside the requested read-only scope.

## 7. Stage 2 manual checklist and expected outcomes

**All steps below are pending approval.** Check only the chosen gates; a Stage 2 approval must identify exact targets, operations and ceilings. Do not infer write permission from “localhost”: hosted authentication still creates provider state.

### A. Setup and approvals before any live action

- [ ] Owner identifies an **isolated nonproduction Supabase target**, existing disposable User A and separate existing Admin B, plus an owned disposable mailbox. Confirm distinct IDs, verified email for login and existing B membership without changing roles/accounts.
- [ ] Owner privately reviews hosted Site URL and exact callback allowlist: `http://127.0.0.1:5000/auth/callback` and `http://127.0.0.1:5000/auth/reset-callback`. Confirm numeric `{{ .Token }}` Confirm signup template, unchanged compatible PKCE recovery template, SMTP sender/recipient eligibility, quotas/cooldowns. Expected: no mismatch. If any setting needs editing, request a separate specific configuration-change permission first.
- [ ] Authorize any needed local-only target configuration, keeping secrets private. Keep development mode and production startup refusal. Use one loopback process, debug/reloader disabled, no experimental adapter. Future live harness must allow only approved operations/egress and block business/profile/trip/photo/audit writes.
- [ ] Specify allowed protected pages, provider claims/user validation, possible refresh/session/security-log effects, evidence policy and stop conditions. The Phase 2R read-only POST blocker cannot be treated as an authorized live test harness.

After the target and actions are approved, the ordinary local launch command is:

```powershell
.\.venv\Scripts\python.exe -m flask --app app --no-debug run --host 127.0.0.1 --port 5000 --no-reload
```

This command alone does not enforce a future provider/action allowlist; those controls must be prepared before side-effecting submissions. Use a disposable browser profile throughout.

### B. User A / Admin B sign-in gate

1. Explicitly authorize **at most four total password-sign-in submissions**, zero intentional invalid-password probes, zero provider-wide sign-outs and zero business writes. Count submitted attempts even when a response is ambiguous; stop on 401/403/429/503/timeout rather than consuming the ceiling by retrying.
2. Open `/login`; submit A once through its rendered form. Expected: User protected page and A identity; no auth credentials exposed in URLs/browser output. This creates real provider session/log state.
3. In the same cookie jar, open `/admin/login`; submit B once. Expected: B passes existing current-caller Admin RPC and reaches Admin dashboard. `/user` must still identify A. Record aliases and cookie attributes only.
4. Submit Admin logout. Expected: B local realm logged out, A retained. Submit B login once more (third password attempt), then User logout. Expected: A local realm logged out, B retained. Finally submit Admin logout. No global provider sign-out.
5. Reserve the fourth password attempt for **one** approved follow-up login, such as post-reset A or the verification account. It cannot cover both. Reverse-order live rehearsal, additional accounts, refresh experiments or further logins require an explicitly revised ceiling; both orders are already isolated-tested.

### C. Signup / email verification gate — optional, separate permission

1. Authorize exactly **one disposable account creation**, its expected profile/signup-hook effects, **one signup email**, and **one valid OTP confirmation** in the isolated target. Existing confirmed A/B accounts cannot demonstrate first-time confirmation. Without this permission, skip the live signup flow.
2. Submit `/register` once on the exact 5000 origin. Expected: 303 to `/verify-email`, pending state and resend cooldown. Keep server/browser running; pending state lasts 30 minutes.
3. Owner opens the mailbox privately and enters the received numeric code into `/verify-email` in the same browser. Expected: verified state, no automatic normal login. Record receipt and elapsed time only. A legacy link callback page alone is not a PASS.
4. Baseline allows **zero resend emails**. If required, separately authorize one additional resend, wait at least 60 seconds and any longer provider limit, then submit once. Do not run live invalid/expired/replay OTP probes under this allowance.
5. If password login for this new account is requested, allocate the reserved fourth sign-in or obtain a new explicit budget. No implicit account deletion/cleanup permission.

### D. Password recovery gate R1 — request, delivery and exchange only

1. Authorize **one recovery request/email** for the named existing disposable account and **one PKCE code exchange/recovery session creation**. Do not target a production password/account.
2. Submit `/forgot-password` once. Expected: generic response; confirm actual mailbox receipt separately. No mail after a timeout or generic success means stop for owner inspection, not resend.
3. Open the recovery link in the initiating disposable browser, exact host/port, within the 600-second local bound and provider expiry. Expected: validated callback redirects 303 to `/reset-password` with valid CSRF; bare reset URL access does not grant authority. Do not record the link/code/token.
4. **Stop before password submission.** R1 does not authorize a password change; real reset completion remains unverified if R2 is not approved.

### E. Password recovery gate R2 — separate password-write permission

1. Explicitly authorize **one password update** for that disposable nonproduction account, grant consumption and any account-specific provider session invalidation. Privately choose a compliant new test password.
2. Submit the reset form once. Expected: successful update and return to login; recovery grant cannot be reused. Use one allocated sign-in attempt to verify the new password. Do not intentionally try the old password, restore it, or repeat an ambiguous update without fresh approval.
3. Cross-account session preservation can remain covered by isolated evidence. A further live sequence keeping B authenticated through the reset must be separately scheduled within a revised login budget; do not add B sign-ins to the four-attempt ceiling silently.

### F. Gemini gate — separately approved one-request smoke test

1. Owner names the project/key alias and exact entitled model and confirms schema compatibility and thinking/output accounting. No model-list or countTokens calls are included. Do not change the model by guessing.
2. Explicit ceiling: **one generateContent POST total**, one candidate, **512 input tokens including text/schema** verified using approved offline/available owner evidence, **128 output tokens**, no retries/redirects/tools/grounding. Use only the unchanged synthetic [Phase 2S smoke payload](../phase2s-live-demo-preparation/gemini-smoke-request.json). If the input budget cannot be verified, stop.
3. Default permitted cost remains **US$0.00**, contingent on verified no-charge allocation and controls preventing paid spillover. A quota display or budget alert alone is insufficient. Billable testing requires a separate exact dollar ceiling and verifiable enforcement. Stage 1 grants neither free nor paid Google requests.
4. Before sending, prepare a reviewed one-attempt harness enforcing payload/model/endpoint checks and a 20-second total deadline plus connection/read limits. The sender is not implemented/executed by Stage 1. A timeout consumes the one-request allowance.
5. Expected: HTTP 200, one STOP candidate and exact `{"answer":"RosaGo"}`. On refusal, unsupported model/schema, 4xx/429/5xx, truncation or timeout, stop and retain unavailable behavior. Save status/sanitized category and supplied usage only; no key/provider envelope. Any second request needs new permission.
6. This verifies transport/schema only. The current in-app action has a 1,800-output-token ceiling and a larger context: do not click it under this smoke allowance. Full in-app generation needs a separately approved request/input/output/cost budget.

### G. Stop and evidence rules

- [ ] Stop on unexpected writes, origin mismatch, provider throttling, ambiguous success or missing quota controls. No automatic retries, resends, account creation, password restoration or cleanup writes.
- [ ] Retain only alias/realm matches, status codes, elapsed time, cookie attributes and sanitized usage/categories. No keys, addresses, passwords, email links, OTPs, tokens, raw provider bodies or personal screenshots in shared evidence.
- [ ] Close owned local server and disposable browser. Provider account deletion, hosted changes, global sign-out and other cleanup need additional specific approval. Local logout does not prove provider session revocation.

## 8. Decision and preservation

**GO: Stage 1's bounded read-only and isolated scope.** The anonymous local authentication routes, separate local session stores/cookies, public Auth settings and isolated failure/success contracts are verified. The earlier public catalog/map/weather qualification remains Phase 2R evidence; those integrations were not re-probed here.

**NO-GO: complete live localhost authentication/email/recovery/Gemini demonstration.** The remaining gates are authorized isolated accounts/target, hosted redirect/template/SMTP review, real session/membership and inbox acceptance, separately permitted password completion, and model/quota/cost-qualified generation. A passing public endpoint or synthetic test cannot close those gaps.

No live sign-in/account modification, email/password operation, database/Storage write, Gemini API request, experimental adapter activation, safeguard change, deployment, staging, commit or push occurred. Existing files in the preservation scope remained unchanged. **Stop after Stage 1; wait for explicit scoped Stage 2 approval.**
