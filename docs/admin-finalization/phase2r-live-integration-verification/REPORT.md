# Phase 2R — Controlled Live Integration Verification

Verified **2026-11-06, Asia/Manila**. Reference: [Phase 2Q](../phase2q-local-demo-readiness/REPORT.md).

**GO for a read-only localhost catalog/map/weather demonstration. NO-GO for claiming a complete live User/Admin demonstration.** The real configured Supabase public endpoints and existing published data were successfully read, the unchanged Flask app started locally, and its live map and weather loaded. Real authentication, mail/reset flows, authenticated Admin reads/writes and Gemini generation remain unverified or blocked by this phase's restrictions.

No production write, account creation/sign-in, email, password change, upload, direct SQL submission, experimental session activation or public deployment occurred. No secrets, user identities, raw photo URLs, destination names or provider response bodies were saved in evidence. The read-only server and disposable browser were stopped afterward.

## 1. Startup and verification safeguards

The actual existing `app.py` loaded using the workspace's configuration. `ROSAGO_AUTH_MODE` remains absent and therefore selects the existing **development** mode; the probe rejects a different mode rather than overriding it. It used `RealmSessionInterface`, separate User/Admin `NormalAuthStore` instances, no shared-session extension and debug disabled. The production startup refusal remains unchanged.

The verification wrapper bound only `127.0.0.1:5099`, one process, no reloader. It allowed selected public GET/HEAD pages and rejected form writes and credential callbacks before entering Flask. HTTP-client egress was restricted to GET/HEAD on specified public Auth/catalog/photo and weather/routing/tile paths. Zero unexpected outgoing requests were blocked: no code attempted a disallowed provider operation in the observed run. This wrapper is a new test harness, not a modification to the working application or an alternative session implementation.

Actual localhost GET results:

| Path | HTTP result |
| --- | --- |
| `/login`, `/admin/login` | 200 / 200 |
| `/register`, `/forgot-password` | 200 / 200 |
| `/places`, `/api/places` | 200 / 200 |
| `/map`, `/api/weather` | 200 / 200 |
| `/auth/status` | 200, anonymous |

No form was submitted. Anonymous local browser cookies and login challenges were created in memory; no real Supabase Auth session was created. The only direct Supabase credentials used were the configured public application key, validated by `PublicPlacesClient`; the Storage secret was not used.

## 2. Supabase Auth connectivity

**PASS — public Auth endpoint connectivity/configuration reads.** `GET /auth/v1/health` and `GET /auth/v1/settings` both returned HTTP 200 through the configured gateway/public key.

Public settings reported:

- Email provider enabled.
- Sign-up not disabled.
- Automatic email confirmation disabled, so email confirmation is required for ordinary email sign-up.

This verifies reachability and the listed public settings, **not** password validity, completed registration, OTP delivery, SMTP permissions, Admin membership or authenticated JWT/session validity. No `/token`, `/signup`, `/recover`, `/verify`, `/resend` or sign-out call was made. No privileged Auth management endpoint was queried.

## 3. PostgreSQL-backed data reads

**PASS — published destination data via PostgREST, using the application's public access model.** The bounded public query returned **35 published destinations**, `Content-Range: 0-34/35`. Every returned status was published; 34 Environment values were NULL and one row referenced a photo URL.

Before and after verification, the returned published projection had the same count, range and SHA-256 fingerprint. The projection included ID, slug, status, image URL, Environment, updated timestamp and coordinates. Raw rows were retained only in process memory. The actual public `PlacesService`, Explore, API and map also retrieved data successfully.

**Scope limit:** this is not a count of all production rows or a reconciliation against the historical 49/50-record snapshots. Draft/archived rows were not read with privileged credentials. No statement is made about unqueried fields or concurrent changes outside this projection. No database write was issued by the probe.

**Direct PostgreSQL protocol/SQL connection: NOT TESTED.** RosaGo's existing integration reads the PostgreSQL-backed REST API; no direct DB DSN, SQL Editor or PostgreSQL session adapter was used. REST success is not a separately qualified wire-protocol connection or evidence about all RLS roles.

## 4. Storage and existing photos

**PASS — the one distinct public Storage URL referenced by the returned published rows was retrievable.** It matched the same configured project and `destination-images` public-object prefix. No third-party/signed URL was followed.

- Public HEAD: HTTP 200, `image/jpeg`, reported length **76,976 bytes**.
- Bounded GET: HTTP 206; first **4,096 bytes** read with valid JPEG signature.
- No bearer/admin secret, upload, replacement, deletion, bucket listing or policy update.

