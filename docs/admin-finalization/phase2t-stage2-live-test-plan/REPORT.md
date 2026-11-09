# Phase 2T — Stage 2: Controlled Live Integration Test Plan

Prepared **2026-11-06, Asia/Manila**. References: [Stage 1 results](../phase2t-controlled-verification/REPORT.md), [Phase 2S limits](../phase2s-live-demo-preparation/REPORT.md).

**Plan ready; every live test remains NO-GO until its individual approval and prerequisites are recorded.** This document is an ordered manual runbook, not authorization to execute. No account lookup/sign-in, signup, email, password change, database/Storage operation or Gemini request was performed while preparing it. No live sender or application changes were added.

## 1. Evidence and scope

Stage 1 recorded 214 passing isolated Python tests, passing registration/verification/recovery frontend checks, and public Auth health/settings HTTP 200/200. Email provider and signup were enabled; email confirmation was required. Actual-config anonymous pages and separate development cookie/store configuration worked through Flask's in-process test client. These are existing results, not fresh live results from this planning phase.

Outstanding gates: actual disposable account identities; hosted callback allowlist, OTP/recovery templates and SMTP delivery eligibility; authenticated Admin membership/RPC acceptance; real email/recovery acceptance; Gemini model entitlement and enforceable quota/cost controls. The configured backend must not be assumed disposable from the workspace location or `.env`.

Offline source review reconfirmed:

- Signup callback: `http://127.0.0.1:5000/auth/callback`; recovery callback: `http://127.0.0.1:5000/auth/reset-callback`.
- `migrations/0001_profiles.sql` defines an Auth-insert trigger that creates `public.profiles`; profile deletion cascades from Auth-user deletion. This describes repository design, not a newly inspected hosted schema.
- `rosago_is_admin` checks the current caller's existing membership. The Admin dashboard additionally reads catalog/counts and calls `rosago_admin_operational_overview`. A read-only RPC can use HTTP POST; HTTP method alone does not classify database side effects.
- Password reset invokes provider `update_user`, consumes the grant and returns 303 to `/login?password_updated=1`. It is a real credential change, even on localhost.

All live backend tests use one separate Supabase **test project** with matching reviewed schema/RPC/RLS and synthetic data. Existing disposable accounts in an otherwise isolated nonproduction project are acceptable if the owner explicitly confirms that scope. Production accounts, destination records, Storage and schema changes are excluded. Creating/provisioning the test project, applying migrations, adding Admin membership or preparing accounts is a separate owner task/permission, not part of these tests.

## 2. Exact account and target requirements

Actual addresses/IDs were not supplied in Stage 1 and were not discovered by querying Auth. Do not invent them. These three roles are the exact required identities; execution is blocked until the owner privately maps each alias to a concrete identity and target.

| Alias | Required identity | Tests | Required condition |
| --- | --- | --- | --- |
| `TEST-PROJECT` | Owner-designated isolated nonproduction Supabase project | T1–T5 | Same reviewed Auth/schema/RLS as intended demo; synthetic data only; target privately confirmed. |
| `USER-A` | One **existing**, dedicated email/password User | T1, T2, T4, T5 | Confirmed email; owned recovery mailbox; no Admin membership; disposable password/session history; no personal trips/data. |
| `ADMIN-B` | One **existing**, dedicated Admin with a different Auth ID from A | T1, T2 | Confirmed email; existing authorized membership; synthetic project-only Admin access. Never grant membership during testing. |
| `VERIFY-C` | One **not-yet-registered** address, different from A/B | T3 | Owner-controlled delivery-eligible mailbox; signup and its profile trigger effects must be explicitly authorized before creating this identity. |
| `GEMINI-TEST` | Owner-designated Google project/key alias | T6 | Private key, exact entitled model, verified token accounting and enforceable cost/quota scope. Separate from Supabase. |

Minimum existing accounts: **two** (A and B). Maximum new accounts in this plan: **one** (C), only under T3 approval. Reuse A for recovery; no fourth account is needed. A and C need independently addressable owned mailboxes; B's verified address may be another owned test address. Delivery eligibility for aliases/plus-addressing must be confirmed rather than assumed.

Private execution record to complete before approval:

