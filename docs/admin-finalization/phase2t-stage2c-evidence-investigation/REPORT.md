# Phase 2T Stage 2C — Login Evidence Mismatch Investigation

Investigated **2026-11-06, Asia/Manila**. Reference: [Stage 2B report](../phase2t-stage2b-user-login/REPORT.md).

**The proven failure is an unverified browser/client-to-verifier execution path. Requests bypassing the wrapper reproduce the observed evidence exactly. The specific historical process, routing or browser cause cannot be established from the retained records.** Stage 2B remains indeterminate, not a failed-login finding. Its one owner-confirmed submission remains consumed.

**10 synthetic tests passed; zero network attempts.** No live application was started, no real configuration/browser profile was read, no credentials were accessed, and no User/Admin/provider request was sent during this investigation. No Stage 2B authorization was reused.

## 1. Root cause and confidence

The verifier never established that the browser and tool HTTP requests were reaching its wrapped WSGI application before inviting credential entry. It accepted a process-local READY message, a socket-listener observation and an anonymous `/login` HTTP 200 as readiness. Those checks do not identify the responding application instance or prove the browser cookie jar is attached to it.

The implementation gives two strong diagnostic invariants:

1. A `GET /__phase2b/status` reaching the wrapper returns JSON **200**, even after the wrapper stops application activity. That control route precedes the stop/allowlist branches. It does not depend on Flask routes, cookies, authentication or the browser's session realm.
2. An admitted `HEAD /login` reaching the wrapped app calls `Boundary.observe('/login', status)` at WSGI `start_response` and saves a route event. A successful captured HEAD 200 cannot leave the route map empty under normal persistence.

Stage 2B instead observed a login-page HEAD **200**, control-route GET **404**, and an empty route map, including at the owned server's final save. The synthetic bypass test reproduces all three by sending requests to the underlying app **without the wrapper**. The normal wrapped test captures HEAD and returns control 200. This establishes a sufficient explanation and an actionable readiness defect; it does **not** prove which real process or network path handled the owner's submission.

The Stage 2B report correctly stopped instead of retrying. My earlier execution should have verified the unique control endpoint and a recorded anonymous browser request before asking the owner to sign in. That missing preflight is the confirmed procedural cause of permitting an unobservable attempt.

### Alternative explanations

| Candidate | What the evidence/tests establish |
| --- | --- |
| Direct/unwrapped app, another process, port mapping or different local execution context | Consistent with the observations; direct-app bypass reproduces them. No saved response PID/run ID or historical routing evidence identifies the actual cause. Do not assert a particular proxy or second Flask process existed. |
| Wrong browser profile, host or cookie jar | Profile use was requested, not proven. Separate synthetic cookie jars lose authentication but still generate wrapper route evidence. Cookie differences alone do not explain control GET 404 or an unrecorded wrapped HEAD. |
| Redirect/navigation behavior | A synthetic POST 303 followed by homepage 200 is captured. Relative form action `/login` and native browser POST are correct in source; no direct browser-to-Supabase login is implemented. A redirect cannot erase already-saved attempt/route evidence. An old tab, cached page or other origin remains historically possible. |
| Verifier started too late | The saved startup and READY/listener observations preceded the owner's confirmation, but the actual click time and browser server identity were not recorded. Late startup is not established. It does not explain a control-route 404 from the intended running wrapper. |
| Rejected Origin or early policy response | Original wrapper can return 403 before `observe`, leaving route/attempt counters empty. This blind spot is reproduced. It cannot itself explain control GET 404 or a successful wrapped login-page HEAD with no route event. |
| Control tab missing/failed/closed | Possible; launch and polling success were not verified. The script catches polling failures only in browser text. Control requests themselves are not entered in the old route map. Absence of control counters therefore proves nothing about whether the tab ran. |
| Stale/overwritten result file or wrong output artifact | Not conclusively excluded: no per-run ID, request timestamps, immutable startup fingerprint or event journal. The close flag proves a final writer ran, not that every client used that process. The synthetic tests validate normal capture, not historical filesystem/network behavior. |
| Wrong User/Admin realm | No live session realm was observed. The User route uses the normal User store; Admin boundaries are separate. Realm/cookie checks occur after ingress and cannot independently turn the verifier's control endpoint into 404. |

