# Phase 2S — Controlled Live Authentication and Gemini Verification Preparation

Prepared **2026-11-06, Asia/Manila**. Reference: [Phase 2R](../phase2r-live-integration-verification/REPORT.md).

**GO for the previously qualified read-only localhost demonstration and isolated authentication/AI demonstration. NO-GO for claiming a complete live User/Admin, email, recovery and Gemini demonstration.** Fresh isolated checks passed; hosted identity/mail settings, authorized test accounts and Gemini entitlement/quota remain acceptance gates. No live provider request was made during Phase 2S. Public documentation browsing did not use application credentials.

## 1. Blockers and root causes

| Area | Exact cause / evidence boundary | Required resolution |
| --- | --- | --- |
| User sign-in | Local route and mocked credential verification work. Phase 2R checked only public Auth health/settings. No approved account password/session operation has been exercised. | Authorize an existing disposable User A in an isolated backend; verify password, confirmed email, claims and protected page access. |
| Admin sign-in | Password authentication alone is insufficient: the current caller must pass `rosago_is_admin` through the authenticated client. Hosted membership/RPC/RLS acceptance for a test Admin has not been checked. | Authorize a separate existing Admin B and read-only membership/dashboard requests; no role grants or membership changes. |
| Email verification | Phase 2R reported email enabled, signup enabled and confirmation required. These public settings do not expose SMTP, recipient restrictions, email templates or delivery. RosaGo expects a numeric OTP, not merely a successful link callback. | Owner reviews hosted Confirm signup template against `docs/supabase-confirm-signup.html`, SMTP/sender and recipient eligibility; separately approve one test signup/email/OTP flow in an isolated backend. |
| Recovery | Callback is fixed to port 5000. Phase 2R's port 5099 probe never rehearsed it. Hosted redirect allowlist, recovery template and real PKCE exchange/claims remain unverified. | Confirm exact callback allowlist and same-browser flow; separately authorize recovery mail and code exchange. Password submission requires an additional disposable-account write permission. |
| Gemini | Local key passes header syntax validation. Model defaults to `gemini-3.5-flash-lite`; syntax acceptance does not prove model existence, access, structured-output compatibility, quota or billing safety. | Owner confirms the exact model/project and hard quota/cost controls before one bounded synthetic request. |
| Local process lifetime | Development authority, pending verification and recovery state live in memory. Restart, multiple workers or a reloader can lose the flow. | One loopback process, debug/reloader disabled; finish flows without restart. Production safeguard stays enabled. |

These are unverified acceptance/configuration gates, not evidence that a provider rejected a real login or that SMTP/key/model is defective. No failed live credential or generation response was observed in this phase.

## 2. Authentication configuration assessment

Fresh offline review merged `.env` and process environment using the application's environment precedence. Only presence/boolean classifications were retained in [isolated-results.json](isolated-results.json).

| Setting | Result |
| --- | --- |
| `SUPABASE_URL` | Present; HTTPS origin shape accepted; hostname withheld. |
| `SUPABASE_KEY` | Present; value withheld. Presence alone does not verify key type, privileges or validity. |
| `FLASK_SECRET_KEY` | Present; at least 32 characters. This does not measure entropy. |
| `ROSAGO_AUTH_MODE` | Absent; existing `development` default selected. |
| `GEMINI_API_KEY` | Present; accepted by service syntax checks; value withheld. |
| `GEMINI_MODEL` | Absent; code default selected. |
| Hosted Site URL, redirect allowlist, SMTP/sender, templates, recipient restrictions and quotas | Not inspected; no management credentials used. |

No local SMTP variables are required by these routes: the hosted Supabase Auth service sends mail. A Storage secret is unrelated to authentication or mail readiness and was not used. Existing Phase 2R read-only connectivity results are historical evidence, not newly repeated live results.

### Route and authority review

