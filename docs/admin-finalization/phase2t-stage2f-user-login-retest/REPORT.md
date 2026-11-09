# Phase 2T Stage 2F — Controlled Live User Login Retest

Prepared and anonymously probed **2026-11-06, Asia/Manila**. References: [Stage 2D collector](../phase2t-stage2d-verifier-correction/REPORT.md), [Stage 2E preflight](../phase2t-stage2e-anonymous-preflight/REPORT.md).

**NO-GO: the fresh preflight failed before the approval checkpoint. Execution stopped immediately; no retry or live authorization request was made.** No browser was opened, no login was submitted, and the owned verifier is closed. The earlier Stage 2E PASS was not treated as a substitute for this fresh run.

## 1. Authorization boundary

The current instruction authorizes preparation and anonymous preflight only. Exactly one live User submission would require a **later explicit confirmation after the fresh preflight passes**. No such confirmation was requested or received in this stage.

The Stage 2B attempt remains consumed. Its ledger, stop marker and prior evidence were not changed. No credentials were requested, entered, inspected, copied or recorded.

## 2. Preparation and controls

New [checkpoint_server.py](checkpoint_server.py) assembles the corrected collector over the preserved restricted WSGI wrapper and the unchanged actual Flask application. It prepares a fresh visible-browser bootstrap that uses only anonymous GETs and keeps the credential form hidden until a later operator-only approval. That bootstrap was checked synthetically but **not opened in a real browser** because the independent-client step failed first.

The server starts disarmed. Provider traffic is blocked until a later fresh explicit authorization; no authorization file is created by preparation. A later command would have to match the active run, explicitly confirm fresh owner permission and allow exactly one submission, after both external-client and browser checks pass. Nothing in anonymous readiness, a GET, or a public run ID arms login. No arming method was called here, and no allowance was reserved.

Offline checks in [offline-checks.json](offline-checks.json) passed:

- Anonymous bootstrap can be served through the collector.
- Disarmed `/login` hides the credential form.
- A **synthetic in-process** premature POST is rejected before the inner handler; no real application/configuration or provider was involved in that check.

No live POST, empty credential submission or Supabase authentication request was used to test the boundary.

## 3. Actual anonymous preflight outcome

The native host listener query found port 5000 free before launch. The verifier was started in the host context established by Stage 2E. No existing process needed to be stopped or replaced.

| Check | Result |
| --- | --- |
| Bind/origin | `127.0.0.1:5000` / `http://127.0.0.1:5000` |
| Run ID | `c339ca2542a243f7bc7b7facdf473a5a` |
| Verifier process | PID **30968** |
| Bound time, Asia/Manila | **13:35:07**, 2026-11-06 |
| Closed time, Asia/Manila | **13:35:28**, 2026-11-06 |
| Actual startup | Development; `RealmSessionInterface`; distinct User/Admin `NormalAuthStore` instances; no shared extension; debug/reloader disabled |
| Same-process anonymous identity GET | 200, matching run; captured |
| Same-process disarmed login HEAD | 200, matching sequence; captured |
| Actual Flask HEAD `/admin/login` | 200 through the restricted wrapper; no body/credential read and no Admin sign-in |
| Independent client/native listener check | **FAILED before any HTTP request** |
| Actual browser/profile | **NOT STARTED**, because the preceding check failed |
| Credential form / arming | Not exposed to an owner browser / never armed |
| Live User login | **NOT AUTHORIZED / NOT RUN** |

The independent helper returned `passed=false`, `requests=[]` and the generic category `identity_listener_or_capture_mismatch`. It did not produce `listener_pid_matches`. Source order shows the failure occurred during subprocess/native-listener enumeration or parsing **before** the HTTP probe. The helper suppresses raw subprocess/exception text, so the exact subprocess/parse error cannot be established from this result.

**This is not evidence that an HTTP identity mismatched or that the User password failed.** It is a failed prerequisite: the independent path/native listener proof was not completed. No actual browser continuity proof exists for this run. The passing self-client checks cannot replace those missing checks.