| Field | Owner must fill privately | Public evidence retains |
| --- | --- | --- |
| Supabase target and project isolation confirmation | Actual project reference/origin and matching configuration | `TEST-PROJECT`, isolation confirmed yes/no |
| A/B mapping and distinctness | Actual emails/IDs, ownership, verified state, existing B membership | Aliases, distinct yes/no, role check outcome |
| C mailbox | Actual unused recipient and SMTP eligibility | `VERIFY-C`, eligible yes/no |
| Google target | Project/key alias, exact model, tier/controls, price evidence if paid approval is sought | Nonsecret aliases/model, approved ceilings |
| Operator, selected tests and expiry | Person, approved time window, operation budgets | Approval reference and dates |

Passwords, secret keys, access/refresh tokens, OTPs and callback links belong only in private local entry mechanisms. Never paste them into this report or chat. If existing A/B accounts are unavailable, stop; do not create replacements under a sign-in permission.

## 3. Shared execution controls and budget ledger

Before any live submission, owner approval **P0** must confirm the account/target mapping, read-only hosted settings review and the selected test IDs. Confirm exact callback allowlist, numeric `{{ .Token }}` Confirm signup template, compatible PKCE recovery template, SMTP sender/recipient restrictions and current limits. Identify any custom hooks or security-notification emails. Any configuration mismatch needs separate change approval; do not save hosted settings during this run.

Use one disposable browser profile/cookie jar and `http://127.0.0.1:5000` throughout, one Flask process, development mode, debug/reloader off. No experimental adapter, public bind, proxy tunnel or production safeguard bypass. After target/configuration approval, the local start command is:

```powershell
.\.venv\Scripts\python.exe -m flask --app app --no-debug run --host 127.0.0.1 --port 5000 --no-reload
```

Do not launch it against an unconfirmed target. This command does not enforce the test allowlist. Before execution, prepare/review controls that allow only the selected routes/provider actions, count attempts before sending, redact callback query logs and block database/Storage mutations. Stage 1's anonymous GET harness and Phase 2R's POST blocker cannot execute these tests unchanged. That execution harness remains an explicit release prerequisite; preparing this runbook does not claim it already exists.

Allow only rendered forms for the selected operation. Protected reads may require Auth user/claims/JWKS validation and token refresh; their provider session/rotation/log effects require approval too. Do not deliberately wait for expiry or trigger repeated refreshes. Permit only reviewed read RPCs, including `rosago_is_admin` and the dashboard's operational overview; block mutation RPCs such as `rosago_admin_mutate_destination`, table writes, uploads and audit insertion. Read only `/`, `/user`, `/admin/login`, `/admin`, `/admin/account` and the selected auth-flow pages/static assets. No Planner/profile editing, management search/listing, destination forms or AI buttons.

The overall ceilings are **not additive per test**:

| Operation | Maximum for the complete selected sequence |
| --- | --- |
| Password-sign-in submissions | **4 total**: T1 A once/B once; T2 B once more; fourth allocated explicitly to T5 A login. Failed/ambiguous submissions count. |
| Signup | **1**, C only. |
| Signup email / valid OTP verification | **1 / 1**. |
| Resend email | **0 baseline**; optional **1** only with separate P3R approval. |
| Recovery email request / PKCE exchange | **1 / 1**, A only. |
| Password update | **0 baseline**; **1** only with separate P5 approval. |
| Intentional wrong-password/OTP, replay, negative membership or load probes | **0**; retain isolated coverage. |
| Gemini generation | **0 until P6**; then **1 total**, no other Google API requests. |
| Business/database/Storage writes | **0**, except C's specifically approved Auth/signup-trigger effects; A's separately approved Auth password state is not a business-data permission. |

Baseline requested mail ceiling is **two messages** (signup and recovery), or three with the optional resend. If configured password-change/security notifications or custom hooks can send further messages or mutate other records, identify and separately approve them before the affected test; otherwise that test remains NO-GO. The intended request count is not a guarantee about a provider's internal mail processing.

T1 and T2 share the first A/B logins. If T1 ends and logs them out before T2 is approved, T2 cannot silently start a new sequence under the spent budget. Reverse-order rehearsal or login for C requires a revised allocation/approval. If T5 is omitted, the fourth slot is unused unless explicitly reassigned to C; it cannot serve both.

