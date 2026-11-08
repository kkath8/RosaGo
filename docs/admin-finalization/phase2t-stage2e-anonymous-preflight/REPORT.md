# Phase 2T Stage 2E — Anonymous Browser/Client Preflight Verification

Verified **2026-11-06, Asia/Manila**. Reference: [Stage 2D correction and qualification](../phase2t-stage2d-verifier-correction/REPORT.md).

**PASS for the actual anonymous browser/client path. Conditional GO for a separately authorized User retest, with a fresh preflight on its new run. No authentication was enabled or performed.** The corrected collector captured an actual headless Edge profile, independent HTTP clients and a real anonymous Flask route under one matching run/PID/origin. The owned verifier is now closed; this is not an active login-ready session.

## 1. Scope, startup and existing-server handling

Initially `127.0.0.1:5000` belonged to existing Python process **19212**. An anonymous identity GET returned **404**, with no verification-run header. It was an unwrapped server, not an attachable corrected verifier. No credential form or protected content was read to investigate it.

The owner explicitly authorized stopping that process and restarting the unchanged application through the anonymous verifier, acknowledging loss of its process-local state. The normal sandbox denied termination. A sandboxed anonymous launch also failed its own identity check and closed before any application request. Its evidence is retained in [initial-sandbox-results.json](initial-sandbox-results.json) and its separate run directory. No provider traffic or authentication occurred.

Using the existing explicit authorization, the host-context command verified process identity/start time and stopped only **19212**. The corrected anonymous verifier was then started in the host context. This avoided treating a sandbox-local bind or generic localhost HTTP response as proof of the owner-browser path. No unrelated process was stopped, and no original server was restarted automatically afterward.

Actual approved startup:

| Item | Verified result |
| --- | --- |
| Origin/bind | `http://127.0.0.1:5000`, loopback only |
| Serving PID | **11564** |
| Public run ID | `921a2229eeb540fa87a55395103e968c` |
| Bound time, Asia/Manila | **13:23:00**, 2026-11-06 |
| Closed time, Asia/Manila | **13:25:43**, 2026-11-06 |
| Session architecture | Development; `RealmSessionInterface`; separate User/Admin `NormalAuthStore` instances |
| Experimental/shared adapter | No shared-session extension; no Redis/PostgreSQL authority activation |
| Debug/reloader | Disabled / absent |
| Authentication gate | Never armed; no allowance reserved or spent |

The original application was loaded with its existing configuration, after the nonsecret mode precheck. Authentication configuration, runtime source and startup safeguard were not changed. All HTTPX provider egress was denied for the entire application lifetime; **zero provider attempts** occurred.

## 2. Actual client and browser results

The Stage 2D assembly helper mounted the corrected collector as `server.app` and checked the actual bound address before readiness. The anonymous inner guard permits only GET/HEAD on selected anonymous routes, strips incoming application Cookie/Authorization headers before Flask, and blocks all submissions independently of the outer disarmed gate. Thus even accidental use of an existing application session cannot trigger refresh through this launcher.

| Check | Actual result |
| --- | --- |
| Same-process self-client identity GET | 200, expected JSON run/PID/origin, disarmed |
| Anonymous login HEAD | 200 with matching run/sequence and durable event; returns disarmed preflight message, not credential form |
| Actual Flask HEAD `/admin/login` | 200 through the real application and collector, proving a Flask route was reached; no body read, credentials or Admin sign-in |
| Separate client identity GET and login HEAD | 200/200, matching run/PID/header and durable HEAD sequence **18** |
| Native OS listener lookup | `Get-NetTCPConnection` returned `127.0.0.1:5000` owned by **11564**, matching process/identity/journal |
| Fresh headless Edge Start → Confirm → Login | All three anonymous navigations completed at the approved origin |
| Browser marker continuity | Confirmed by the collector; no cookie value exported |
| Browser's identity fetch | 200, same run and PID; `browser_preflight=true`, `browser_login_get=true` |
| Final auth state | `armed=false`, `spent=false`, zero form submissions |
| Browser cleanup | Owned browser stopped; its fresh test-owned profile removed without inspecting profile files |

The independent client's initial text-parsed `netstat` ownership check found no matching listener row, even though HTTP identity and event checks matched. It was treated as **not yet qualified**, not silently ignored. Native `Get-NetTCPConnection` then independently established the actual owner PID; saved HTTP evidence and journal sequence were combined with that native observation **without replaying HTTP again**. An additional PID-0 row was not treated as a serving process. The client tool now uses the native query for future runs. Failed text-query proofs are retained separately.

The browser was a new, dedicated **headless Edge** process with a fresh workspace-owned profile, no extensions/sync and no pre-existing app session. Only the approved local GET pages were navigated. Page interception permitted only GET/HEAD to the exact localhost origin; external page requests were blocked by policy. No screenshot, credential field, cookie inventory, auth header, HAR or existing profile was inspected. This qualifies an actual browser path, not the owner's future interactive window; that future window must repeat the anonymous handshake.

## 3. Durable capture evidence

Primary evidence:

- [anonymous-results.json](anonymous-results.json): actual-app startup, HTTP self-client observations, anonymous-only limits and terminal closure.
- [client-proof.json](client-proof.json), [listener-proof.json](listener-proof.json): independent HTTP/event proof and native listener ownership.
- [browser-results.json](browser-results.json): real browser navigation/continuity results; zero submitted forms/cookie inspection.
- [run journal](r/921a2229eeb540fa87a55395103e968c/events.jsonl), [final snapshot](r/921a2229eeb540fa87a55395103e968c/snapshot.json): request capture and terminal state.
- [evidence-validation.json](evidence-validation.json): capture-schema/source-fingerprint/Stage 2B preservation checks.

