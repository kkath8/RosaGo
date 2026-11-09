# Phase 2T Stage 2G — Independent-Client Helper Diagnosis and Correction

Investigated and qualified **2026-11-06, Asia/Manila**. Reference: [Stage 2F failure](../phase2t-stage2f-user-login-retest/REPORT.md).

**The helper's unchecked subprocess-output parsing is corrected. All 58 synthetic/regression tests pass. Native listener visibility remains unqualified in the current execution context, so repeating the full anonymous preflight is presently NO-GO until a fresh, independently verified native ownership proof can be obtained.** No real RosaGo application or authentication session was started in this stage.

## 1. Root cause and historical evidence boundary

Stage 2F's outer helper exited **1**, with `passed=false`, no HTTP requests and no `listener_pid_matches` field. The helper successfully started Python, imported HTTPX, read the intended ready file and printed its correct run/PID. Failure therefore occurred before its HTTP block, during native subprocess invocation/output handling. It was not an observed login, cookie, redirect or provider failure.

The relevant exact child invocation was an argument list, not a shell-built string:

```text
powershell -NoProfile -Command
@(Get-NetTCPConnection -State Listen -LocalPort 5000 -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess) | ConvertTo-Json
```

It used `capture_output=True`, `text=True`, `timeout=10`, inherited the workspace working directory/environment, and performed `json.loads(listener.stdout)` **without first checking `returncode` or empty output**. One broad exception handler converted subprocess, decoding, file and HTTP failures into the same misleading `identity_listener_or_capture_mismatch` category.

### Reproduction without authentication

[diagnose_listener.py](diagnose_listener.py) held an owned synthetic listening socket and executed that query. Both sandbox and host-context reproductions returned:

- PowerShell resolves and launches; Python is **3.13.1** from the workspace virtual environment; PowerShell major version **5**.
- Legacy child exit status **1**, empty stdout and nonempty stderr.
- Parsing that empty stdout raises **`JSONDecodeError`**.
- An explicit diagnostic envelope identifies **`Microsoft.PowerShell.Cmdletization.Cim.CimJobException`**, category **`ObjectNotFound`**, error ID **`CmdletizationQuery_NotFound,Get-NetTCPConnection`**, HRESULT **-2146233087**. The diagnostic wrapper exits **2** deliberately after emitting its safe failed envelope.

See [diagnosis-sandbox.json](diagnosis-sandbox.json) and [diagnosis-host.json](diagnosis-host.json). Raw stdout/stderr and exception messages were not saved. The original Stage 2F child exit code/exception text were not retained, so these reproduced values must not be presented as recovered historical bytes. They reproduce the same pre-HTTP failure class and explain the helper's loss of diagnostics.

### Origin assessment

| Candidate | Finding |
| --- | --- |
| Python executable, import or source syntax | Not the reproduced cause: helper/diagnostic start and dependencies load. |
| Working directory or ready-file path | Stage 2F loaded the correct ready run/PID. A path error is not supported by that result; corrected code handles such failures separately. |
| PowerShell missing or command quoting | PowerShell launches with fixed argument-list parameters; the native cmdlet executes and raises a CIM query error. No credential/space-containing user input is interpolated. |
| PowerShell/CIM listener query | Reproduced upstream failure: no matching listener object is reported, even for an owned synthetic listener. |
| Output parsing/error handling | Confirmed tooling defect: nonzero/empty subprocess output was treated as JSON, then the generic catch hid the actual stage/class. |
| Verifier/HTTP integration | Not reached in Stage 2F's independent helper; no HTTP mismatch was established. Synthetic corrected identity/HEAD/journal integration passes. |
| Execution-context/native ownership visibility | Still unresolved. A synthetic control endpoint was reachable with matching run header while native ownership discovery did not qualify. This does not establish a Windows defect, particular proxy/namespace design or historical Stage 2B route. |

A direct read-only `GetExtendedTcpTable` experiment also failed to observe its owned synthetic socket in the current context. It is retained as diagnostic evidence in [native-api-results.json](native-api-results.json), not selected as a fallback. The precise platform visibility cause remains unknown; no ownership requirement was relaxed.

