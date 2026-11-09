# Phase 2Q — Local Demonstration Readiness and Functional Verification

Verified 2026-11-05–06, Asia/Manila. Reference: [Phase 2P](../phase2p-recovery-boundary/REPORT.md).

**GO for the constrained, synthetic local demonstration described below. NO-GO for presenting a complete live-Supabase/email/AI workflow as verified.** The existing development User/Admin implementation passed regression and browser verification without activating PostgreSQL, Redis or any new session architecture. Live Supabase writes were intentionally blocked because the configured project is external and not approved as disposable.

The safe demonstration covers independent accounts, Admin destination lifecycle, Environment, synthetic photos, User synchronization and synthetic audit attribution. Registration/email/recovery, itinerary persistence and AI have passing isolated contracts, but are **not live-provider acceptance** and are not fully implemented in the interactive demo double. Keep that distinction visible to the panel; do not describe mocked records, email or audit events as production transactions.

## 1. Scope, active configuration and preservation

Read-only inspection found `ROSAGO_AUTH_MODE` absent in the workspace environment, so `app.py` defaults to **development**. `session_realms.py` selects separate process-local User/Admin credential stores and an Admin browser-state store. User browser state uses Flask's signed cookie; Admin uses an independent opaque HttpOnly cookie scoped to `/admin`. Credentials remain in server memory. A User cookie is not Admin authority, and an Admin cookie is not User authority.

This mode is **single-process, loopback-only**. Do not run multiple workers or a reloader: stores are not shared and restarts lose auth/recovery state. User mutable signed-cookie state still has the previously documented stale-response limitations; do not imply the PostgreSQL concurrency improvements are active. The credential stores enforce 30-minute idle and eight-hour absolute lifetimes. Admin browser state has separate CAS/expiry. Plain-HTTP localhost uses development cookie settings; it is not a public HTTPS security profile.

The configured Supabase URL/key are present, HTTPS/public-key-shaped, and the Flask secret meets a 32-character length check. Storage and Gemini keys are present; ORS key is absent, so routing defaults to OSRM. Gemini uses the code-default model because no model override was found. Tourism/Environment flags are already configured; none were changed. A presence/length check is not proof of secret quality, provider permission, model availability or a safe database target. No secret, project URL, token or key value is included in the inventory.

**Do not run ordinary `python app.py` or a plain Flask CLI against this workspace's inherited `.env` for the write walkthrough.** That could connect forms to the external project. The supplied synthetic launcher clears inherited configuration, suppresses dotenv loading, uses fake provider credentials, and blocks outbound server socket connects before importing the unchanged application. It binds only `127.0.0.1:5089`, one process, no debugger/reloader. It does not remove or bypass the production startup refusal; it explicitly exercises the permitted local development mode.

All changes are new artifacts in this directory. No existing application, test, SQL, secret file or session implementation was edited. Existing uncommitted work was preserved. No production SQL, records, Storage, Auth sessions, feature flags, staging, commits, pushes or public deployment occurred.

## 2. Exact verification results

| Verification | Result | Scope |
| --- | --- | --- |
| Full Python regression | **1,108 passed; 1,407 subtests passed; 74 skipped; 175.19 s** | Mocked providers/temporary stores. Skips are 63 opt-in Redis and 11 opt-in PostgreSQL storage cases; experimental backends intentionally not activated. |
| JavaScript regression | **69 passed; zero failures** | Local DOM/behavior tests; 476.6534 ms recorded. |
| Real Chromium browser | **31 checks passed** | Two tabs, one temporary profile, existing development auth/routes/templates; synthetic business/Auth/Storage transports. Desktop and mobile. |
| Anonymous public connectivity | **Four HTTP 200 responses** | Weather, OSRM route, OpenStreetMap tile and Leaflet JS. No API credentials, Supabase or billed AI request. |
| Actual application routing service | **PASS** | Default OSRM adapter returned validated estimated driving geometry with 31 coordinates for synthetic public Santa Rosa points. |
| Actual application weather service | **INTERMITTENT / NOT READY for a promised live forecast** | Earlier application probe returned a snapshot; final probe returned `None` despite the simple temperature endpoint succeeding. Cause not established; do not weaken validation or claim a forecast. |