The server observed the failed proof and closed. A stop marker was also saved. No native-query retry, HTTP retry, replacement browser, manual credential entry or login approval was attempted after the failure.

## 4. Durable evidence and redaction

Evidence:

- [checkpoint-results.json](checkpoint-results.json): stopped/unapproved terminal state, actual startup and self-client results.
- [client-proof.json](client-proof.json): independent preflight failure with no HTTP requests.
- [boundary-results.json](boundary-results.json): zero User submissions and zero provider password requests; only the anonymous Admin-form HEAD response is observed by the inner wrapper.
- [run journal](e/c339ca2542a243f7bc7b7facdf473a5a/events.jsonl) and [snapshot](e/c339ca2542a243f7bc7b7facdf473a5a/snapshot.json): readiness before ingress, three captured GET/HEAD requests, terminal closure, `armed=false`, `spent=false`.
- [evidence-validation.json](evidence-validation.json): schema checks, no auth reservation and Stage 2B preservation.

The journal/snapshot use the established non-sensitive allowlist. There are no password fields, cookie values, access/refresh tokens, Authorization headers, API secrets, raw provider responses or arbitrary exception text in capture evidence. Unknown paths would be normalized rather than saved verbatim. No real browser profile, screenshots, HAR or credential fields were inspected. The application used its ordinary private configuration internally; no configuration secret was exported.

There are **three captured anonymous requests**, all GET/HEAD and all 200. No `operator_armed` or `attempt_consumed` event, approval file or authorization reservation exists. Provider egress attempts, auth submissions and arming calls are all **zero**. All seven Stage 2B file fingerprints still match the Stage 2C preservation record.

## 5. Approval checkpoint

**Not reached.** It would be incorrect to report the verifier/browser ready or ask for live login permission after this failed fresh preflight.

- Verifier: closed, not active.
- Browser: never started; no profile to retain.
- Live User allowance: none granted or spent in Stage 2F.
- Stage 2B allowance: remains consumed, independently of Stage 2F's zero counts.

Any later successful preparation must use a fresh run, complete the independent native listener/client and actual fresh-browser checks, validate the durable evidence, and then report that the **same** browser and verifier remain active before asking for exactly one User submission. No stale READY file or the earlier Stage 2E run can authorize that submission.

## 6. Remaining work and proposed live verification

Before another anonymous preflight, investigate the helper's native subprocess/JSON handling **offline**, preserving only safe diagnostics such as failure stage, return code and exception class. The current generic category is too broad to distinguish enumeration failure from response parsing. Do not save raw stdout/stderr or credentials as a diagnostic shortcut. Stage 2E's independently combined native listener proof suggests a route for correction, but its previous success does not prove this helper invocation worked.

After a corrected, newly successful anonymous preflight, the separately approved live plan remains: owner enters existing dedicated User credentials privately; one rendered-form submission; verify redirect/protected User access and session continuity; check ordinary User authority does not grant Admin access; retain only sanitized results; stop without retry. **Every one of those live steps is NOT RUN and NOT AUTHORIZED by this report.** Admin login, registration, mail/recovery/password actions, business/Storage writes and Gemini calls remain excluded.

## 7. Recommendation and preservation

**NO-GO for a live User retest now.** Fix/qualify the independent anonymous helper and repeat the fresh preflight under an appropriate preparation scope. Request login authorization only after all checks pass and the new verifier/profile remain active.

Only new Stage 2F tooling/evidence/report files were added. Existing authentication code/configuration, corrected collector, session architecture and prior evidence were not modified. No experimental adapter activation, startup-safeguard change, live User/Admin login or refresh, Supabase Auth request, account/email/password operation, production destination/photo/data/Storage/SQL write, Gemini request, deployment, staging, commit or push occurred. **Stopped at the failed preflight, before the approval checkpoint.**