## 2. Exact test-tooling correction

The helper no longer launches PowerShell internally. Native ownership capture and HTTP verification are two explicit steps, matching the independently captured proof approach that worked in Stage 2E:

1. **[capture_listener.ps1](capture_listener.ps1):** run directly in the trusted host PowerShell context, after the new disarmed verifier is ready. It records only the current run/origin, UTC observation time and loopback listener address/port/PID. It checks for the expected sole positive owner. Query failure replaces any prior proof with a failed envelope and returns nonzero; raw error text is not emitted. A separate `listener-query-result.json` retains safe stage/result/exception-class diagnostics when its run directory is writable.
2. **[independent_client.py](independent_client.py):** loads that run-local proof, validates it and the active run snapshot **before constructing an HTTP client**. Missing, malformed, stale, future-dated, failed, wrong-run, wrong-port/host, ambiguous or wrong-PID evidence stops immediately. UTF-8 BOM from Windows PowerShell is supported. A proof must be at most **60 seconds** old and cannot be supplied from outside its run directory.
3. Only after those prerequisites pass, the helper allows exactly **GET `/__verify/identity`** and **HEAD `/login`** at fixed `http://127.0.0.1:5000`, with redirects/environment proxies disabled and a five-second timeout. It checks response run/PID/state/no-store metadata and a matching persisted HEAD event. It never submits credentials, arms a gate, refreshes a session or selects a provider URL.
4. Failures now report a fixed **`failure_stage`** and category/exception class: `ready_file`, `active_snapshot`, `listener_evidence`, `http_identity`, `http_head`, `durable_capture` or `evidence_write`. No arbitrary exception text, response body or subprocess stream is copied into results. The sanitized client result is written through an atomic replacement.

The existing [Stage 2E helper entry point](../phase2t-stage2e-anonymous-preflight/independent_client.py) now delegates to this implementation. Its `HERE` override compatibility is retained for Stage 2F-style callers, but fresh native proof is mandatory. Historical Stage 2F artifacts were not changed or retried.

Additional Stage 2G files are diagnosis scripts/results; [test_helper.py](test_helper.py), [qualify_offline.py](qualify_offline.py), [synthetic-results.json](synthetic-results.json); a closed synthetic loopback fixture and its evidence; this report and transient-work ignore rules. `native_listener.py` is explicitly diagnostic-only and is not imported by the corrected helper. Production auth, app configuration, session adapters, startup refusal and database code remain unchanged.

## 3. Synthetic regression results

Run the isolated suite from the repository root:

```powershell
.\.venv\Scripts\python.exe docs/admin-finalization/phase2t-stage2g-helper-correction/qualify_offline.py
```

**58 passed, zero failures/errors/skips**:

- **21 helper tests:** successful two-request/durable-event protocol; missing ready/proof; empty legacy-style output; failed native envelope; BOM; stale/future/naive time; wrong/ambiguous/PID-zero ownership; wildcard/wrong-port/boolean-PID rejection; armed/closed snapshots; identity/HEAD failures; missing/wrong-run journal; safe CLI exit/persistence; compatibility entry point; proof-path restrictions and secret canaries.
- **22 Stage 2D** corrected-wrapper integration, fail-closed, persistence and redaction regressions.
- **10 Stage 2C** capture/bypass/privacy regressions.
- **5 Stage 2B** boundary-policy regressions.

The suite blocks socket/DNS/send operations and subprocess creation. Positive HTTP paths use MockTransport; requests are asserted to be anonymous GET/HEAD to loopback. **Zero network/subprocess attempts** occurred during this suite. No actual app/configuration or provider was loaded. Stage 2D's saved sample evidence was preserved rather than overwritten by rerunning its tests.

