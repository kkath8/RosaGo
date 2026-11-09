# Phase 2T Stage 2D — Verifier Correction and Synthetic Preflight Qualification

Qualified **2026-11-06, Asia/Manila**. Reference: [Stage 2C investigation](../phase2t-stage2c-evidence-investigation/REPORT.md).

**GO for the corrected verifier's synthetic qualification. Conditional GO for a separately authorized User retest only after its actual anonymous client/browser preflight passes. No live login is authorized now.** All **37 tests passed**, with zero network attempts. Stage 2B's consumed authorization and stop/evidence files remain unchanged.

## 1. Files changed and preservation

All changes are new test tooling/evidence in this directory:

| File | Purpose |
| --- | --- |
| [corrected_verifier.py](corrected_verifier.py) | Outer WSGI capture/preflight layer, durable journal/snapshot, browser continuity and operator-only one-attempt gate; server assembly helper. |
| [test_corrected_verifier.py](test_corrected_verifier.py) | 22 synthetic integration, attachment, persistence, authorization and privacy tests. |
| [qualify_offline.py](qualify_offline.py) | Network-blocked qualification runner, including Stage 2B/2C regression tests and preservation checks. |
| [qualification-results.json](qualification-results.json) | Aggregate results; no raw test output or credentials. |
| [sample-evidence/events.jsonl](sample-evidence/events.jsonl), [sample-evidence/snapshot.json](sample-evidence/snapshot.json) | Actual durable output from one successful **synthetic** fixture sequence; public run/process/route metadata only. |
| `.gitignore`, this report | Ignore transient test work/cache and document qualification. |

No production authentication, templates, JavaScript, provider adapter, session store, migration or existing verifier artifact was edited. Preservation checks matched **70 prior artifacts/root runtime files** before and after qualification. Tests remove only their own verified workspace subdirectories; no browser profile or real environment file was read.

## 2. Why the wrapper is necessary

RosaGo's Flask routes authenticate users; they do not own the test's one-attempt ledger, provider-operation budget, control endpoint or evidence journal. Stage 2B's observers existed only inside the WSGI wrapper and process-local HTTP transport guard. A browser or client reaching `app.py` directly, another server or another execution path bypasses those observers even if `/login` returns 200.

The wrapper must therefore be **the application installed on the exact listening server used by the browser**. A working login URL or a running Flask process is insufficient proof. This correction mounts the preflight layer over the existing restricted verifier, which in turn wraps Flask. It does not replace RosaGo's authentication or introduce a session adapter.

Stage 2C reproduced the historical HEAD-200/control-404/empty-counter pattern by bypassing the wrapper. It did not identify the exact historical browser/process cause. This stage corrects that release defect; it does not retroactively turn Stage 2B into an authenticated PASS.

## 3. Capture correction implemented

### Instance identity and durable ingress

- A unique **public diagnostic run ID**, current PID and approved exact origin identify each run. Responses carry run/sequence headers; the no-store identity endpoint exposes non-sensitive readiness metadata. Run IDs are diagnostic labels, not authentication credentials.
- A fresh exclusive per-run directory prevents another launch from overwriting the run's journal. Every request is recorded **before** control, policy, Origin or readiness branches, including rejected requests and control polling.
- JSON-lines events are flushed and fsynced. An atomic snapshot uses write/flush/fsync plus `os.replace`. A journal/snapshot failure stops and disarms execution before further dispatch. The attempt-consumed event is durable before the inner application can process a login form.
- Events contain only normalized method/path, UTC time, sequence, run ID, PID, fixed phase and HTTP status. Unknown paths become `other`; static paths become `static`. Query strings, identities, body fields, cookies and arbitrary error text are excluded.
- Shutdown has an explicit closed timestamp/terminal state. Application, stream and cleanup exceptions produce fixed categories; raw exception messages are not exposed by the wrapper. A quiet request handler prevents access-log URLs/queries and request-handler messages becoming evidence.

### Same server and preflight before credential entry

`assemble_verifier` accepts the existing restricted WSGI application and a server factory. It checks the supplied **non-sensitive startup classifications** against development mode, `RealmSessionInterface`, distinct normal stores, no shared extension and debug off **before binding**. It mounts the corrected wrapper as the server application, then verifies `server.app is verifier` and exact `127.0.0.1:5000` attachment before marking bound/ready. A wrong application/port is rejected and the owned misattached server is closed.

The caller must derive these classifications from the actual approved startup; supplying a dictionary is not independent proof of a live configuration. Existing startup refusal and provider/action guards remain mandatory. The helper does not load actual configuration or start itself automatically.

