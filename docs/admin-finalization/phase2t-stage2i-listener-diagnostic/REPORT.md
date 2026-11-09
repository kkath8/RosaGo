# Phase 2T Stage 2I — Windows Listener Diagnostic and Verification Strategy Decision

Diagnosed **2026-11-06, Asia/Manila**. Reference: [Stage 2H qualification](../phase2t-stage2h-listener-pid-qualification/REPORT.md).

**Decision: stop developing the current verifier as the capstone demonstration's default testing path. Preserve its strict fail-closed rules and historical evidence, but replace the demonstration workflow with a separately approved, operator-observed browser procedure if that evidence standard is acceptable.** No further verifier-development phase is recommended: this investigation found an observation-context limitation, not a new demonstrated parser/authentication defect that another verifier layer can fix.

The environment can report native TCP LISTEN records **in general**, but still cannot qualify the owned test listener at its declared port. Its underlying platform cause remains unknown. **NO-GO for further automated preflight using the current native-PID gate here.** Manual testing would be a different, explicitly limited evidence method—not a PASS or bypass of that gate.

## 1. Finite diagnostic performed

Reviewed Stage 2H's parser, failure conditions, three recorded loopback probes and unchanged application entry point. Ran one bounded [diagnose_context.ps1](diagnose_context.ps1) comparison in each of two contexts:

- Normal sandbox execution.
- Authorized host-context execution, using the same script and fixture.

Each created one .NET IPv4 loopback listener on an automatically assigned unused port and sampled it immediately, after a short delay, and after accepting **one empty TCP connection**. Each checked `Get-NetTCPConnection`, `netstat -ano`, socket listening flags and safe process-context metadata. No HTTP/application payload, Flask app, browser, actual preflight or authentication was involved. All fixtures closed in `finally`.

Evidence: [context-sandbox.json](context-sandbox.json), [context-host.json](context-host.json), [diagnostic-summary.json](diagnostic-summary.json). No additional soak tests, adapter changes, listener fallbacks or verifier-development layers were created.

## 2. Findings: permissions, context and visibility

| Observation | Sandbox | Host-context |
| --- | --- | --- |
| Process / managed PID | 8940 / 8940 | 35568 / 35568 |
| Owned test port | 51143 | 51892 |
| PowerShell / architecture | Version 5 / 64-bit | Version 5 / 64-bit |
| Administrator/System token flags | False / False | False / False |
| Effective execution policy | RemoteSigned | RemoteSigned |
| `WERKZEUG_RUN_MAIN` present | No | No |
| Native CIM enumeration | Three `CimException` failures, **PermissionDenied** | All three enumerations succeeded |
| Native global Listen entries | Unavailable due to access failure | **7** in each sample |
| `netstat` global LISTENING entries | **8, 7, 7** | **8, 7, 7** |
| `netstat` exit / encoding | 0; no embedded NUL | 0; no embedded NUL |
| Target-port native Listen/LISTENING | **Absent** | **Absent** |
| Target after empty accept | ESTABLISHED with fixture PID | Established/ESTABLISHED with fixture PID, plus state 0/blank native row |
| Socket reports bound / accepts connections | True / 1 throughout | True / 1 throughout |
| Fixture closed | Yes | Yes |

Host-context execution also read the parent PID **32996** without reading process command lines. The sandbox parent query was denied. These are process/permission metadata only; no usernames, SIDs, token handles, credentials or account information were captured.

### What this establishes

1. **The diagnostic environment is capable of exposing some LISTEN records.** It is incorrect to say all native TCP discovery is unavailable or that every native command is broken. Both tools report listener records elsewhere.
2. **Permissions explain one layer of failure.** Unfiltered sandbox CIM enumeration is explicitly denied. Host-context execution resolves that access failure, despite the process still not having an administrator token. It does not resolve target-listener qualification. “Run as Administrator” is therefore not an established fix and was not attempted as a further workaround.
3. **The owned target remains unqualified even when enumeration succeeds.** Host results show PID 35568 with numeric state **0/blank**, then state **5/Established** after connection, never the required state **2/Listen**. `netstat` likewise exposes only the established target connection. These records are not listener proof.
4. **Execution policy/bitness are not the observed difference.** Scripts execute successfully under RemoteSigned and 64-bit PowerShell in both contexts. No policy was changed.

## 3. Root-cause assessment