## 2. Trusted evidence and timeline

Reviewed only known verifier source, sanitized JSON/report files, login route/browser-script source and session-selection code. **Browser History, Cookies, Login Data, DevTools traces, request bodies, environment secrets and provider account/session logs were deliberately not opened.** No credential recovery or reconstruction was attempted.

[evidence-review.json](evidence-review.json) records sizes, current SHA-256 fingerprints and UTC/Manila modification times of seven known Stage 2B files. These fingerprints preserve the investigation baseline; none was available to identify the running source version during the original attempt.

| Time, Asia/Manila | Existing evidence | Limit |
| --- | --- | --- |
| 12:07:50.257626 | Saved `started_utc=2026-11-06T04:07:50.257626+00:00`; development startup metadata | Timestamp is saved before `make_server` binds; it is not a browser/request timestamp. |
| After startup; no saved request time | Transcript records READY and a 127.0.0.1:5000 listener, PID 22736 | PID was not included in durable verifier results or matched to the response/browser. |
| Before mismatch; no saved request time | Tool reports HEAD `/login` 200; owner reports one Log In click and later homepage/User-page navigation | HEAD is anonymous and not proof of authentication. Owner observations are trusted as reports, not independently measured HTTP/session results. |
| 12:10:43, approximately by file metadata | Stop and owner-attempt-consumed artifacts created; control GET 404 recorded in the report/transcript and attempt ledger | No exact click, HEAD or control-request timestamps; filesystem modification time is not request-time evidence. |
| 12:10:44, approximately by file metadata | `live-results.json` final modification; `server_closed=true`, all wrapper route/attempt/provider counters zero | Proves what that saved wrapper observed, not whether another execution path created an Auth session. `stopped=false` and `awaiting_owner_submission` remained stale because the external stop marker only exits the loop. |
| 12:12:34–35, approximately by file metadata | Owner visible outcome added; final report updated | Documentation update times do not establish when login/provider processing occurred. |

The current Stage 2B source includes the post-stop consumed-marker restart guard, with a modification time after startup. There is no startup source hash; do not present today's file fingerprint as proof of the exact initial executable bytes. The WSGI functions tested here are the preserved current implementation.

Reliable conclusions: the owner reported **one submission** and **homepage or User-page loading**; the controlled process reported approved development stores/no shared extension; its final recorded request counters were zero; control endpoint probing returned 404; an owned close was recorded. No durable access log, control poll history, browser-profile acknowledgement, matched response/run identifier, provider-session acceptance or authenticated page result exists.

## 3. Synthetic reproduction and results

Run from the workspace root:

```powershell
.\.venv\Scripts\python.exe docs/admin-finalization/phase2t-stage2c-evidence-investigation/reproduce_capture.py
```

The script imports Stage 2B class definitions **without invoking `main`**, extracts its original nested WSGI functions through Python AST, and runs them in-process against a small synthetic Flask app. It never imports RosaGo `app.py`, loads `.env`, binds a socket, starts a browser or contacts a provider. Synthetic POSTs change only fixture session state; there is no Supabase account/password authentication.

| Test | Result |
| --- | --- |
| Original wrapped HEAD `/login` and control endpoint | HEAD 200 saved; control JSON 200. |
| Bypass wrapper and address underlying synthetic app | HEAD 200, control 404, wrapper counters empty: observed mismatch reproduced. |
| Original synthetic POST and redirect chain | One local fixture submission, 303 and subsequent homepage 200 captured. |
| Separate synthetic browser cookie jars | Protected access changes from 200 to 302, but both requests remain captured. |
| Wrong-Origin early rejection | 403, zero admitted login and zero old route events; demonstrates ingress blind spot. |
| Original control-page/status requests | Both served, neither recorded by old observer. |
| Original capture secret-canary test | Synthetic password, cookie, Authorization/access/refresh query values absent from state and saved-state serializations. |
| Corrected prototype identity/header/ingress test | Identity and login HEAD share public run ID; sequence/status events include control, HEAD and rejected POST. All mutations disarmed. |
| Corrected prototype body/header/query privacy test | A body stream that raises if read is never accessed; private canaries absent; unknown path normalized to `other`. |
| Corrected exception test | Fixed outcome recorded, exception message excluded. |