## 4. Test-by-test execution

### T1 — Existing-account User and Admin sign-in

**Approval P1:** two submissions total (A once, B once), provider session/history/log changes, Auth validation/possible refresh, and the named protected database reads/RPCs. No membership changes. P0 must already pass.

1. In the empty disposable profile, open `/login`; submit A's owner-entered credentials once with the rendered CSRF form. Follow the normal redirect via `/`, then open `/user` once.
2. Expected: successful login redirect (303), protected page 200 and privately confirmed A identity. `/` may read public places and A's own profile/upcoming trips; `/user` reads A's profile. These are reads only. Do not save or edit anything.
3. In the same cookie jar, open `/admin/login`; submit B once. Expected: current-caller membership passes; 303 to `/admin`, then 200 if dashboard data/RPCs are available. Open `/admin/account` once to privately confirm B identity. A dashboard 503 is not a complete Admin demonstration even if password authentication succeeded.
4. Open `/user` once. Expected: still A, while the Admin page remains B. Inspect cookie attributes only: User `session` at `/`, Admin `rosago_admin_session_dev` at `/admin`, HttpOnly/SameSite=Lax in existing HTTP development mode.
5. Continue directly to T2 only if P2 was granted before this sequence. Otherwise submit each realm's rendered local logout once and end T1.

**Side effects:** real provider sessions, sign-in metadata/security logs and possible refresh rotation; local memory/cookies/challenges; authenticated profile/catalog/aggregate reads and Admin authorization RPCs. No deliberate database business writes. Admin overview can read aggregate account/trip information, so use only the synthetic test project.

**Cleanup/rollback:** local logout clears realm authority, not necessarily provider sessions. Close the disposable browser when finished; let provider sessions expire under the owner-approved policy. Provider logs cannot be rolled back. Account-scoped revocation, if desired, is a separately approved cleanup operation, never a global sign-out.

**Stop:** wrong/unconfirmed credentials, membership denied, identity/realm mismatch, unexpected data/write, 401/403/429/503 or timeout. No reattempt, role grant or account repair.

### T2 — Independent User/Admin local sessions

**Approval P2:** continue from successful T1 without restarting; one additional B sign-in (third submission overall) and rendered local logouts. The full P1/P2 sequence uses three sign-ins. Recovery/registration flows must not be pending during these User logout steps.

1. With A and B signed in, submit Admin logout once. Expected: redirect to Admin login; `/admin` no longer grants B access, while `/user` still identifies A.
2. Submit B's Admin login once more using a fresh rendered challenge. Expected: B restored and A unchanged.
3. Submit User logout once. Expected: `/user` requires login, while `/admin/account` still identifies B.
4. Submit Admin logout once. Expected: both realms unauthenticated. Do not use provider-wide sign-out or revoke unrelated sessions.

**Side effects:** one new provider B session, possible validation/refresh effects, protected reads and local realm revocation/cookie changes. User logout clears the User browser session including pending recovery/verification references; therefore run this before T3/T4.

**Cleanup/rollback:** step 4 completes local cleanup. Prior provider sessions/security logs remain; no database restoration is needed. Abort cleanup uses only still-available rendered local logout forms or closes the browser; do not sign in again merely to obtain a logout form.

**Stop:** either logout clears the other identity, stale/incorrect actor appears, token/session state becomes ambiguous or any provider failure occurs. Reverse-order live login is excluded; isolated tests already cover both orders.

### T3 — Registration and numeric email verification

**Approval P3:** one C signup, one signup email, one valid OTP verification and explicitly enumerated signup-trigger/hook effects in the test project. A/B remain unchanged. Owner must confirm the hosted profile trigger/hook behavior before approving; repository migration text alone is insufficient.