While disarmed, `/login` returns a preflight message with the public run ID instead of the credential form. The independent client's identity result, PID/run/origin, no-store HEAD `/login` headers and matching durable HEAD response event must pass local attestation. A 404, missing sequence/header, wrong instance or absent event stops qualification.

The owner's browser then visits `/__verify/start`, which issues one anonymous HttpOnly/SameSite=Strict marker. `/__verify/confirm` checks its round trip, and a subsequent anonymous `/login` GET must come from that same marker-bearing jar. Only the first profile receives the marker; another profile cannot acquire the same marker by repeating Start. Only boolean confirmation is recorded. The marker value remains in memory/browser state and is never written to evidence.

### No public arming or allowance reset

Only the local operator method `authorize_once` can arm after complete preflight and an explicitly fresh approval reference. There is no HTTP arming endpoint. Browser GETs and knowledge of the public run code cannot enable login. The same confirmed profile must load the actual form after arming and submit with the exact Origin.

The new gate permits one User POST, over the existing inner verifier's own one-attempt/provider guards. Admin login and other mutations remain denied. Wrong-profile/origin, repeated or premature submission fails closed. Authorization reservations are exclusive and durable across runs sharing the **same evidence root**; restarting cannot reuse the same reserved approval. References identifying the consumed Stage 2B stage are rejected. Human approval remains required: an arbitrary reference string is not permission.

The Stage 2B ledger/stop marker were neither cleared nor modified. No real approval was passed to this method; qualification uses explicitly synthetic fixture references only. If a future approved run is interrupted after reservation, do not delete the reservation or silently restart with a new reference.

## 4. Synthetic preflight and integration results

Command from repository root:

```powershell
.\.venv\Scripts\python.exe docs/admin-finalization/phase2t-stage2d-verifier-correction/qualify_offline.py
```

The runner loads the preserved Stage 2B WSGI functions through the Stage 2C AST harness, layers the correction over them and injects a synthetic Flask app. No RosaGo `app.py` import, `.env` load, real server bind, browser launch or provider client operation occurs. Socket/DNS/send and HTTPX transport operations are blocked during qualification.

| Scenario | Result |
| --- | --- |
| Correct server-factory mounting | Wrapper installed as exact synthetic server application; bound/ready recorded after factory returns; credential form remains disarmed. |
| Wrong WSGI app, port, run, PID, origin or missing event | Rejected; no credential processing. |
| Underlying unwrapped app | Identity endpoint 404; attestation fails closed. |
| Independent client plus owner-profile preflight | Matching run/PID/HEAD response event; marker round trip and anonymous login GET required. |
| Separate profile | Cannot confirm/reacquire first profile's marker or submit an armed login. |
| Browser GETs, incomplete preflight, consumed Stage 2B reference | Cannot arm or dispatch login. |
| Complete synthetic login/redirect sequence | One fixture POST 303, homepage 200, two protected `/user` reads 200, `/admin` and `/admin/account` redirects 302; original boundary reaches its expected success state. |
| Second POST or approval reuse in another run | Blocked; no second inner login dispatch. |
| Ingress journal, atomic snapshot or attempt-event persistence failure | 503/disarmed/stopped; inner form handler not invoked for the failed dispatch. |
| Experimental/production/debug/shared startup classifications | Rejected before server factory is invoked. No adapter activation. |
| Application/stream/cleanup exceptions | Fixed categories recorded; exception text excluded. A failure after response headers may retain the initial HTTP status, so terminal events must also be assessed. |

The sample journal/snapshot are from the in-process successful fixture sequence, not a production application run. The direct middleware fixture has no actual-app startup manifest; separate assembly tests exercise manifest validation and server attachment. Do not treat the sample PID/origin or its synthetic bind as evidence that a real port/browser was tested.

## 5. Evidence-redaction verification

Tests inject clearly synthetic password, access/refresh token, Authorization/API-key, Cookie/query/path and exception canaries. They inspect **all durable fixture files** and assert the canaries and anonymous marker value are absent. A request body that raises if read confirms the gate does not inspect rejected body content. Raw application response headers/cookies are passed through but not serialized. Request-handler tests confirm sensitive query/error strings produce no stdout/stderr.

The marker is the verifier's own anonymous continuity check; the capture layer does not parse or record application auth-cookie values. It does not inspect login form fields or credential inputs. The synthetic app uses only fixture session state and has no Supabase connection. `credentials-not-recorded` is not taken on trust: the serialization/logging paths are exercised by these tests.