Artifacts: `full-output.txt`, `full-test-results.xml`, `javascript-output.txt`, `browser-results.json`, `browser-output.txt`, `preflight-results.json`, screenshots and `demo-run-summary.json`. The public probes and the two application service calls are separate requests; success of a minimal temperature GET is not success of the full forecast parser. Observed connectivity is a point-in-time check, not an availability guarantee.

The browser script initially selected the navbar logout form instead of publication confirmation. Later image checks exposed fixture multipart decoding and background-tab/lazy-image timing. These were corrected only in new test/demo artifacts; the final run used the exact confirmation form and foreground navigation. Initial failed evidence is retained. No existing RosaGo runtime bug was repaired or silently changed.

## 3. User system verification

| Flow | Isolated result | Remaining live evidence |
| --- | --- | --- |
| Registration | PASS: validation, consent, safe errors, metadata/redirect contract and no unintended sign-in. | BLOCKED: creating a real Auth account requires a disposable project/test mailbox. |
| Email verification/resend | PASS: code expiry/validation, throttles, CSRF/origin, recovery isolation and truthful provider failure. | BLOCKED: actual inbox delivery, provider redirects and real verification. |
| Login and logout | PASS: actual browser login forms for synthetic User A; independent logout and both login orders. | Real provider credential validity not exercised. |
| Password recovery/reset | PASS: PKCE/callback/reset contracts, expired/wrong grants, CSRF and Admin isolation in tests. | BLOCKED: sending a real recovery email and updating an Auth password. |
| Profile/settings/account management | PASS in full regression; no production profile update. | Interactive fixture supports account display, not all persistence operations. |
| Explore/details/categories | PASS: publication filtering and parsing tests; browser sees edited published name/Environment/photo. | No current production catalog audit was attempted. |
| Itinerary quiz/recommendations/preview | PASS in `test_itinerary_quiz_*`, `test_itinerary_preview*`, `test_recommendation_engine`, selection and personalized-recommendation suites. | Not a live persisted itinerary walkthrough. The fixture has no complete trip/draft database RPC implementation. |
| Maps/routing | PASS for marker/publication contracts, routing service/routes and JS tests, plus anonymous real routing/tile/CDN checks. | No comprehensive interactive geolocation/navigation rehearsal; fixture server blocks real routing IO. |

The registration, email and reset routes still belong to the unchanged application. The synthetic launcher is deliberately not an email server or Supabase emulator; do not attempt to demonstrate completed registration/reset in it. Use the recorded tests until an isolated provider environment is explicitly approved.

## 4. Admin verification and User synchronization

The full regression includes `test_admin_management.py`, `test_admin_photos.py`, `test_admin_destinations.py`, `test_admin_authorization.py`, `test_admin_audit.py` and `test_destination_environment.py`.

Fresh browser results:

1. User A logs in, then Admin B in another tab in the same profile. User identity stays A; Admin account stays B.
2. Admin creates one synthetic Draft with Environment NULL; User detail returns 404.
3. Admin saves Indoor plus a synthetic PNG, then publishes. User detail displays the edited name, Indoor and the same photo; browser loads its pixels.
4. Admin saves Outdoor and replaces the photo. User refresh shows Outdoor and a new photo path.
5. Admin submits an unrelated save with Environment omitted. Outdoor and the photo remain unchanged.
6. Admin saves Mix of Both and unlinks the photo; User shows Mix of Both and no uploaded photo.
7. Admin explicitly clears Environment; User shows **Not recorded**.
8. Admin archives the synthetic destination. User detail returns 404 again. Synthetic audit UI attributes the changes to B.
9. User logout preserves Admin. The reverse login order and Admin logout preserving User also pass, including mobile navigation.

Final synthetic state: **one destination, archived; eight audit events, all actor UUID `22222222-2222-4222-8222-222222222222`; two in-memory photo objects retained.** The eight actions are create, edit, publish, four further edits, archive. Unlinking a photo does not delete its object. These are in-memory doubles, not SQL audit-trigger or Supabase Storage executions, and all vanish on fixture restart.

The demo transport shares one mutable catalog between Admin and the actual public `PlacesService`, so this is a genuine browser check of application propagation through the shared read contract, not two independent canned pages. For display only, fixture HTML rewrites fake provider photo URLs to a local in-memory image route. This proxy is not a product change or a test of real Storage/CDN delivery.