1. Confirm C is unused privately from the owner's existing knowledge; do not run an account-enumeration request. Open `/register`, enter synthetic names, C's mailbox, an owner-chosen password and consent; submit once.
2. Expected: 303 to `/verify-email`, pending flow and resend countdown. Supabase creates C; the reviewed deployed profile trigger may create C's profile. No Admin membership, trips or destination writes are permitted.
3. Owner privately checks the mailbox. Operational wait ceiling: **five minutes** after submission, also respecting provider expiry and the 30-minute local pending-flow lifetime. This is a test stop deadline, not a promised delivery SLA. If missing, stop and record delivery unverified; do not register again.
4. Enter the delivered numeric code once on `/verify-email` in the same browser. Expected: verified success state, provider confirmation state updated, no automatic ordinary RosaGo login. Any temporary SDK OTP session is not a normal User session.
5. Do not follow the old link callback as proof of verification. Do not log C in under the default ledger; that needs explicit reassignment of the fourth slot if T5 is skipped, or a new ceiling.

**Optional P3R approval:** one additional resend email to C through `/verify-email/resend`, only while pending, after at least 60 seconds and any longer provider limit. Choose the original-mail path or one authorized resend path before entering the single valid OTP; no wrong/expired/replay probes. A provider 429 ends the test, even if a countdown later expires.

**Side effects:** Auth user creation, profile trigger/hook writes, signup mail, email-confirmation state and possible temporary provider OTP session. Resend may replace the active code and sends another message.

**Cleanup/rollback:** account creation and email delivery are not transactionally reversible. Leave C retained as an identified disposable test artifact unless a later **P7** explicitly permits deletion of C and its exact dependent rows. Close local browser state at the end; do not delete C, revoke it globally or run a rollback migration automatically. No profile/trip/Storage cleanup is expected beyond identified signup dependencies.

**Stop:** duplicate address, unexpected automatic confirmation/template, missing mail, unexpected hooks/writes, 429, delivery to another recipient, OTP rejection or server restart. Do not create a replacement account.

### T4 — Password recovery request and PKCE exchange, without password update

**Approval P4:** one recovery request/email to A, one same-browser PKCE exchange and its provider recovery-session/token-consumption effects. No password update. T2 local logout sequence must already be complete; do not restart after initiating recovery.

1. Open `/forgot-password`; submit A's address once. Expected: generic response. It does not prove the account exists or email was delivered.
2. Owner checks A's inbox privately for at most five minutes. Open the recovery link in the **initiating browser** on the exact 5000 origin, within the remaining 600-second local window and any shorter provider expiry. Do not use a mail-app webview or copy the link into evidence.
3. Expected: `/auth/reset-callback` validates pending PKCE state, verified user/claims/recovery method and redirects 303 to `/reset-password`; form has valid CSRF and recovery-only authority. Do not treat a 200 error page or arbitrary callback rendering as acceptance.
4. **Pause before entering/submitting a new password.** Proceed to T5 only if P5 and the reserved fourth sign-in allocation are approved and still within the valid recovery window. Otherwise end T4 and allow the recovery grant to expire; a later fresh recovery email needs a revised P4 budget.

**Side effects:** recovery challenge state and mail; code consumption and provider recovery session; local pending state/grant. No password/business-data change. An opened code/link cannot be unconsumed, and delivered mail cannot be recalled.

**Cleanup/rollback:** stop/close the disposable local process/profile when no approved continuation remains, discarding process-local grants; provider sessions expire under approved policy. No implicit provider revocation, new recovery mail or password change.

**Stop:** different host/browser, missing/expired pending state, missing mail, provider claims/method rejection, callback error, 429 or ambiguous exchange. Do not weaken recovery validation to make a link pass.

### T5 — Complete reset on disposable A only

**Approval P5:** exactly one A password update, possible provider session invalidation, any identified notification effects and one new-password A login using the fourth overall sign-in slot. P4 must have succeeded; A must be disposable/nonproduction. P5 is separate from permission to send a recovery email.

1. Owner chooses a new compliant test password privately and submits the valid `/reset-password` form once. Expected: update succeeds, recovery grant consumed, 303 to `/login?password_updated=1`.
2. Enter A's new password once on `/login`. Expected: protected `/user` 200 with A identity. Do not try the old password, replay the grant, sign B in again or deliberately trigger another refresh under this budget.
3. Submit A's local logout once. Record success and that the owner securely retained A's new test password.

**Side effects:** real credential change, provider account/session/security state and any separately approved notification. Consumption can occur even if later client cleanup/response validation fails. Do not infer unrelated live B provider-session behavior from the isolated tests; additional live cross-account reset checks require a revised sequence/budget.