The prefix validates retrieval and image signature, not a full-image decode/render. It does not establish the total number of Storage objects or check unreferenced/private objects. Photo bytes and URLs were not archived. Storage upload authorization remains untested, as required.

## 5. Email, verification, recovery and login configuration

**PASS — local form rendering and read-only public Auth settings. UNVERIFIED — actual delivery, credentials and recovery completion.**

Source inspection confirms these existing callback destinations:

| Flow | Existing source configuration |
| --- | --- |
| Registration callback | `http://127.0.0.1:5000/auth/callback` |
| PKCE password recovery | `http://127.0.0.1:5000/auth/reset-callback` |

The temporary probe origin was **5099**, not 5000. That was suitable for read-only page verification, but it must not be represented as an email callback rehearsal. Future approved manual account testing should use the exact configured 5000 origin or a separately reviewed callback/configuration change, and verify the hosted redirect allowlist.

Hosted Site URL, redirect allowlist, email templates, SMTP credentials/sender, recipient restrictions and email-rate quotas were **not** exposed by the public settings read and were not inspected through management credentials. Do not infer that custom SMTP is configured merely because an email form renders or a Storage/Gemini key exists. Supabase's documented SMTP/delivery restrictions depend on its actual project configuration. [Supabase email configuration](https://supabase.com/docs/guides/auth/auth-smtp).

No real email was sent, no address/password was submitted, and no account or provider session was created. The Phase 2Q isolated email/PKCE regressions remain useful contract evidence; they are not live delivery acceptance.

## 6. Gemini status

**BLOCKED — no Gemini request performed.** A key is present locally and the configured code-default model name passes the application's syntax check. This does not establish key validity, model entitlement, remaining quota or a no-charge allowance.

No explicit bounded generation allowance with verified quota/billing safety was available. Therefore no generation, model-list or authenticated Google API call was attempted. Zero potentially billable generation requests were made. A key-presence check is not a Gemini connectivity PASS.

The existing explanation/chat/failure contracts passed in Phase 2Q with mocked providers. Live generation requires a separate explicit user approval identifying the permitted project/key, model, request/token ceiling and billing limit. If that cannot be verified, retain the unavailable/fallback behavior and do not advertise live AI as demonstrated.

## 7. Weather, Leaflet, OpenStreetMap and routing

### Weather

**PASS during this run; previous intermittency remains documented.** The real local `/api/weather` returned 200. Two additional fresh, unchanged `WeatherService` instances each returned validated **three-day** snapshots. All three captured provider responses were 200, used the expected Asia/Manila offset, started forecasts on the current local date, and had a reported age of approximately 11–13 minutes. No stale fallback or relaxed validation was introduced.