[synthetic-results.json](synthetic-results.json): **10 passed; zero failures/errors/skips; zero blocked-network attempts**. Network sends/connections/DNS are denied during tests. Stage 2B artifacts and five selected runtime files matched their initial fingerprints (**12 preserved files**). Raw test output and fixture credentials/cookies are not archived.

Stage 2B's five original policy tests exercised `Boundary` methods directly, not the full WSGI/client route. They correctly checked counters/classification but could not detect an unwrapped listener, wrong process or missing control-tab preflight. This investigation adds that missing in-process coverage. It does not prove real browser/TCP forwarding, which remains a future release gate.

## 4. Privacy assessment

The original observer saves fixed state/counters and admitted path/status pairs; it does not inspect incoming password form fields, Cookie/Authorization headers, access/refresh token bodies or provider response bodies. `classify` inspects only the URL host/path/method and the nonsecret grant type. Original normal request logging is disabled. A self-declared `credentials_or_tokens_recorded=false` flag alone was not evidence; the new canary tests independently exercise the observed serialization path.

The [capture prototype](capture_prototype.py) uses an explicit field allowlist: public run ID, PID, sequence, timestamp, normalized method/path, route-realm label, status and fixed outcome. It does not read request streams, query strings or headers, and does not persist response headers/cookies or exception text. It adds public run/sequence headers to responses. The route-realm label is routing metadata, **not proof of authenticated identity**.

These tests establish privacy for the exercised wrapper/prototype paths. They cannot attest to the unobserved Stage 2B application instance, operating-system/browser internals, external logs or arbitrary future changes. Do not inspect real browser artifacts to fill that gap. Any future capture must retain this allowlist and suppress framework/raw exception/request logs too.

## 5. Smallest recommended capture correction

Keep RosaGo's login, cookies, credential stores and startup safeguard unchanged. Correct the verifier and its release process:

1. Generate a **public per-run identifier**, record PID and source/configuration classifications, then emit READY **after binding**. Include the identifier and sequence in every controlled response and a small no-store identity endpoint. Use per-run output files so another launch cannot overwrite an unrelated run's observations.
2. Observe ingress at the outer WSGI boundary **before** control/Origin/allowlist/stop branches. Record only normalized method/path, UTC time, sequence and fixed result/status; capture early rejections and control polling. Add a fixed close reason/time rather than leaving `awaiting_owner_submission` after shutdown.
3. Fail closed until an **anonymous end-to-end preflight succeeds from the actual owner browser and the independent verification client**. A login-page 200, READY message or port number alone must never enable credential entry.
4. Preserve the consumed-before-dispatch one-attempt ledger and **all Stage 2B stop/consumption markers**. A fresh approved retest gets its own run and explicit new authorization; a zero wrapper count does not restore the previous allowance.

`capture_prototype.py` demonstrates the first part of this correction and earlier ingress capture offline. It is deliberately **not a live login verifier**: no listener, real app/config import, provider transport, arming method or authorized POST path. Its events are in memory; future integration must add a sanitized durable journal/atomic snapshot and startup/close metadata, with tests for persistence failure. A persistence failure must prevent arming or dispatch. Do not expose the existing credential form before that gate; the future wrapper should show a disarmed preflight page instead.

This is smaller than changing the authentication architecture and directly addresses the failed evidence path. No existing application, Stage 2B evidence or enforcement code was modified in this investigation.

## 6. Mandatory preflight before any newly authorized login