**Cleanup/rollback:** retain the new disposable credential privately. Restoring the old password is another credential write and is not authorized. If the update times out or is uncertain, mark indeterminate and stop; owner inspection/further verification requires explicit scope before any second change.

**Stop:** uncertain provider completion, invalid grant/CSRF, policy rejection, 429 or login failure. The UI may offer retry; this plan does not authorize it. No production password or account is ever an acceptable substitute.

### T6 — Minimal Gemini connectivity and structured-output smoke test

**Approval P6, separate from all Auth permissions:** one exact Google project/key alias/model; one synthetic external request; verified token/quota/billing controls. No account is needed and Supabase must not be accessed by this test.

1. Owner confirms the selected model exists and is entitled for this key, supports the smoke schema and has understood thinking/output-token accounting. `gemini-3.5-flash-lite` is the application's current syntax-valid default, not a verified entitlement. Do not guess another model or call model-list/countTokens APIs.
2. Use the unchanged [Phase 2S payload](../phase2s-live-demo-preparation/gemini-smoke-request.json), asking only for `{"answer":"RosaGo"}`. Verify **at most 512 input tokens including text/schema** through an approved offline tokenizer or available owner evidence. No personal data/history/catalog/auth context. Unverifiable token count means NO-GO.
3. Before sending, prepare/review a dedicated manual one-shot sender with fixed Google host and approved model, key only in `x-goog-api-key`, validated payload, a persisted consumed-before-send attempt counter, redirects/retries/environment proxies off, bounded response and **20-second overall wall-clock deadline** plus connection/read timeouts. The current app's 12-second per-operation timeout does not enforce this deadline. This sender is a release prerequisite, not a completed artifact of this planning phase.
4. Upon P6, send exactly **one POST** to `https://generativelanguage.googleapis.com/v1beta/models/{approved-model}:generateContent`. Maximum **one candidate, 128 output tokens**. Mark the attempt consumed before dispatch; process restart, timeout, rejected response or uncertain delivery must never reset permission.
5. Expected: HTTP 200, one STOP candidate and JSON exactly `{"answer":"RosaGo"}`. Save only status, elapsed time and supplied token usage/sanitized category. No key or provider envelope in evidence. Any second request requires a new approval.

**Maximum requests:** zero now; one generation if P6 later passes. Zero model-list, countTokens, streaming follow-ups, tools/grounding or in-app AI clicks. The app's 1,800-output-token action is excluded from the 128-token smoke allowance. Transport PASS does not qualify full application prompts or all AI features.

**Potential cost:** unknown while project/model/tier are unidentified. Default approval ceiling is **US$0.00**: execute only when the owner verifies a no-charge allocation and controls preventing paid spillover. A remaining-quota display or budget alert is not sufficient. If paid testing is wanted, P6 must be replaced/amended with an exact numeric dollar ceiling, current model-specific input/output/thinking pricing, a conservative one-request cost calculation and verifiable enforcement. No paid amount is preauthorized by this plan; no unsupported price estimate is presented as a guarantee.

**Side effects:** external prompt transfer, Google quota use, provider logs and possible charge absent verified protection. They cannot be rolled back. No Supabase writes, user-facing message history or saved itinerary changes.

**Cleanup/stop:** close the one-shot client; keep the attempt consumed and retain application fallback. Stop on invalid entitlement/controls, 400/401/403/404/429/5xx, refusal, truncation, invalid schema/JSON, network failure or deadline. A canceled request may already have run or incurred usage; never retry or revoke the key as implicit cleanup.

## 5. Individual approval record

All boxes begin unchecked. Approval must be explicit for each selected ID and the privately completed identity/project mapping. Permission for a test does not include its optional variants or cleanup writes.

