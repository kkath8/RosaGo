# RosaGo final functional completion audit

Completed on the existing `dev` branch without staging, committing, pushing, resetting, restoring or discarding unrelated work. The pre-change [audit list](initial-audit.md) and [complete static control inventory](initial-controls.json) were recorded before implementation changes. The inventory includes conditional controls and Jinja macros; map-generated controls were additionally inspected and exercised through JavaScript tests.

The audit found and resolved these user-facing issues:

- Global search was disabled and labeled Coming Soon. It is now a real native GET form submitting to `/places?q=...`.
- The local Tourism metadata rollout flag was disabled. A read-only query confirmed the existing columns and populated records before enabling `ROSAGO_TOURISM_METADATA_ENABLED=true` in local `.env`. No schema or record changes were needed. Other configuration values were retained. Restart the development app to load the current code and this flag if an older process is still running.
- Signed-out Add to Trip lost its destination after login. The existing protected route now supplies a slug-only login continuation. The login form retains that hint on validation/provider failure and successful login returns to the real chooser. The destination is re-read through the published-only service before adding; trip ownership and CSRF checks remain unchanged. Arbitrary URLs, duplicate hints and malformed slugs cannot become redirect targets. Existing ordinary login behavior remains unchanged.
- Public detail actions explicitly say `Add to Trip (sign-in required)`. Public pages continue to avoid authentication lookup/mutation; a cookie hint never grants authority.
- Open Map discarded the selected destination. It now uses the existing validated `destination` parameter, and the JavaScript preselects only a destination actually present in the published marker list.
- Unsupported Remember me and manual-trip Organize / Preview controls were removed. Future organization promises were replaced with an accurate description of saving destinations in add order. No unsupported remove/reorder/scheduling feature was added.
- The existing recommendation-selection flow had no entry from Review. A real Choose Recommended Destinations link now exposes the existing flow without changing automatic generation, ranking or selection policy. A route integration test follows Review ? Recommendations ? Selection ? stored Preview.
- The redundant public-header Your account link was removed; the existing profile link and navigation remain.

Search implementation is deliberately small: `place_search.py` reuses `PlacesService.list_published`, paging through all published results in stable slug order. Name, application category/label, address, description, Tourism Type and Tourism Category are searched using Unicode case-insensitive literal partial matching. Every whitespace-separated query word must match the combined visitor fields. Search text is never passed to SQL or a PostgREST expression. The existing service owns publication/category filtering and RLS remains in force. Queries are limited to 200 characters; duplicate query parameters and control characters receive a safe 400 response. Results and query echoes are escaped, empty results provide a clear recovery action, and category links retain the query. No Gemini, extra search provider, migration or database index was added. Search scans the full catalog; unfiltered Explore retains its existing 50-record window, which currently contains all 34 published records.

Changed implementation files: `app.py`, `auth_helpers.py`, new `place_search.py`, `templates/partials/toolbar.html`, `templates/partials/navbar.html`, `templates/auth/login.html`, `templates/places/list.html`, `templates/places/detail.html`, `templates/trips/new.html`, `templates/trips/detail.html`, `templates/user/planner.html`, `templates/itinerary/review.html`, and the small functional search/control rules in `static/css/site.css`. No optional redesign was undertaken. Application JavaScript was not modified.

New behavior coverage is in `tests/test_functional_completion.py`: real publication-filtered search with an offline transport double, all requested fields, combined categories, beyond-first-page results, hostile/repeated/oversized queries, no-result/error handling, repeated-page rejection, restricted login continuation, failed login and the complete signed-out login → chooser → protected add → detail HTTP flow with external auth/storage doubles. Existing layout/route expectations were updated for the now-functional search and clarified actions without removing their security assertions.

Two test assumptions were found during regression: the itinerary selection test selected the first page submit button, which is now the header Search action; it now targets its actual itinerary form. The legacy map harness lacked the browser's `URLSearchParams` and still expected the earlier popup text, 50-marker cap and absence of any routing/geolocation code. Its browser fixture and expectations were updated to the existing implemented features. Runtime guards still forbid unsolicited network/location/storage activity. Injection, credentials, payload/coordinate validation, popup safety and failure behavior remain tested. A regression now verifies maps over 50 markers. The routing suite adds destination-link preselection and rejection of unknown/external destination hints. No application map behavior was changed to satisfy these tests.

Verification results:

- Focused changed-subsystem run: 104 tests passed.
- Broad user-facing regression: **824 tests passed**, 62 Python modules, no failures/errors/skips. Auth adapters/coordinators/store, OTP, recovery/PKCE, profile, trips, draft lifecycle, generation, recommendations, selection, preview, explanation, conversational adjustment, weather/proposals, assistant, alerts, routing and data contracts are covered. Admin modules were excluded because admin was outside this task. Migration/transition contract tests inspect or generate text; no SQL was executed. See [Python summary](python-results.json) and [test log](python-results.txt).
- JavaScript: **28 Node tests passed** (3 verification + 12 routing + 13 map), plus the recovery frontend assertion script passed. See [JavaScript results](javascript-results.json).
- `git diff --check` passed. Existing CRLF notices and the `.pytest_cache` permission warning are Git/environment messages, not ignored test failures.
- Fresh-process live public-route checks used the actual local configuration and real read-only public Supabase catalog. Dashboard, Explore, Enchanted Kingdom/Kanin Club details, Map, auth/legal forms and Leaflet assets loaded; private routes redirected to login; Reset Password without a recovery grant returned the expected safe 403. No traceback was exposed.
- Live search: Japanese **2** results, Kanin **1** (Kanin Club), heritage **9**, Local **8**, and the deliberately unmatched query **0** with a recovery state. These are observed live results, not hardcoded application data.
- Live Open-Meteo returned validated weather with three forecast days. Gemini returned a validated chat reply. Live shortlist explanations, per-destination preview explanations and the requested two-heritage-place adjustment all passed schema/intent validation. Outcomes are recorded in [live-results.json](live-results.json).
- Live OSRM returned the handled `no_route`/422 response for sampled existing catalog coordinates, including Enchanted Kingdom → SM City Santa Rosa through the real `/api/route` endpoint. No successful live route geometry is claimed, no coordinates were altered, and no fallback straight line is fabricated. Successful provider geometry, stale responses, consent, failures and rendering are covered offline. Leaflet assets served successfully; a live browser tile/popup/navigation session remains manual.

Live provider checks use only public destination information or a generic audit question. No live login, registration, OTP email, recovery email, profile edit or trip/draft mutation was performed. Those flows were exercised offline through real Flask routes/adapters with isolated external-service doubles. No credentials, raw provider responses or API keys are included in the report. This distinction is reflected in the feature statuses below: a passing isolated test alone is not labeled full live end-to-end verification.

| Feature | Status | What was tested | Remaining limitation |
|---|---|---|---|
| Global Search | WORKING | Live published catalog/name/category/Tourism examples; offline address/description, pagination, input safety and category composition | Local metadata flag must be loaded by the running app; literal keyword search, no semantic search. |
| Dashboard | WORKING WITH DOCUMENTED LIMITATION | Live public render/catalog; offline signed-in trip states/actions/auth guards | Signed-in live trip data not exercised. |
| Explore | WORKING | Live public catalog/details/search; offline category visibility, metadata and safe links | Existing unfiltered 50-record window; current published catalog is 34. |
| Place Details | WORKING | Live EK/Kanin details; offline metadata/hours/coordinates/XSS/action conditions | Hours retain existing verification caveats; no new destination facts inferred. |
| Add to Trip | WORKING WITH DOCUMENTED LIMITATION | Offline signed-out login → chooser → add → detail; owner/CSRF/UUID/unpublished checks | Live authenticated trip write not performed. If no trip exists, create one and return to the place as instructed. |
| Planner | WORKING WITH DOCUMENTED LIMITATION | Offline start → preferences → review; validation, revision, auth, expiry | Live draft writes not performed. |
| Recommendations | WORKING WITH DOCUMENTED LIMITATION | Real deterministic engine/selector in route tests; matched selection/zero matches | Live authenticated draft/catalog flow still manual; category-interest ranking only. |
| Preview | WORKING WITH DOCUMENTED LIMITATION | Offline generation/selection → stored preview/read/edit and lifecycle checks | Temporary preview does not create a saved trip; no exact scheduling. |
| AI Explanation | WORKING WITH DOCUMENTED LIMITATION | Offline request/schema/security/response rendering; live outcomes in live-results.json | Authenticated persisted-preview explanation still manual. |
| Conversational Adjustment | WORKING WITH DOCUMENTED LIMITATION | Offline supported changes, stale revision, malicious output, atomic write; live parser outcome recorded | Live draft mutation not performed; only supported category/count/pace changes. |
| Weather Advisory | WORKING WITH DOCUMENTED LIMITATION | Live Open-Meteo; offline horizon, freshness, failure and route rendering | City-level, request-driven, three forecast days; no continuous monitoring. |
| Weather Proposal | WORKING WITH DOCUMENTED LIMITATION | Offline applicability, trusted metadata, proposal binding, Keep Current/Use Suggested, atomicity | Appears only when applicable; no live trip/draft mutation or forced bad-weather state. |
| My Trips | WORKING WITH DOCUMENTED LIMITATION | Offline list/create/view/edit/add/delete/ownership/pagination/error paths | Live writes not performed; no individual destination remove/reorder feature advertised. |
| Map | WORKING WITH DOCUMENTED LIMITATION | Live map page/local Leaflet assets; offline markers, popups, destination selection, external links/fallbacks | Live browser tiles/location/Google coverage not verified. |
| Routing | WORKING WITH DOCUMENTED LIMITATION | Live no-route/422; offline successful geometry/API errors/stale requests/consent/coordinate bounds | Sample catalog pairs produced no route; successful live geometry unverified. |
| Transport | WORKING WITH DOCUMENTED LIMITATION | Offline real map/routing wrapper, supported modes and disclosures; live auth guard | Same routing/provider limits; no public-transit schedules/fares/bookings. |
| AI Assistant | WORKING WITH DOCUMENTED LIMITATION | Live validated Gemini chat; offline auth/context/send/clear/empty/error/XSS/security | Authenticated browser conversation still manual; process-memory history. |
| Alerts | WORKING WITH DOCUMENTED LIMITATION | Offline saved-trip reminders/preferences/weather/error handling; live weather/auth guard | Live private reminders not queried; no push/SMS/background monitoring. |
| Settings | WORKING WITH DOCUMENTED LIMITATION | Offline POST/validation/CSRF/session preference affecting Alerts; live auth guard | Authenticated browser save still manual; session-only preference is intentional. |
| Profile | WORKING WITH DOCUMENTED LIMITATION | Offline first/last-name save/validation/read-only email/error/security paths | Live profile write not performed. |
| Registration | WORKING WITH DOCUMENTED LIMITATION | Offline form, validation, provider request, throttling and pending state; live form GET | No live account created or email sent. |
| Email OTP Verification | WORKING WITH DOCUMENTED LIMITATION | Offline verify/resend/expiry/cooldown/rate-limit/CSRF; JavaScript timer; live GET | Actual inbox delivery and real OTP not exercised. |
| Login | WORKING WITH DOCUMENTED LIMITATION | Offline SDK/verified identity/session/continuation/logout/guards; live form/guard GET | No real credentials used. |
| Forgot Password | WORKING WITH DOCUMENTED LIMITATION | Offline recovery request, anti-enumeration, provider/rate errors; live form GET | Actual recovery-email delivery not exercised. |
| Password Reset | WORKING WITH DOCUMENTED LIMITATION | Offline PKCE callback/claims/grants/CSRF/one-use reset; live invalid-grant rejection | Real email callback and password mutation not performed. |
| Terms | WORKING | Live GET and offline legal/auth/back-link contracts | Existing legal content retained. |
| Privacy | WORKING | Live GET and offline legal/auth/back-link contracts | Existing legal content retained. |