This qualification covers test-tool evidence collection. The real application will necessarily process an owner-entered password and keep session credentials in its approved server-memory design during a separately authorized login. Framework/provider logging and browser behavior still need the existing controlled-launch/privacy settings. No real credentials, environment secrets, browser stores, HAR or screenshots were used here.

## 6. Regression results

[qualification-results.json](qualification-results.json): **37 passed; zero failures/errors/skips; zero network attempts**:

- **22** new corrected-verifier integration, attachment, persistence, authorization and privacy tests.
- **10** Stage 2C capture/bypass/privacy regressions.
- **5** Stage 2B one-attempt/provider-boundary policy regressions.

Initial qualification encountered Windows path-length failures in deeply nested synthetic work directories. Short workspace test paths and short hashed reservation filenames resolved them. A test assertion was then corrected to compare new inner-login observations against the existing count when qualifying a second synthetic run. No application behavior or prior evidence was changed to obtain a pass. Subsequent exception/assembly/privacy checks also pass in the final 37-test run.

No broad authentication suite was rerun: runtime authentication did not change, and the targeted regressions exercise the modified capture/qualification behavior. Earlier 99/214-test authentication results remain historical evidence, not fresh live acceptance.

## 7. Required preflight on the next separately authorized run

1. Obtain a **new explicit single-User-attempt approval** and reconfirm the isolated target. Retain the consumed Stage 2B ledger and all existing reservation records. Use a stable, private local evidence root across future runs; do not reset allowance by choosing a new root/reference.
2. Load the actual app only through the approved development startup checks, retaining production refusal and provider/action guards. Assemble the corrected outer wrapper over that restricted application, with one process, no reloader and the quiet request handler. Record actual classifications; no public bind or experimental adapters.
3. After successful bind, independently verify the listener PID and no-store identity response from `http://127.0.0.1:5000`; require its public run/PID to match saved startup. HEAD `/login` must carry that run ID and a sequence matching the durable HEAD event. Do not infer readiness from HTTP 200 alone.
4. In the actual disposable owner browser, use that origin's Start → Confirm → anonymous Login preflight links. Require matching visible run code, successful marker round trip, and corresponding durable browser events. An old tab, wrong profile, 404 or missing event aborts before credential entry.
5. Only then may the operator arm under the fresh approval. The owner loads the real form, enters the unchanged User credential privately and initiates exactly one POST. No credential automation or inspecting form/cookie values. Check the consumed event, inner provider-attempt budget, redirect/protected-read events and terminal state before declaring PASS.
6. Stop on any identity, persistence, authorization or provider discrepancy. No retry, Admin login, account/email/password operation, business/Storage write, Gemini request or automatic sign-out. Close with explicit terminal evidence; cleanup follows the separately approved scope.

These actual TCP/browser/PID checks were **not performed in Stage 2D**, because its authorization is synthetic/offline only. The generic server-assembly helper is available for a future controlled launch; it does not supply a new live sender, actual-app loader or user authorization. Original Stage 2B `main` remains stopped and must not be restarted as a retest.

## 8. Remaining limitations and recommendation

- Historical Stage 2B outcome remains indeterminate. Its specific execution-path cause and possible provider session effects are not recovered by these tests.
- Synthetic factory/address checks prove integration logic, not current OS listener, port mapping or actual browser routing. Those must pass anonymously at execution time before arming.
- Supported scope remains a single process and the original restricted provider/action wrapper. This layer is not a sandbox or a substitute for Supabase RLS, provider budgets, hosted-hook review or startup safeguards. It does not validate real passwords/Admin membership or Gemini entitlement.
- File flush/fsync/atomic replacement and injected failure handling are tested on this workspace. They do not promise power-loss durability across every OS/OneDrive failure. Partial response/stream failure must be classified from terminal journal events, not status alone. Disk/path or journal failures mean stop, never disable evidence collection.
- Public identity and a marker round trip establish current anonymous path/profile continuity; they do not establish authenticated identity or prevent a privileged local operator from bypassing tooling. Approval and stable reservation-root discipline remain necessary.

**GO: corrected test tooling and synthetic preflight qualification. Conditional GO: a fresh, separately authorized User retest using the integrated wrapper only after all actual anonymous preflight checks pass. NO-GO: any live login under this stage's authorization, any reuse of Stage 2B, or a retest that skips the runtime browser/client/PID checks.** Admin testing remains separately gated.

No live User/Admin/Supabase Auth request, account creation, mail/password action, database/Storage/SQL write, Gemini call, experimental-adapter activation, safeguard change, deployment, staging, commit or push occurred. **Testing complete; stop and wait for approval.**