The successful run captured **13 requests: 9 GETs and 4 HEADs**, with corresponding statuses and one run/PID. They comprise readiness/self-client probes, independent identity/HEAD probes used while resolving listener visibility, the browser handshake/identity fetch, and two incidental browser GETs outside the allowlist. Those two paths were normalized to `other` and denied 404; no extra app/provider handler ran. They do not indicate an authentication error.

Only **one** request entered the actual RosaGo Flask route layer: the anonymous HEAD `/admin/login`, returning 200. The remaining requests were answered by the disarmed collector. The journal includes startup readiness, client attestation, marker confirmation, browser login GET and final closure. There are **no** `operator_armed` or `attempt_consumed` events and no non-GET/HEAD ingress.

The failed sandbox run had **zero ingress** captured and was closed/disarmed. Its existence illustrates why binding/READY alone is insufficient; independent identity/event/native listener/browser checks were required. This is consistent with the class of Stage 2B mismatch, but does not establish the exact historical Stage 2B process/browser route.

## 4. Evidence-redaction verification

All run journals were parsed against the Stage 2D event allowlist: run ID, PID, sequence, UTC time, fixed phase, normalized method/path and status. Snapshots were checked against the explicit public state/configuration-classification allowlist. Both source fingerprints match the unchanged Stage 2D collector. Final states are stopped, unarmed and unspent.

No passwords, application cookies, anonymous marker values, access/refresh tokens, Authorization headers, API secrets, raw request/response bodies or exception messages are in the collector evidence. The browser tool returns only approved metadata and the collector's public identity JSON; it never requests cookie inventories or reads credential fields. The anonymous marker is used only in browser/server memory and was discarded with the browser/profile and server.

Stage 2D's secret-canary/persistence tests remain prior synthetic qualification; they were not rerun or overwritten here. Actual Stage 2E evidence-schema checks pass. This does not claim a full OS-wide telemetry audit or inspect private browser/provider logs. The application's ordinary private configuration load is not copied into evidence; only approved startup classifications are retained.

All seven Stage 2B source/evidence file fingerprints still match the Stage 2C preservation record. Its owner-attempt-consumed ledger and stop marker remain unchanged and controlling. No new auth allowance was created in this anonymous phase.

## 5. Fail-closed checks

| Condition | Observed behavior |
| --- | --- |
| Existing unwrapped server | Identity 404/no run header; rejected as unqualified before credentials. Replaced only after owner authorization. |
| Sandboxed launcher/client path not established | Identity preflight failed, zero collector ingress; owned attempted run closed, no app/provider request. |
| Listener ownership not independently matched by text query | Client proof remained failed; browser/auth readiness was not inferred from HTTP 200. Native ownership evidence was required to complete qualification. |
| Collector disarmed | Login GET/HEAD exposes only preflight text. No arming method was called and no POST was sent. Submission rejection remains Stage 2D synthetic coverage, not a live auth submission in Stage 2E. |
| Disconnected after owned shutdown | One fresh anonymous identity GET failed with **ConnectError**; [disconnected-proof.json](disconnected-proof.json) marks execution disallowed. No request replay or other listener was accepted as equivalent. |

These are anonymous readiness failures, not login attempts. At no point did resolving them permit auth submission, refresh or provider access. The headless browser path was observed while all auth gates stayed disarmed. No empty/fake credential POST was sent to test refusal, because this phase prohibits authentication submissions.

## 6. Tooling and remaining limitations

New Stage 2E tooling: [anonymous_probe.py](anonymous_probe.py), [independent_client.py](independent_client.py), [browser_probe.mjs](browser_probe.mjs), this report and sanitized evidence/ready/finish files. The launcher adds an anonymous-only guard around the unchanged application and uses the existing corrected collector. It is not a live login sender and never calls `authorize_once`.

Important limits for the next stage:

1. **Network/process context matters.** Host-context launch and native listener enumeration were needed here. Do not assume a sandbox-local bind, a READY message or a text-parsed listener result establishes the owner's path. Require matching current run/PID, durable events and native loopback ownership again.
2. This actual anonymous run is closed; its marker/PID cannot authorize or qualify a new live run. Reperform preflight in the actual owner-visible private profile before any separately approved credential entry.
3. This launcher intentionally strips application credentials, blocks providers and never enables login. A future authorized login needs the reviewed Stage 2D wrapper over the original one-attempt/provider-restricted live guard, with exact scope and fresh approval. Do not remove all controls from the anonymous launcher as an informal shortcut.
4. No credential validity, Supabase session acceptance, logged-in dashboard, authenticated session continuity, live User/Admin isolation, email flow or Gemini connectivity was tested. Stage 2B remains indeterminate.
5. No runtime/authentication source was edited. The initially running server was stopped with specific permission and its in-memory sessions were lost; no provider sign-out/revocation/account cleanup was performed. The original server was not restored automatically. All owned verifier/browser processes were closed, and the temporary profile was removed.

## 7. Recommendation

**GO for the anonymous browser/client preflight demonstrated in this run. Conditional GO for a separately authorized single User login retest, after a fresh run repeats the native PID, independent client, owner-browser marker and durable-event checks before arming. NO-GO for login under Stage 2E itself, for reuse of Stage 2B authorization, or for skipping a new run's preflight.** Admin login remains separately gated.

Zero User/Admin logins, authentication submissions/refreshes, Supabase Auth requests, account/email/password operations, database/Storage/SQL writes or Gemini requests occurred. No experimental adapter activation, safeguard change, deployment, staging, commit or push. **Anonymous preflight complete; stopped and waiting for approval.**