| Route | Methods / expected behavior |
| --- | --- |
| `/login` | GET form; POST requires origin/CSRF and bounded login attempts. Password adapter uses fresh clients with session persistence/auto-refresh disabled; verifies claims, user identity and confirmed email before establishing authority. Success redirects via `/` to the User flow; only a validated `add_place` slug is accepted as continuation. |
| `/admin/login` | GET form; strict POST fields, origin/purpose-bound challenge and rate limit; password verification followed by current-caller Admin authorization. Admin cookie/store separate from User. |
| `/register` | GET/POST; successful provider signup creates a pending verification flow and redirects 303 to `/verify-email`. Signup is a real account write and may trigger database hooks. |
| `/verify-email` | GET/POST; pending-flow-bound numeric OTP verification, CSRF/origin checks, bounded attempts. Confirms email through a fresh SDK client; does not establish ordinary RosaGo login. |
| `/verify-email/resend` | POST; pending address only, CSRF/origin checks, atomic 60-second cooldown. This sends mail. |
| `/auth/callback` | GET informational completion page. It does not exchange arbitrary URL credentials or prove verification; it grants no login authority. |
| `/forgot-password` | GET/POST; valid email sends `/auth/v1/recover` with S256 challenge, 10-second timeout and no redirects. Generic accepted/rejected-provider presentation prevents account enumeration. A displayed success is not delivery evidence. |
| `/auth/reset-callback` | GET; requires a single code, same-browser pending PKCE state and permitted origin; exchanges code, validates user/claims/recovery method and consumes pending state before issuing a recovery-only grant. |
| `/reset-password` | GET/POST require a valid recovery grant; POST checks CSRF/origin/password policy and verified recovered identity before provider update. Direct anonymous access denied. |
| `/logout`, `/admin/logout` | POST with appropriate CSRF; development logout revokes local realm authority. Do not use provider-wide sign-out for this rehearsal. |

