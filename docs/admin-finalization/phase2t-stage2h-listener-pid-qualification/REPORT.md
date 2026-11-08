# Phase 2T Stage 2H — Native Listener PID Evidence Qualification

Investigated **2026-11-06, Asia/Manila**. Reference: [Stage 2G findings](../phase2t-stage2g-helper-correction/REPORT.md).

**Native listener qualification did not pass in the current execution context. NO-GO for repeating the full RosaGo anonymous preflight here until a trustworthy host observation shows the actual target-port listener.** The test-tooling correction and **80 synthetic/regression tests pass**. They correctly reject the observed missing-listener condition; they do not establish an actual serving PID by substituting a connected socket, another port or a parent process.

No real RosaGo application, browser/client preflight or authentication session was started. All real network activity was confined to owned .NET loopback fixtures and empty TCP connections; no HTTP/application payload was exchanged.

## 1. Root cause and confidence

Stage 2G identified the helper's unchecked nonzero/empty PowerShell output and subsequent JSON parsing failure. That defect was separate from **why native discovery had no listener object to return**.

This stage narrowed the latter failure:

- A synthetic .NET `TcpListener` binds loopback, reports `IsBound=true`, accepts an empty connection and reports socket `AcceptConnection=1`.
- `Get-NetTCPConnection -State Listen -LocalPort <target>` nevertheless returns no matching listener and raises `CimJobException`.
- Removing the state filter can expose the correct PID on an **Established** record, and sometimes an empty/unrecognized state, at the target port.
- `netstat -ano` returns successfully and exposes an **ESTABLISHED** row with the fixture PID, but **no LISTENING row at that target port**. Enumerating both address families did not resolve the gap. .NET's independent `GetActiveTcpListeners()` also found no target-port listener.

**Proven proximal cause:** native observation does not expose the expected **listening-state** record at the logical bound port. It is not simply a missing PID, malformed JSON, wrong Python working directory, unlaunched PowerShell or netstat parser failure. A query restricted to Listen legitimately has no qualifying row in these observations, and its error was previously obscured by the helper.

**Underlying platform cause remains unproven.** The records show disagreement between socket-level listening behavior and native table visibility. They do not identify a specific proxy, network compartment, security product or Windows defect. No network/security configuration was altered to force a match.

This result was reproduced in a **single PowerShell process with no Python/Flask application or development reloader**. Flask parent/child confusion therefore cannot explain the isolated failure. It remains important for future application PID validation, but is not a justified explanation for these fixtures.

## 2. Isolated Windows observations

| Recorded fixture | Expected PID | Target port | Observations | `Listen`/`LISTENING` at target |
| --- | --- | --- | --- | --- |
| [Native probe](native-probe.json) | 34908 | 54175 | Three bounded comparisons | None from either tool |
| [Detailed probe](native-probe-detailed.json) | 20784 | 53392 | Three comparisons, both families, socket flags and .NET enumeration | None from either tool |
| [Exact-port probe](native-port5000.json) | 16160 | **5000** | Three comparisons, including unfiltered native states | None from either tool |

All recorded fixtures accepted one controlled empty TCP connection, reported the correct PID on established-connection evidence, and were closed in `finally`. Two-second waits between observations did not resolve the missing listener. `netstat` exit status was 0 and its output contained valid TCP rows without embedded-NUL decoding corruption.

The port-5000 probe also observed a LISTENING row at **another port** belonging to the same PID in one sample. That is explicitly **not** proof of a listener at 5000 and was not adopted as a port mapping. Likewise, an established accepted socket proves a connection was handled, not independent native ownership of the listening socket.

An initial trial could not save its JSON because the phase directory did not yet exist; it was not treated as durable evidence. The three recorded probes above were run after directory creation. All owned fixtures, including the initial trial, closed; no existing app/process was terminated or modified. See [qualification-summary.json](qualification-summary.json).

## 3. Listener discovery and PID validation method

The corrected test-tool method uses two independently obtained Windows views and validates explicit process roles:

1. **`Get-NetTCPConnection`:** collect target-port rows with their state, rather than discarding all non-Listen diagnostics at the query boundary. A native query failure is recorded as failure, not parsed as empty success.
2. **`netstat -ano`:** require successful execution, parse numeric TCP endpoints and PID columns exactly, and classify state. Only the requested port is retained; full connection inventories and remote endpoints are excluded from durable proof.
3. Normalize Windows PowerShell `Listen`, numeric Listen enum 2 and netstat `LISTENING`; treat Established, TIME_WAIT, unknown/blank states and other states as **not listener evidence**. Match port 5000 exactly, never a substring such as 50000.
4. Require both successful sources to show one positive owner for **127.0.0.1:5000**, matching the expected serving PID. Missing rows, PID 0, multiple owners, disagreeing sources, wildcard exposure or alternate-family binding fail the current IPv4-only profile. A different bind profile would need separate reviewed configuration.
5. Require that serving PID equals both the **Flask actor PID** and **verifier snapshot PID**, with explicit `reloader=false`. No PID is inferred from the last launched shell, process name, parentage or an established connection.

### Parent/child and reloader handling

A development reloader can make a launcher/monitor PID different from the serving child. Selecting the parent merely because it started Flask is unsafe; accepting any child is also unsafe because the wrapper and in-memory state may not exist in that child.

The approved capstone verifier uses one process and `make_server`, with debug/reloader disabled. Its new ready manifest explicitly includes `flask_pid` and `reloader=false`. A benign external launcher/venv parent may exist, but its PID is not the listener identity. If an actual reloader is active, metadata is missing, or native/Flask/verifier PIDs differ, qualification stops. This stage did not activate a reloader or modify application startup behavior.

For a future real run, the actual identity endpoint and durable request sequence must still match that serving PID/run after native qualification. Native rows alone do not prove that a particular Flask route or wrapper handled a browser request. No such real-app comparison is claimed here because a full RosaGo preflight is excluded by this stage's scope.

## 4. Exact test-tooling changes

New Stage 2H tooling:

- [listener_evidence.py](listener_evidence.py): pure PowerShell/netstat parsing, listener-state/PID consensus and process-role validation.
- [capture_native.ps1](capture_native.ps1): captures target-port observations and exit classifications, without Python launching a nested PowerShell. It marks qualification pending before capture.
- [qualify_native.py](qualify_native.py): normalizes a run-local native input into a strict `Get-NetTCPConnection+netstat` proof, replaces stale success on failure, and removes the exact transient raw-row input. Pending/failed qualification remains marked until successful durable publication.
- [probe_native.ps1](probe_native.ps1), tests/runner and sanitized observations/results: isolated qualification only, no actual app or provider integration.

Existing **test tooling only** changed:

- [Stage 2G helper](../phase2t-stage2g-helper-correction/independent_client.py) now requires the dual-source proof, rejects pending/failed qualification, and requires explicit serving-Flask PID/reloader metadata **before HTTP client construction**. The old one-source proof is intentionally no longer sufficient.
- [Stage 2G helper tests](../phase2t-stage2g-helper-correction/test_helper.py) use the stricter schema; zero-owner rows are now rejected even alongside a positive owner.
- Stage 2E's anonymous launcher, Stage 2F's checkpoint launcher and Stage 2G's synthetic fixture ready writers now add `flask_pid` and `reloader=false`. No runtime auth behavior, credentials, routing, session backend or startup safeguard changed. Their previous JSON evidence was not rewritten.

The legacy Stage 2G single-source `capture_listener.ps1` is superseded for future qualification by the Stage 2H capture/normalization commands. Its old output is rejected by the corrected client; it is not a fallback.