## 5. Security and external services

**PASS locally:** CSRF/Origin validation, single-use realm-bound login challenges, cross-realm token rejection, nonmember Admin denial, current membership checks through mocked database transports, Admin cookie rotation, malformed/duplicate cookie denial, independent expiry/revocation and B's mutation bearer/actor contracts. Audit read authorization, escaping and changed-field rendering also pass. Stale-version destination writes are rejected in existing tests. No SQL RLS or real database audit insertion was executed.

Development auth is not protected shared storage. Keep the trusted demo operator on loopback, do not expose port 5089 to LAN/tunnel/public hosting, and do not use synthetic passwords for real accounts. The fixture's known test actors are intentionally accepted by its mock password adapter; that is not live Supabase authentication. It must never be deployed. Use a separate browser profile/private session; close it afterward.

External/API findings:

- **Open-Meteo:** minimal city weather GET succeeds. The full application adapter was not consistently successful; its safe unavailable state remains appropriate. Do not substitute stale/fabricated data or change weather-exposure logic to make the screen look live.
- **OSRM:** keyless driving request and actual adapter geometry validation pass. It does not prove walking/transit support; ORS is not configured. Respect the app's per-process request throttle and provider availability.
- **Leaflet/OpenStreetMap:** sampled JS asset and tile are reachable. A complete map still depends on internet/CDN access and browser permissions. No personal geolocation was sent.
- **Gemini:** key presence and model syntax/configuration were inspected without exposing the key. Structured explanation/chat, catalog grounding, escaping, rate limiting and failure fallback pass with `MockTransport` in `test_gemini_service.py` and `test_ai_routes.py`. **No live generation, quota/model entitlement or billing request was attempted.** Missing approval for provider usage is an unresolved live-demo dependency, not a passed AI integration.
- **Supabase Auth/PostgreSQL/Storage:** configured external target was not contacted. Real account writes, trip persistence, publication, photo upload and audit insertion against that project are BLOCKED for this task.

## 6. Repeatable local startup

From the repository root in PowerShell, use the existing virtual environment; do not install/upgrade dependencies or edit `.env` during the rehearsal:

```powershell
.venv/Scripts/python.exe docs/admin-finalization/phase2q-local-demo-readiness/preflight.py
.venv/Scripts/python.exe docs/admin-finalization/phase2q-local-demo-readiness/demo_fixture.py
```

The first command only inventories configuration with redacted values. Optional `--public-connectivity` makes anonymous public weather/routing/map/Leaflet reads; no project Auth or AI calls. The second starts the isolated fixture and stays running. Open **http://127.0.0.1:5089/login** and **http://127.0.0.1:5089/admin/login** in two tabs of one browser profile.

Synthetic accounts only:

| Realm | Email | Password |
| --- | --- | --- |
| User A | `user-a@example.invalid` | `Local-test-password-1!` |
| Admin B | `admin-b@example.invalid` | `Local-test-password-1!` |

Start from an empty fixture each rehearsal. Use `demo-photo.png` in this directory for manual photo testing. New destinations are Draft; use the actual publication confirmation page, not the navbar logout form. Refresh User details after Admin saves. Admin audit is `/admin/audit-logs`. The fixture starts with no catalog/trips, and unimplemented provider operations fail visibly; weather is deliberately unavailable and AI has no real key. Do not promise an interactive persisted Planner or email flow in this launcher.

Stop with Ctrl+C in its terminal, or from a separate terminal:

```powershell
Invoke-WebRequest -UseBasicParsing -Method POST -Uri 'http://127.0.0.1:5089/__demo/stop'
```

Shutdown writes a synthetic run summary. Restart discards all data/photos/audit and auth sessions; clear localhost site cookies or start a new private session if old tabs retain stale state. Never delete real Storage objects/audit history as demo cleanup. There is no demo server or debug browser intentionally left running after this verification.

To repeat automated local contracts:

```powershell
.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider
$testFiles = @(Get-ChildItem -LiteralPath tests -Filter '*.js' | ForEach-Object { $_.FullName })
node --test @testFiles
```