Registration's configured redirect is `http://127.0.0.1:5000/auth/callback`; recovery's is `http://127.0.0.1:5000/auth/reset-callback`. Use **127.0.0.1, port 5000 throughout**; switching to `localhost`, another port, another browser or a mail-app webview can lose cookies/PKCE state. The hosted allowlist must match the requested redirects. [Supabase redirect configuration](https://supabase.com/docs/guides/auth/redirect-urls).

The signup template must expose `{{ .Token }}` for RosaGo's OTP form; keep the recovery template compatible with its existing PKCE link. SMTP capability and recipient eligibility require owner inspection. [Supabase SMTP configuration](https://supabase.com/docs/guides/auth/auth-smtp), [password authentication and recovery](https://supabase.com/docs/guides/auth/passwords).

Source review also found `/forgot-password` has no route-level CSRF/origin guard or local resend throttle comparable to login/verification. Provider limits still apply. This did not block the isolated contract tests, but should be fixed in a separately reviewed code change before broader exposure. No abuse/load test was performed.

## 3. Gemini integration assessment

Reviewed `gemini_service.py`, its environment construction in `app.py`, AI route callers and existing contract tests.

- Fixed server-side endpoint: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`; model syntax excludes path/query injection. Key is only in `x-goog-api-key`, never the URL/browser payload.
- Request supplies `systemInstruction`, a JSON task/context in a user `contents` part, and `generationConfig` with JSON MIME type, `responseJsonSchema`, temperature 0.2, one candidate, maximum **1,800 output tokens**. No tools or database authority are offered. This is the documented generateContent API shape, subject to the selected model's supported schema subset. [Google REST reference](https://ai.google.dev/api/generate-content), [structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).
- Application cap is 64,000 encoded request bytes; streamed response cap is 256,000 bytes. These are byte limits, not input-token or monetary budgets.
- HTTPX uses `timeout=12`, redirects off and environment proxies disabled. This is a timeout per network operation/inactivity interval, **not a guaranteed 12-second total deadline**. A slow stream can exceed 12 seconds overall.
- Shared per-service lock permits at most one attempted call per two seconds; it records failed attempts too. There are no automatic retries. This is a process-local pacing rule, not a project quota or hard spending cap.
- Responses must have one candidate finishing `STOP`, permitted text parts and valid JSON without duplicate object keys. Thought text/signatures are excluded. Task validators enforce exact shapes, lengths and supplied destination IDs/interests. These checks do not prove every generated statement is factually grounded.
- Missing config, provider HTTP errors including 429, connection/read failures, safety refusal, oversized/malformed/truncated output yield `None`. Routes show fixed unavailable text; recommendations/preview remain usable and unchanged. Chat returns a fixed 503 unavailable page without accepting a successful answer into history. No raw provider errors/keys are exposed.
- GET pages do not generate. Explain/chat are explicit protected POST actions. Adjustment interpretation is advisory until the existing validated application operation applies it; do not use itinerary adjustment for the minimal smoke test.

Model access and actual billing tier remain unknown. No authenticated model listing, token-count call or generation was sent. Do not substitute a guessed model silently. Consider configurable token limits and an elapsed-time deadline in a later change; no runtime changes were made here.

## 4. Isolated test results

Command from repository root:

```powershell
.\.venv\Scripts\python.exe docs/admin-finalization/phase2s-live-demo-preparation/isolated_review.py
node tests/test_registration_frontend.js
node tests/test_verification_frontend.js
node tests/test_recovery_frontend.js
```

**196 Python tests passed, zero failures/errors/skips, 21.78 seconds.** Thirteen selected modules cover User/Admin login, redirect behavior, registration/OTP, callback behavior, recovery transport/PKCE/grants/password-update contracts, independent realms, Gemini transport/validation and AI route behavior. See the exact module list in [isolated-results.json](isolated-results.json).

The runner removes real environment credentials before loading tests, suppresses dotenv loading, selects only development mode and blocks socket connection/DNS/send operations. Auth SDKs are mocked; Gemini uses MockTransport; no real account/password/data is used. Outer network guard recorded **zero attempts**; inherited fixtures also deny network. Python's rendered-recovery test invokes the reviewed offline Node fixture with synthetic HTML. Raw test output, secrets and provider response bodies are not archived.

Frontend checks: **9 registration tests passed; 3 verification countdown tests passed; recovery password/visibility fixture passed**. These exercise scripts/DOM fixtures, not a real browser or email inbox.

Harness corrections: initial Python run had 195 passes and one harness error because clearing PATH prevented Node discovery. Preserving only ordinary executable/temp system variables resolved it. A separate `node --test` multi-file launch encountered sandbox `spawn EPERM`; executing each reviewed file directly passed. No application or existing test was changed to obtain a pass.

No live server, production backend, experimental adapter, real email, account signup, password update or Gemini quota was used. These results establish isolated behavior only.

## 5. Manual User A / Admin B login procedure — pending authorization

1. Owner identifies an **isolated nonproduction backend** and existing disposable accounts A (User) and B (Admin), with different IDs. Confirm verified email and B's existing membership without adding a role. Keep credentials in a private local entry mechanism; use only aliases in evidence. Do not assume the current `.env` is an isolated target.
2. After explicit approval of the target/configuration, run unchanged Flask on `127.0.0.1:5000`, one process, debug/reloader off. Retain development mode and startup refusal for production. The Phase 2R wrapper blocks POST and cannot perform this rehearsal; any future live harness must allow only the approved actions/egress, not remove all write controls. Block business/profile/trip/photo/audit mutations.
3. Use a disposable browser profile. Open `/login`, submit A once using its rendered CSRF form. Expect successful protected User access and User A identity, with no credential in URLs/cookies/screenshots. Stop on 401/403/429/503; no repeated guessing.
4. In the same browser cookie jar open `/admin/login`, submit B once. Expect B's Admin dashboard and successful membership check. Read only approved pages; `/user` must remain A. User `session` at `/` and `rosago_admin_session_dev` at `/admin` remain separate HttpOnly scopes; record attributes only.
5. Submit Admin logout; A must remain authenticated. Re-login B once if included in the approved budget; submit User logout; B must remain authenticated. Submit Admin logout to finish. Repeat in reverse order only if separately budgeted. Negative membership tests remain mocked unless explicitly added to approval.
6. Proposed live ceiling: **four total password sign-ins** (A once, B twice, A once for a subsequent recovery check if needed), zero intentional failed credentials, zero provider-wide sign-outs, zero business writes. A reverse-order rehearsal needs a revised explicit ceiling. Protected requests can validate/refresh tokens and cause provider session/security logs; approve these effects too.
7. Record only statuses, alias/realm match, local logout isolation and timestamps. Stop the server, discard the browser profile and let provider sessions expire under the approved plan; local logout does not prove provider revocation. Do not perform global cleanup/sign-out automatically.

## 6. Manual email verification and password recovery — pending authorization

### Verification

1. Owner confirms one controlled disposable mailbox and isolated project, signup permissions/hooks, numeric Confirm signup template, delivery eligibility and provider cooldowns. Obtain explicit permission for **one account creation plus one signup email and one OTP confirmation**. A pre-existing confirmed account cannot demonstrate new signup confirmation. Creating a new account remains prohibited in this preparation phase.
2. On the exact 5000 origin in the same disposable browser, submit `/register` once. Expect 303 to `/verify-email`, a pending flow and resend cooldown. Do not restart Flask; pending verification state lasts 30 minutes.
3. Owner reads the received message privately and enters its numeric code into `/verify-email`. Expect verified state and no automatic ordinary login. Continue to `/login` only under the separately approved sign-in budget. Callback-page rendering alone is never a verification PASS.
4. Proposed baseline: one signup mail, zero resend mails, one valid OTP submission. If testing resend is necessary, explicitly approve **one extra email**, wait at least the app's 60-second cooldown and the provider's longer limit if applicable, then submit once. Keep invalid/expired/replay cases isolated unless a separate live attempt budget is approved.
5. Record receipt yes/no and elapsed time only. No mailbox address, OTP, email link, token or full message in shared evidence. Stop at provider rejection or missing mail; do not keep resending. Account cleanup is a separate deletion permission, not implicit.

### Password recovery: two independently approved gates

1. Gate R1 authorizes **one `/forgot-password` request/email** for an existing disposable test account in the isolated project. Keep the initiating browser/profile/origin running. Success text is intentionally generic; independently verify inbox delivery.
2. Open the recovery link in that same browser within the pending/recovery window (local bound is 600 seconds; provider expiry also applies). Authorize one code exchange/session creation. Expect `/auth/reset-callback` to redirect 303 to `/reset-password` with valid CSRF; bare URL access, missing state and implicit-token links must not grant authority. Do not copy the link into reports or another browser.
3. **Stop before submitting a new password unless Gate R2 is explicitly approved.** A complete reset cannot be demonstrated under a no-password-change permission. R2 must name the disposable nonproduction account and permit exactly one password update plus recovery-grant consumption and any account-specific provider session invalidation. Production passwords/records remain out of scope.
4. If R2 is approved later, the owner privately chooses a compliant new test password, submits once, observes return to login and verifies one new-password login within the sign-in ceiling. Do not deliberately try the old password unless separately authorized. Check that an unrelated Admin B local session is preserved; live provider invalidation effects must be assessed separately from mocked isolation.
5. Any ambiguous timeout after submit: stop, inspect the result through the authorized account owner, and obtain permission before another update/mail. Never retry a possibly completed side effect automatically. Do not reset the password back as implicit cleanup.

## 7. Minimal Gemini smoke test — prepared, not executed

[gemini-smoke-request.json](gemini-smoke-request.json) contains a synthetic structured-output request asking only for `{"answer":"RosaGo"}`. No user/catalog data, auth/session context or history is included. This is a provider transport/schema smoke test; it does **not** establish that the full application prompt, 1,800-token configuration or every AI feature succeeds live.

Approval budget proposed:

- One exact approved project/key alias and model; **one generateContent POST total**, one candidate, `maxOutputTokens=128`, no retries, redirects, model listing, countTokens, tools, web grounding or follow-up application AI clicks.
- Input ceiling **512 tokens including all supplied text/schema**, to be verified by an owner-approved offline tokenizer or already available console evidence before sending. If it cannot be verified, do not execute. Do not add a token-count API call without separate approval. Confirm the chosen model's thinking/output accounting and support; do not blindly add model-specific thinking fields.
- Maximum authorized cost by default: **US$0.00**. Owner must establish that this exact request is confined to a verified no-charge allocation with controls preventing paid spillover. Remaining quota or a budget alert alone is insufficient. If a billable test is wanted, obtain a new explicit dollar ceiling and verifiable enforcement before execution. Key presence never establishes no-charge entitlement.
- Future harness must validate the payload/model/budgets, allow only the single fixed Google endpoint, use a one-attempt counter and a 20-second overall wall-clock deadline in addition to connect/read limits. A timeout spends the request allowance; it never permits an automatic retry. Harness implementation/execution is deferred until approval; no runnable live sender was added.
- Accept only HTTP 200, one STOP candidate and the exact expected JSON. 400/401/403/404/429/5xx, refusal, truncation, unsupported schema/model or timeout: stop, record a sanitized category, retain application fallback. Record token usage/status if supplied, never the key or raw provider envelope. A second request requires a revised approval.

The existing application path allows 1,800 output tokens and up to 64 KB request bytes; **do not use its AI button under this 128-token smoke-test allowance**. A subsequent application end-to-end request needs its own full-context/token budget and authorization. No pricing or free-tier eligibility is assumed.

## 8. Exact live permissions and approval checklist

Unchecked items mean **not authorized**. Identify projects/accounts by private owner-visible aliases, never secret values. A generic “proceed” should not be interpreted as permission for every optional action below.

| Proposed check | Real Supabase state / mail / potential charge |
| --- | --- |
| Offline regressions/configuration classification | None; completed. |
| Hosted configuration inspection | Read-only owner inspection; no configuration save. |
| User/Admin sign-in and protected reads | Provider session/history/log state; possible refresh token rotation. No intended business writes. |
| Signup | Auth account write, possible profile hooks and signup email. |
| OTP confirmation / resend | Confirmation state and possible temporary provider session / an additional email. |
| Recovery send / callback exchange | Recovery challenge/provider state and email / token consumption and recovery session state. |
| Reset submit | Password/account write and potential session invalidation. Only disposable nonproduction target. |
| Gemini smoke | External synthetic prompt transfer, project quota consumption, potentially billable generation absent verified controls. |

- [ ] **Target:** confirm isolated nonproduction Supabase project alias, mailbox ownership and existing User A/Admin B aliases; explicitly exclude production accounts/data. Approve any needed local-only target configuration without recording secrets.
- [ ] **Read-only setup:** owner confirms exact 5000 Site URL/redirect allowlist, OTP and recovery templates, SMTP sender/recipient eligibility and limits. Any hosted configuration change needs a separate named permission; this checklist does not authorize it.
- [ ] **Login:** authorize the exact four-sign-in ceiling described above, current-caller Admin RPC/protected reads, token validation/refresh and provider session/log effects. Specify approved pages and local logout; exclude business/audit/storage mutations and global sign-out.
- [ ] **Signup/verification, optional:** authorize one disposable account creation, expected hook effects, one signup email and one valid OTP confirmation. Specify a separate extra-email allowance if resend is requested. Otherwise skip the live verification flow.
- [ ] **Recovery R1, optional:** authorize one recovery email/request and one same-browser PKCE exchange for the named disposable account; explicitly stop before password submission.
- [ ] **Recovery R2, optional:** separately authorize exactly one password update on that nonproduction account, expected session invalidation and one verification login within the stated login budget. Otherwise complete reset remains NO-GO.
- [ ] **Gemini, separate approval:** identify project/key alias, exact entitled model, 512-input/128-output-token limits, one-request ceiling, verified quota/tier and hard cost ceiling/enforcement. Approve synthetic external prompt transfer. If US$0 cannot be guaranteed, stop or obtain a separately enforced paid allowance.
- [ ] **Execution controls:** localhost only; single process; no reloader/experimental adapters; startup safeguard retained; allow only selected routes/egress; stop on ambiguity, throttling, timeout or unexpected write. No automatic retries, cleanup writes, mail or account creation.
- [ ] **Evidence and ending:** retain aggregate statuses only; discard disposable local browser state and stop owned processes. Provider account deletion, password restoration, global sign-out or hosted cleanup require additional explicit approval.

## 9. Remaining issues, fixes and decision

Priority acceptance work: owner review of hosted URL/template/SMTP settings; identify disposable existing A/B accounts and test mailbox; approve narrowly bounded live session/email operations; confirm Gemini model entitlement and enforceable quota/cost limits. No hosted configuration defect is established until that review.

Recommended later code work: add origin/CSRF and application throttling to recovery-mail requests; centralize callback origin configuration with validation; make Gemini token ceilings configurable and add a total elapsed-time deadline. Keep recovery method/claims checks, unavailable states and production startup refusal intact. These are recommendations, not changes performed in this phase.

**Complete localhost demonstration: NO-GO pending the named live acceptance gates.** A successful isolated run cannot establish real inbox delivery, passwords, membership or paid API entitlement. **Controlled read-only catalog/map/weather demo: GO based on Phase 2R's bounded observations**, with its internet/availability limits; offline synthetic authentication/Gemini behavior can be shown clearly labeled as isolated. A smoke-test PASS alone would still leave full in-app Gemini generation unverified.

Only new Phase 2S documentation/evidence/harness files were added. Existing runtime code, configuration, tests, migrations and prior-phase artifacts were not intentionally modified. No deployment, staging, commit, push, live email, account creation, real password change, production record change or billable request occurred. No experimental session adapter was activated and no startup safeguard was disabled. **Preparation complete; stop pending explicit scoped approval.**