PowerShell producer syntax was parsed without executing a query. An actual owned synthetic loopback control fixture was separately started to investigate native visibility, served an anonymous identity GET with matching run header and then closed. It dispatched **zero application handlers**, never armed or spent an auth allowance, and made no real auth/provider request. The native producer remained failed in that context; this is not counted as an end-to-end native-proof PASS. See [native-capture-results.json](native-capture-results.json), [visibility-probe.json](visibility-probe.json) and [loopback-results.json](loopback-results.json).

## 4. Evidence-redaction and stop behavior

Canary tests inject synthetic password, Cookie, access/refresh token, Authorization/API-key and exception values. Those values are absent from returned/durable helper results. Request options disable environment proxies and redirects; input URL origin is fixed and never taken from unvalidated metadata. Proof failures are tested with a client factory that fails if constructed: no HTTP is attempted, much less an authentication request.

The helper saves only validated run/PID metadata, booleans, fixed request paths/methods/statuses, sequence, proof age and fixed failure stage/category. It does not serialize full ready/proof documents, identity bodies, headers, cookies, queries, provider data or exception messages. Unknown proof fields are rejected. The native producer emits only an exception **class**, not its potentially sensitive message or stderr. No actual password, token, API secret, browser profile, screenshot or HAR was read.

Preservation checks matched **75 Stage 2B/Stage 2F/root-runtime files**. The consumed Stage 2B ledger and Stage 2F stop state remain unchanged. No fresh login authorization was created, reserved or used. No browser was started. The synthetic listener was closed; no owned test process remains intentionally active.

## 5. Corrected invocation and fresh-preflight requirements

These are **future execution instructions, not a new preflight performed here**. Use a newly authorized anonymous run directory, never a closed Stage 2F ready file.

First, in the same trusted host context that can actually enumerate the disarmed verifier's native listener:

```powershell
& '.\docs\admin-finalization\phase2t-stage2g-helper-correction\capture_listener.ps1' `
  -RunDirectory '.\docs\admin-finalization\<fresh-run-directory>'
```

Proceed only if that command exits 0 and publishes a matching current proof. Then, within 60 seconds:

```powershell
.\.venv\Scripts\python.exe docs/admin-finalization/phase2t-stage2g-helper-correction/independent_client.py `
  --run-dir '.\docs\admin-finalization\<fresh-run-directory>' `
  --listener-proof '.\docs\admin-finalization\<fresh-run-directory>\listener-proof.json'
```

The original Stage 2E entry point can also accept those explicit arguments. Changing directories is unnecessary; absolute resolved paths are used. Both commands return nonzero on failure. Do not edit proof timestamps/PIDs, copy an old proof, forge `ok=true`, use a public HTTP response as ownership evidence, remove the native gate or silently fallback to another process/port.

A fresh anonymous preflight still needs: unchanged approved development startup; actual native listener ownership; independent identity/header/journal correlation; actual fresh owner-browser marker continuity; durable redaction checks; and a still-active browser/verifier before requesting any separate one-login permission. Native visibility must be established **before** declaring readiness. No auth permission follows from this corrected helper or a synthetic PASS.

## 6. Remaining limitations and recommendation

**GO for the corrected helper's isolated behavior and error reporting. NO-GO for repeating the complete anonymous browser/client preflight in the currently unqualified native-observation context.** First establish a trustworthy host context/procedure that successfully captures the live verifier's real loopback owner. Once that prerequisite works, a separately authorized anonymous-only run can use the corrected two-step invocation and retain all fail-closed checks.

The native proof is operator-supplied local OS evidence, not a cryptographic attestation; it must come from the actual current native query, not a fixture. Synthetic owner metadata proves protocol handling, not historical/actual OS ownership. PowerShell/CIM and direct API visibility were not made reliable by this correction, and no environment policy/network settings were changed to force them to pass.

Stage 2F's exact child exception/return code remain historically unretained; the reproduced failure is documented separately. Stage 2B remains indeterminate and consumed. No User/Admin authentication, Supabase Auth request, account creation, email/password action, production database/Storage write, Gemini request, experimental-adapter activation, startup-safeguard change, deployment, staging, commit or push occurred. **Correction and isolated testing complete; stopped pending approval.**