`browser_checks.mjs` is the optional Chromium/CDP automation: it expects this fixture on 5089 and a dedicated temporary Chrome profile with loopback debug port 9251. Do not point it at a normal browser profile or another server. It clears cookies in that dedicated profile. Screenshots/results from the completed run are already included; browser automation is not required for the manual checklist.

## 7. Capstone demonstration checklist

| Step | Expected result |
| --- | --- |
| 1. State the scope | Explain that accounts/data/providers are synthetic; production is untouched. Show this report's live-provider limitations. |
| 2. Start the fixture | Loopback 5089, development mode, one process, no reloader or experimental store. |
| 3. User A then Admin B | Both identities remain in separate tabs within one browser. |
| 4. Create Draft, leave Environment blank | Draft saved, Environment Not recorded; User detail unavailable. |
| 5. Add PNG, set Indoor, publish | Confirmation required; refreshed User shows name, Indoor and photo. |
| 6. Edit Outdoor and replace PNG | User refresh reflects both; unrelated fields preserved. |
| 7. Omit Environment, then clear explicitly | Omission preserves Outdoor; clearing produces Not recorded. Test Mix of Both separately. |
| 8. Unlink photo, archive | Photo disappears from User without object deletion; archived detail is 404. |
| 9. Inspect audit | Eight events for the automated sequence; all attributed to synthetic Admin B. Manual extra saves add extra events. |
| 10. Independent logout | User logout leaves B signed in; Admin logout leaves A signed in. Repeat reverse login order. |
| 11. Present other feature evidence | Show passing isolated registration/email/recovery, itinerary/recommendation, category/map and AI tests. Do not substitute these for a live end-to-end claim. |
| 12. Present availability handling | Weather/provider unavailable states are truthful; public API preflight results are point-in-time evidence. |
| 13. Stop/reset | Close fixture/browser, restart only if needed; no production cleanup action. |

### Safe manual procedure for blocked live flows

This is **not authorization to provision infrastructure or write any existing project**. Before live testing, obtain explicit approval for a named disposable Supabase target, test mailboxes and any Gemini usage budget; separately verify its schema/membership/Storage setup and callback origin. Do not infer approval from existing `.env` values. No SQL for that setup is executed here.

In the approved isolated target only: register a new test User, confirm actual email delivery/code and resend cooldown, log in, request PKCE recovery in the same browser, follow the reset link and change only that test account's password; confirm old/expired links fail and Admin B remains signed in. Use a separately approved test Admin membership, create a new clearly synthetic Draft, run the create/edit/photo/publish/archive sequence, and compare all pre-existing records/photos/audit against checkpoints. Preserve audit history; archive only the test record. Test Planner persistence only on that account. For Gemini, send one bounded synthetic catalog question, verify grounded output/model availability and redacted logs, then test its unavailable fallback. Any uncertain response stops mutation testing. Real endpoints must not be used until this isolation is verified.

## 8. Outstanding limitations and final decision

No unresolved application regression failure was observed. Remaining limitations are material:

- The ordinary environment points at an external, unapproved database. Full live mutation/identity testing is blocked.
- The interactive demo transport intentionally implements only the verified account-display/catalog/photo/audit subset. Unsupported trip/Planner/email/provider calls can return unavailable responses; it is not a full isolated backend.
- Live weather validation was intermittent; full-forecast reliability remains unresolved. Public routing, tiles and CDN still need internet during an online map demo.
- Live Gemini model/quota/output and real email/callback delivery remain unverified.
- Development sessions/recovery are process-local, expire and vanish on restart; User browser state does not gain the experimental shared-store guarantees.
- Database policies, Storage authorization/CDN and SQL audit behavior were tested as contracts/doubles, not executed on a real Supabase instance.

**Final: GO for the explicitly constrained synthetic local demonstration/checklist. NO-GO for a complete live-provider capstone walkthrough or public deployment.** If the panel requires live registration/email/reset, persistent itineraries, real uploads or generated AI responses, those are launch blockers until the approved isolated manual procedure passes. The eight production gates from Phase 2P remain FAIL; this local-demo work does not close or redefine them.

New artifacts include this report, the synthetic launcher/data double, preflight/browser/diagnostic/evidence scripts, sample PNG, screenshots, fresh test/probe/browser evidence and retained fixture-failure logs. Prior source and SQL preservation is recorded by `verify_evidence.py`/`verification-summary.json`. Stop pending approval.