| Explanation | Assessment |
| --- | --- |
| Missing CIM permissions | **Confirmed in sandbox**, resolved for enumeration by host-context execution. Not the complete cause of the missing target listener. |
| Listener closed before discovery | Not supported by the bounded probes: the same listener remains bound, reports accept-connection flag 1 and later accepts an empty connection. Closure occurs after sampling. |
| Immediate startup timing | Delay and post-accept samples still fail; Stage 2H also held listeners across repeated observations. Longer waits were not exhaustively tested and are not a justified indefinite test strategy. |
| Command-output parsing | Not supported as the current blocker: native objects show state 0/5, `netstat` exits 0 with valid TCP/LISTENING rows elsewhere and no NUL corruption. Existing synthetic parsing tests already pass. |
| Wrong expected PID | Managed/current PIDs agree; target established records carry that PID. This proves connection ownership, **not** listener ownership. |
| Flask development reloader or parent/child ambiguity | Cannot explain these fixtures: no Flask/Python app or reloader is running. A real reloader would still require serving-child identification and is excluded by the current single-process verifier. |
| A proxy, network compartment, sandbox network layer, security product or Windows defect | Possible explanations for the socket/table disagreement, **not established by this evidence**. No such component or mapping was identified. |

**Root cause of the remaining native target-listener visibility gap is unknown.** The proven facts are the sandbox permission failure and the persistent mismatch between socket behavior and the target's native listening-state representation. State 0, an established socket, a PID-0 row, another port or a related process must not be reclassified as LISTEN to make the test pass.

The Stage 2G subprocess/JSON/error-reporting defect was concrete and has already been corrected. This stage demonstrates no additional fixable verifier-code defect. No authentication bug or production Supabase defect is established.

## 4. Feasibility of the current verifier

The verifier has useful synthetic coverage and correctly refuses missing/contradictory native evidence. Its **80 Stage 2H tests are historical regression evidence**, not newly rerun results here. No validator code changed, so another broad test run was unnecessary.

Six pure checks replayed this stage's actual observation sets through the unchanged validator; all six correctly rejected the unqualified target. [validation-checks.json](validation-checks.json) records those results and the unchanged source fingerprint. These checks made no network/subprocess call and do not turn the isolated native result into a PASS.

As a required gate for the localhost capstone rehearsal, it is **not practical in this observation context**:

- Its required native owner proof cannot currently be obtained consistently for an independently created target listener.
- Correct parsing and more observer layers cannot create an absent native listening-state record.
- Continuing to repeat startup/permissions/preflight variations without a demonstrated fixable defect risks spending demonstration time without increasing assurance.
- Previous Stage 2E observations do not qualify a new process/profile; the Stage 2B login remains owner-reported and indeterminate.

**Freeze the current automated workflow.** Keep its code, strict PID rules, stop markers and evidence unchanged. Do not add fallback acceptance, disable safeguards, relabel manual evidence as native-qualified, or create another verifier-development phase by default.

Reconsider it only if a concrete external fix is demonstrated—for example, a trusted host observation reproducibly exposes both native LISTEN records for the exact owned target and matching serving PID, or a known good native row exposes a specific parser defect. That would justify a bounded retest of that defect, not an open-ended redesign.

## 5. Recommended replacement: limited manual browser verification

This is a **proposed future procedure requiring separate approval**, not an execution authorized or performed now. It uses the existing RosaGo application and ordinary owner-controlled browser/console, without claiming the automated verifier's PID/evidence standard.

### Preconditions and approval

The owner must explicitly accept **operator-observed demonstration evidence** and authorize the intended actions. If independently verified native PID/capture is a formal acceptance requirement, this alternative is insufficient: remain NO-GO and pause until the observation environment is qualified.

Before a manual session, privately confirm the isolated nonproduction project and existing dedicated User account; unchanged credential; no unexpected mail/business-write hooks; one controlled localhost process; development mode and startup refusal retained. Do not infer a test backend solely from `.env` or workspace location.

Approval should identify **one manual User `POST /login`**, its provider session/sign-in/security-log effects and necessary protected reads/validation. No account creation, Admin submission, password/mail action, business/Storage mutation, Gemini call, retry or provider-wide sign-out is included. No password/token is given to the agent. Ordinary login/reads can have provider session/metadata effects; they are not wholly read-only operations.

### One finite manual session

1. The owner starts the unchanged app in a known desktop terminal, at the workspace, with a single process and no debugger/reloader:

   ```powershell
   .\.venv\Scripts\python.exe -m flask --app app --no-debug run --host 127.0.0.1 --port 5000 --no-reload
   ```

   Confirm the intended local origin in that terminal. Do not stop unknown existing servers without permission. No anonymous full preflight or server launch is performed by this report.