Phase 2Q observed both success and an unavailable result. That failure **did not recur here**, and its cause is not established. These short probes do not prove sustained availability, rule out near-midnight/provider/network behavior or justify hiding a future unavailable state. Keep the app's existing freshness/schema checks and truthful failure display. The provider's forecast API supplies the required weather fields/timezone data. [Open-Meteo documentation](https://open-meteo.com/en/docs).

### Map and routing

**PASS — actual browser loading and a bounded routing read.** The localhost map loaded vendored Leaflet JS/CSS with HTTP 200; Chromium reported Leaflet **1.9.4**, an initialized map, **20 marker elements**, **eight loaded tiles**, no displayed tile-failure notice and zero captured JavaScript exceptions. No form was submitted or personal browser geolocation requested.

Leaflet is served from `static/vendor/leaflet/`; the live map does **not** require the unpkg probe used in Phase 2Q. The map background still requests OpenStreetMap tiles over the internet. A separate sample tile GET returned 200. Thirty-five published records and 20 map markers are different scopes: the map includes only records meeting its coordinate/read contract, not necessarily every published destination.

The default OSRM adapter returned validated estimated driving geometry with **31 coordinates** for fixed synthetic Santa Rosa endpoints. This was a read-only service call, not a saved itinerary or interactive route-form submission. ORS key/provider overrides are absent, so driving-only OSRM is the configured fallback; walking/transit and ORS quota are not verified.

## 8. User/Admin session verification

**PASS — fresh isolated regression: 27 tests passed in 8.53 seconds.** `tests/test_independent_sessions.py` ran with network-blocked synthetic actors. It covers both login orders, independent logout/expiry/revocation, cross-realm CSRF and cookie rejection, fixation, membership denial, recovery isolation and B's mutation attribution contract. No experimental store was selected.

The real localhost read-only browser separately received distinct HttpOnly cookie scopes: User `session` at `/`, Admin `rosago_admin_session_dev` at `/admin`, with development HTTP settings. Their values were not recorded. Startup confirmed distinct credential stores. These anonymous cookies are **not proof of authenticated live A/B sessions**.

**Live User A/Admin B authentication: NOT TESTED.** A real sign-in can create/update provider session history, which is outside this read-only phase. Reusing a real token could refresh or expose it, so no existing account token/cookie was loaded. Supabase distinguishes access-token validity from current session/revocation state; endpoint health does not establish either for an account. [Supabase sessions](https://supabase.com/docs/guides/auth/sessions).

Existing local restrictions remain: one process, no reloader/multiple workers, process restart loses auth/recovery state, no public exposure or production security claim. The startup safeguard remains intact.

## 9. Final integration checklist

| Category | Integration / outcome |
| --- | --- |
| **Verified now** | Actual app startup; public Auth health/settings; 35 published-row reads and stable selected fingerprint; one public photo prefix; Explore/API rendering; live Leaflet/tiles/markers; current weather; estimated OSRM driving; separate local stores/cookie scopes; 27 synthetic independent-session cases. |
| **Unverified** | Direct SQL connectivity; all hidden records/fields; full photo rendering/object inventory; hosted SMTP/redirect allowlist; real password credentials, email/OTP/reset delivery; live authenticated A/B sessions and Admin reads; account-specific provider validity; persistent Planner workflows; sustained weather/route availability. |
| **Blocked / approval required** | Gemini generation without quota/billing approval; account creation or real login/session mutation; email/resend/OTP/reset/password changes; destination/publication writes; Storage uploads/replacements/deletes; audit insertion; any schema/Auth/policy/configuration change. |

Read-only checks may be repeated with `live_probe.py`: it keeps all form actions blocked, uses port 5099 and closes automatically after its bounded browser window. It removes its own transient ready/done markers on startup. `browser_probe.mjs` requires a **dedicated disposable** Chromium profile at loopback debug port 9252; do not attach a personal browser. Its own file output contains only page/map/cookie metadata. No running verification server/browser is intentionally left behind.

### Safe manual approval checklist

1. Before a complete workflow rehearsal, explicitly authorize a **named isolated/disposable backend and test accounts/mailboxes**, rather than inferring write permission from the workspace's production-like `.env`.
2. Inspect hosted Site URL/redirect allowlist and SMTP/sender/recipient limits read-only. For future callback tests, confirm the exact 5000 origin. Do not send a diagnostic email without approval.
3. If authenticating test A/B is approved later, record that it creates provider session state. Verify both login orders and independent local logout; do not apply global sign-out to unrelated sessions. This phase did not approve or perform it.
4. Request Gemini approval separately: chosen model, maximum one synthetic prompt, strict output-token cap, project quota/free allowance and maximum permitted cost. If any is uncertain, do not send the request.
5. Keep the read-only server for public Explore/map/weather demonstrations. Do not remove its POST blocker and use production management forms as an informal test. Business, photo, email, password and itinerary writes require a separately authorized disposable target and preservation/cleanup plan.
6. Keep real keys/tokens/mailboxes/screenshots out of shared reports/logs. Stop at ambiguous responses. Close the local server/browser and retain aggregate evidence only.

## 10. Decision, files and preservation

**GO for a controlled read-only localhost catalog/map/weather demonstration. NO-GO for a complete live-integrated localhost demonstration at this point.** The remaining blockers are live identity/mail/recovery acceptance, authenticated A/B verification under approved disposable scope, and Gemini quota/model/generation approval. Successful public reads do not close those gaps. Prior production-readiness gates remain FAIL; this phase does not authorize deployment or activate an adapter.

New files only in this directory: this report; `live_probe.py`, `browser_probe.mjs`, `configuration_review.py`, `verify_evidence.py`; sanitized live/config/browser/session-test results and logs; transient ready/done/browser-process metadata; `verification-summary.json`. No raw rows, photos, API responses, destination names, project hostnames, credentials, cookie values or personal identities are archived. Code-source filenames and synthetic tests are retained as evidence.

No existing runtime/test/SQL/configuration or prior-phase artifact was modified. No staging, commit, push, Render deployment, paid provisioning or startup-safeguard change occurred. The owned localhost server, browser and temporary browser profile were cleaned up. Stop pending approval.

Offline preservation checks matched 22 prior source/test/dependency fingerprints, three SQL contract fingerprints and 75 recorded artifacts from Phases 2M–2Q. The owned server/debug ports were confirmed closed. See `verification-summary.json`; `verify_evidence.py` reproduces the offline checks without contacting a provider.