The unsupported UI controls above were removed rather than presented as functioning features. Disabled buttons that remain in normal templates are real safety states: OTP cooldown, in-flight submissions, or unavailable Gemini configuration. Input placeholder hints are legitimate guidance. Admin-only integration placeholders remain outside this user-facing task and were not changed.

Supabase/schema status: read-only public catalog queries only; no records, UUIDs, slugs, statuses, coordinates, Tourism types or weather classifications changed. No SQL/migrations/transition scripts were executed or created. Starting-file hashes show that of 84 checked root Python/data/migration/JS/admin files, only the intentionally modified `app.py` and `auth_helpers.py` changed; `place_search.py` is the new helper. The other 82 match, including recommendation ranking/selection, weather metadata, trip services, auth internals and application JavaScript. See [protected-file evidence](protected-files.json). Admin CSS/templates were not edited. Full [git status --short --branch](git-status.txt) is preserved without discarding the substantial existing worktree.

Shortest live sequence after restarting/reloading the development app:

1. Signed out: search Japanese, Kanin, heritage, Local and one nonsense term; change/clear a category and open EK/Kanin details.
2. Use Add to Trip, log in, confirm return to the chooser, create a trip if needed, then add the destination and open its detail.
3. Planner → Preferences → Review → Generate → Preview; use Choose Recommended Destinations from Review to exercise Recommendations ? Selection ? Preview.
4. Request an AI explanation, then ask for two heritage places and confirm the preview updates.
5. Check weather advice; if a real proposal is offered, test Keep Current and then Use Suggested on an applicable proposal.
6. My Trips: create/edit/view; add another destination; use a disposable trip to verify deletion.
7. Open a detail's Map action; inspect its marker and route selection, request a route, test Google/Street View/Satellite links and a safe route-failure state. Open Transport's routing controls too.
8. AI Assistant: send a relevant message, verify sources/reply, reject empty input, clear history.
9. Alerts → Settings: change display preference, return to Alerts; Profile: edit names and confirm email remains read-only.
10. Log out → Register with a test inbox → real OTP/resend → verified → Login; open Terms/Privacy from registration.
11. Forgot Password → real recovery email/callback → Reset Password → Login with the new password.

Do not fabricate a weather event, bypass an OTP/recovery grant, or alter coordinates to make a manual check appear successful.

ROSAGO FUNCTIONAL COMPLETION: READY FOR LIVE VERIFICATION