2. Open a fresh private browser profile at the exact `http://127.0.0.1:5000/login`. The owner confirms the expected page and its corresponding ordinary console request line. If the chosen console does not observe the page request, **stop before entering credentials**. This is an operator correlation check, not independent native PID attestation.
3. **Only after a new explicit one-attempt authorization**, the owner types the existing User credential directly into the masked form and clicks Log In once. Do not use clipboard credentials, Show password, tracing, DevTools payload inspection, screenshots or password saving. An error/timeout/uncertain result consumes the attempt; do not retry or reset the password.
4. Privately confirm the expected User identity, open protected `/user`, refresh that page once, and visit `/admin` once without submitting an Admin form. Expected: User state persists and Admin access requires separate Admin login. Do not edit the profile or other records. Distinguish protected-page rendering from a public homepage success message.
5. Record only alias, route path without query, visible outcome, timestamp and HTTP status **only if actually observed in a non-sensitive console request line**. Do not copy raw terminal logs, provider output, emails, credentials, cookies or tokens. Stop on unexpected identity, access, provider or write behavior. Close owned local browser/server state as authorized; a local logout submission needs its own explicit inclusion. No automatic provider revocation or cleanup writes.

### Evidence limitations that must remain visible

- Label results **OWNER/OPERATOR-OBSERVED**, not “independently verified” or “native-PID-qualified.” The observer could use the wrong terminal/tab; request-line correlation reduces this risk but does not provide the rejected verifier's assurance.
- A public page 200 is not authentication proof. A protected page and private identity check are stronger user observations, not independent token-validation/revocation evidence.
- Repeated protected access samples session continuity at that time; it does not qualify expiry, refresh, cross-process persistence, all Admin policies or production security. Existing isolated tests can support those contracts while remaining clearly labeled synthetic.
- The normal app has no new programmatic one-attempt or provider-egress enforcement in this manual procedure. The operator controls the budget and approved routes. Unexpected submissions/network effects are not guaranteed impossible. This is a different testing/control standard requiring explicit acceptance, not a silent relaxation of the automated gate.
- Provider session/security metadata and logs may remain after local closure. No guarantee of zero hosted side effects or automatic rollback is made. An Admin login or simultaneous A/B rehearsal would need separate permission and its own stated account/request scope.

## 6. Finite next-step checklist

1. **Decision:** choose whether the limited manual evidence standard is sufficient for the capstone demonstration. If native attestation is mandatory, pause; do not schedule more automated preflight development without a concrete fix.
2. **If acceptable:** obtain fresh permission for one owner-run manual session, explicitly acknowledging its evidence/control limitations, isolated target, provider session effects and ending/cleanup scope. This diagnostic prompt grants no login permission.
3. **Execute once only after that approval:** owner-controlled terminal/private profile, anonymous page/console correlation, exactly one User login, bounded User continuity/Admin-denial observations, no retry or Admin credential submission.
4. **Close the loop:** produce a short sanitized manual outcome report with operator-observed status and remaining gaps. A failure calls for investigation of that specific app/provider symptom; it does not automatically start another verifier-development phase.

There is no fifth development phase or ongoing diagnostic loop planned. The current automated gate remains closed unless new concrete native evidence changes the feasibility decision.

## 7. GO/NO-GO and preservation

| Action | Decision |
| --- | --- |
| More automated/full browser-client preflight using the current verifier here | **NO-GO**: native target listener proof remains unqualified. |
| Further verifier-development phase without a demonstrated fixable defect | **NO-GO**. |
| Review/approve the limited manual procedure | **GO for consideration**, with explicit acceptance of its lower assurance. |
| Execute a manual anonymous sanity check or live login under this diagnostic prompt | **NO-GO**: no such execution authorized now. |
| One future manual User test | **Conditional GO** only after the owner accepts the evidence standard and separately authorizes its exact scope. |

Only the new bounded diagnostic script, sanitized context results/summary and this report were added. Existing fail-closed validators, authentication code/configuration, session adapters and startup safeguard were not edited. Stage 2B's seven artifact fingerprints still match the preserved baseline; its consumed authorization remains consumed. No real RosaGo authentication/preflight, Supabase Auth request, production database/Storage change, mail/Gemini request, deployment, staging, commit or push occurred. **Diagnostics and strategy decision complete; stopped pending approval.**