This procedure is proposed only; no live/localhost network check was performed in Stage 2C.

1. **New scope:** obtain a new single-attempt User authorization; confirm the isolated target and private owner-entered unchanged credential. Stage 2B remains consumed. Do not request passwords/tokens. Admin login remains separate.
2. **Local instance:** inspect current listener/PID and start the reviewed verifier only on the approved exact loopback origin, one process, no reloader. If another listener exists, do not attach blindly or terminate it. Save verifier PID, bind address, run ID, source hash, start-after-bind UTC and approved development/store classifications; refuse experimental/shared adapters or safeguard bypass.
3. **Independent client, anonymous:** GET the identity endpoint; require 200, correct content type, expected run ID/PID/armed=false, no-store and matching response run header. HEAD `/login`; require the same run header and a matching HEAD event in that exact run's durable journal. A 404, missing header, wrong PID/run or absent event aborts **before credentials are entered**.
4. **Owner's dedicated browser, anonymous:** launch the disposable private profile to the verifier's disarmed preflight page, not an old login tab. The browser page fetches identity and records a fixed successful handshake in the same run journal. Require the displayed public run code to match the verifier/client. Navigate to login from that page and require a browser-originated anonymous login GET event in that run. No screenshots, HAR, cookie values or DOM credential inspection.
5. **Profile/origin continuity:** verify an anonymous HttpOnly preflight-marker round trip with a boolean result only, never logging the Cookie header/value. Both control and login pages must use the same exact origin/profile; do not rely on a global run ID alone to prove the same cookie jar. This marker/handshake integration is not implemented by the minimal prototype and needs its own offline tests before release. In the synthetic fake app, separate jars demonstrably lose session authority while requests remain visible.
6. **Gate readiness:** no-store login responses, visible disarmed state, known matching run/PID/events, fresh User challenge and confirmed durable attempt budget. An operator-only gate may enable **one** submission only after all checks pass and the owner explicitly initiates it; it must not be possible to arm via an unrelated browser GET or a public run ID. Keep the provider/action denylist and privacy protections from Stage 2B.
7. **After that single submission:** immediately correlate the ingress POST, provider password-attempt counter, sanitized HTTP result and subsequent protected-page/status checks under the same run. Do not copy a provider token or cookie for verification. Any missing event, 404 control endpoint, identity mismatch, persistence failure or auth/provider error consumes/stops the attempt; no retry, arming reset or login through a second process.
8. **Ending:** save terminal classification and close time, stop owned processes as authorized, and distinguish local session disposal from provider revocation. No automatic sign-out, account/password cleanup or data rollback.

Anonymous handshake success establishes current end-to-end routing; it cannot retroactively establish what happened in Stage 2B. Browser cookie-marker checks establish anonymous continuity only; authenticated session validity still needs the newly authorized protected requests.

## 7. Remaining Stage 2B gaps and recommendation

Still unknown: which process/origin/profile received the owner's password submission; its actual timestamp/HTTP status; whether Supabase accepted it or created/updated session metadata; whether a valid authenticated User dashboard loaded rather than a public/cached page; session continuity; User-only denial at Admin routes; any unobserved hooks/provider effects. No provider session was queried, revoked or assumed absent.

**GO for the offline capture correction and reviewing these ten passing synthetic tests. NO-GO for an immediate live retest or Admin login.** A separately authorized User retest can be conditionally GO only after the corrected integrated verifier, durable ingress journal and anonymous client/browser/profile preflight are implemented and pass. The prototype alone is insufficient to release another live attempt.

Only new Stage 2C files were added: this report, capture-only prototype, synthetic investigation runner/results and sanitized artifact review. Stage 2B's consumed ledger/stop marker and existing runtime files remain unchanged. No real credential/configuration/browser-profile access, live authentication, account/password/email operation, SQL/data/Storage write, Gemini request, experimental adapter activation, startup-safeguard change, deployment, staging, commit or push occurred. **Investigation complete; stop pending approval for further work.**