- [ ] **P0 — Target/settings/controls:** named isolated Supabase project, A/B/C mappings and ownership; read-only hosted configuration/hook review; local-only target configuration permission; named protected reads/RPCs; approved time window and operator; loopback execution controls ready. No hosted changes or provisioning.
- [ ] **P1 — T1 sign-ins:** A once and B once; provider session/log/validation/possible refresh effects and protected reads. Reserve the shared ledger; no role grants.
- [ ] **P2 — T2 independence:** continue immediately from T1; B once more; Admin/User local logout checks and protected reads. No reverse-order live replay.
- [ ] **P3 — T3 signup/verify:** C creation plus exact identified profile/hook effects; one signup email and one valid OTP verification. No C login under the default allocation.
- [ ] **P3R — Optional resend:** one extra C email after app/provider cooldown; no new account or second OTP verification allowance.
- [ ] **P4 — T4 recovery:** one A recovery mail and one PKCE exchange/recovery session. Stop before password submit unless P5 independently passes.
- [ ] **P5 — T5 reset:** one A-only password update, identified invalidation/notification effects, one new-password A login (fourth slot), then local logout. No password restoration.
- [ ] **P6 — T6 Gemini:** exact project/key alias/model, 512-input/128-output-token ceilings, one POST, no additional Google calls, 20-second total deadline, verified quota/entitlement and US$0 hard protection or separately specified/enforced paid ceiling. One-shot sender reviewed and ready.
- [ ] **P7 — Optional later remote cleanup:** separately identify C's exact test-project account/dependent rows or specific test-session revocations and owner execution method. Review cascades/references first. No blanket deletion, global sign-out, schema rollback, key rotation or production cleanup. P7 is not needed to retain clearly identified disposable test artifacts.
- [ ] **Evidence/stop rules:** aggregate/alias evidence only; no raw request tracing/HAR/inbox screenshots; stop on uncertainty; no automatic retry/resend/repair; stop owned local processes and discard disposable local browser state when complete.

Operator ledger before each submission: `test ID | approval reference | alias | target confirmed | allowance before | consumed before send | result category | elapsed time | cleanup disposition`. Never include secrets. Mark results PASS, FAIL, INDETERMINATE or NOT RUN; skipped/unapproved steps are NOT RUN, never PASS. Stop the selected sequence after a failure rather than spending remaining slots on repair.

## 6. Cleanup and GO/NO-GO matrix

Local cleanup is reversible and limited to owned browser/process state: use still-valid rendered local logout forms under the approved sequence, close the disposable profile and stop the single Flask process. Stopping Flask discards all process-local auth/recovery/email state, so do it only when no approved continuation remains. Do not terminate unrelated processes or use a personal browser profile.

Remote side effects are not a database transaction that can be rolled back: delivered emails/logs/usage remain; password changes need a new change to undo; deleting an Auth user can cascade into profiles/memberships and other deployed dependencies. Prefer retaining named disposable artifacts. Any remote cleanup must pass P7 with precise IDs privately verified in the test project; never run migrations or broad SQL deletion as test cleanup.

| Live test | Current recommendation | Conditional GO requirements |
| --- | --- | --- |
| T1 existing A/B sign-in | **NO-GO now** | P0/P1; confirmed existing dedicated identities and synthetic protected-read scope; execution controls ready. |
| T2 session independence | **NO-GO now** | T1 PASS plus P2 granted before its uninterrupted shared sequence; one B submission remains. |
| T3 signup/verification | **NO-GO now** | P0/P3, unused C mailbox, deployed hook/SMTP/template review; P3R only if resend chosen. |
| T4 recovery through reset form | **NO-GO now** | P0/P4; owned A mailbox, redirect/PKCE review and same-browser state. Does not authorize password update. |
| T5 reset completion | **NO-GO now** | T4 PASS, valid grant, P5, disposable A and reserved fourth login; all notifications identified/approved. |
| T6 Gemini smoke | **NO-GO now** | Separate P6, entitled model, verified input budget and enforceable cost controls; reviewed one-shot sender. Supabase approval irrelevant. |

**GO for reviewing this plan and existing isolated evidence. NO-GO for executing any live test under the current planning-only authorization.** Complete localhost integration acceptance still requires successful authorized tests; T6 alone cannot qualify the full in-app AI path. Existing hardening gaps (recovery-mail CSRF/origin/throttle, hard-coded callbacks, process-local state and Gemini total deadline/token configuration) remain documented in Stage 1 and unchanged.

Only this plan was added. No regression suite or Stage 1 provider reader was rerun, no environment/account data was queried, and no runtime/configuration/test/migration/prior evidence file was changed. No deployment, staging, commit or push. **Stop here and wait for separate, test-specific authorization before any live operation.**