## 5. Synthetic regression results

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe docs/admin-finalization/phase2t-stage2h-listener-pid-qualification/qualify_offline.py
```

[synthetic-results.json](synthetic-results.json): **80 passed; zero failures/errors/skips; zero network/subprocess attempts in the synthetic suite**:

- **22 new tests:** exact states/ports, PowerShell object/numeric forms, netstat parsing/encoding, missing or conflicting sources, PID 0/multiple owners, wrong address family/wildcard, launcher/serving PID distinction, reloader metadata, actual negative-loopback observations, stale-success/pending markers, redaction and proof normalization.
- **21 updated helper tests** for pre-HTTP failure handling, fresh proof, loopback-only requests, identity/HEAD/journal correlation and privacy.
- **37 existing Stage 2B/2C/2D boundary/capture regressions**.

Successful PID proof in [sample-evidence/listener-proof.json](sample-evidence/listener-proof.json) is **synthetic** (fixture PID 4321), demonstrating schema/logic only. It is not an observed Windows owner and must never be copied into a live preflight. The actual loopback observations are separately asserted to **fail** qualification; passing those rejection tests does not mean native ownership qualified.

The suite blocks socket/DNS/send and subprocess calls. Existing saved Stage 2D sample output is preserved. Seventy-five runtime/Stage 2B/Stage 2F files matched their before/after fingerprints during tests; intentionally changed launcher source metadata is listed above. All seven Stage 2B artifact fingerprints still match the Stage 2C baseline; its consumed allowance and stop marker remain unchanged.

## 6. Redaction and evidence safety

No passwords, cookies, access/refresh tokens, Authorization headers, API secrets, browser stores or actual configuration credentials were read. Native discovery inspects socket metadata only. Probes persist their own loopback/wildcard rows, process IDs, counters, flags and fixed error classes; full `netstat` output is not saved.

The normalized proof contains fixed source/exit metadata, timestamp, run/origin, explicit PID roles, reloader flag and canonical local listener rows. Remote endpoints, unknown state strings, raw native rows and arbitrary error text do not survive normalization. Canary tests inject private strings into synthetic output and verify they are absent from proof/failure results. Transient inputs are removed and stale success is replaced with failed proof plus a pending/failed marker.

PowerShell and Python collector syntax was checked. No actual native collector was run against a live RosaGo application. Raw captures used in the isolated probes contain only owned test-socket metadata; no HTTP/application data was sent. All fixtures were closed, and no browser was started.

## 7. Future invocation and success conditions

These commands describe a **future separately authorized anonymous run**, not execution performed in Stage 2H:

```powershell
& '.\docs\admin-finalization\phase2t-stage2h-listener-pid-qualification\capture_native.ps1' `
  -RunDirectory '.\docs\admin-finalization\<fresh-run-directory>'

.\.venv\Scripts\python.exe docs/admin-finalization/phase2t-stage2h-listener-pid-qualification/qualify_native.py `
  --run-dir '.\docs\admin-finalization\<fresh-run-directory>'

.\.venv\Scripts\python.exe docs/admin-finalization/phase2t-stage2g-helper-correction/independent_client.py `
  --run-dir '.\docs\admin-finalization\<fresh-run-directory>'
```

Stop after any failed command/qualification; do not proceed sequentially regardless of exit code. For success:

1. A current trusted host view must actually expose **LISTENING/Listen at 127.0.0.1:5000** from both tools, with one positive owner and no ambiguous zero/wrong owner.
2. That owner must match current Flask and wrapper PIDs; reloader must be explicitly disabled. Old ready files without the role metadata fail closed.
3. Ready/snapshot/run identity must be active, unarmed and unspent. Native proof must match the run/origin and be at most 60 seconds old. Pending/failure markers prohibit use of stale proof.
4. Only after that native qualification may the anonymous helper make its fixed identity GET/login HEAD and require matching headers, body PID/state and persisted sequence.
5. A future full anonymous phase must then prove the actual owner's fresh browser/profile path and redaction, while remaining unarmed. A live User submission still requires a separate subsequent authorization; Stage 2B cannot be reused.

Do not weaken the Listen requirement, accept PID 0 or an arbitrary parent/child, use the same PID's listener on another port, synthesize a mapping, forge native output, edit proof timestamps or enable a reloader as a workaround.

## 8. Limitations and recommendation

**GO for the corrected dual-source parser/qualification logic and its isolated regression coverage. NO-GO for repeating the full RosaGo anonymous preflight in the currently unqualified observation context.** First establish a trusted host-side observation path that exposes the actual target-port listener consistently. The present socket/table disagreement is not solved by parsing fixes or reloader assumptions, and its underlying platform cause is not proven.

The stricter tooling reliably rejects missing/ambiguous evidence; it cannot manufacture independent OS evidence. A later successful native observation will still need a fresh anonymous client/browser preflight. Stage 2E's historical result does not qualify a new run, and Stage 2B's outcome remains indeterminate/consumed.

No real RosaGo preflight, User/Admin login, Supabase Auth request, production database/Auth/Storage modification, email/Gemini request, experimental-session activation, safeguard change, deployment, staging, commit or push occurred. **Qualification finished with the native-evidence gate closed; stopped pending approval.**
