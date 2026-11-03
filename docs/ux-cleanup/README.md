# RosaGo final UX cleanup

Continued from the completed prototype port on the existing dirty `dev` worktree. This is a targeted presentation/navigation cleanup, not a replacement application.

## Changes

| Area | Result |
|---|---|
| Events | Removed from desktop navigation, mobile More, footer, settings and alert generation. `/events` now redirects to Dashboard. Legacy browser-state fields remain compatible with existing backups but are not displayed or counted as notices. |
| Header | Removed the large global search and its client suggestion controller. Explore retains its own real destination search. Removed separate profile/logout controls; account actions are grouped in Account. Trip Bag and bell are compact icon controls. |
| Navigation | Core desktop links include Explore, Planner, My Trips, **Map & Transport**, and AI Assistant. Budget is secondary in Library with Saved/Visited. Mobile tabs expose Explore, Plan, Trips, Map, AI and More; the wordmark opens Dashboard. |
| Consolidation | `/map` is **Map & Transportation**. The old authenticated `/user/transport` endpoint remains and redirects to `/map`; its existing auth protection remains. No separate Transport navigation item or duplicated page is presented. |
| Map layout | Approximately 67% map / 33% side panel on desktop; map minimum height 660px. At tablet/mobile widths the map comes first, then controls; map heights are 520px/400px. Destination directory is expandable. |
| Side panel | Destination, Transportation Mode and Starting Point are grouped with dividers. Location/map selection are prominent. Latitude/longitude are inside **Enter coordinates manually**. Existing request validation, location permission handling and stale-request cancellation remain. |
| Modes | Live configuration exposes **Driving only (OSRM)**. The existing implementation also exposes Walking/Cycling when a configured ORS provider supports them; this task did not enable or change providers. Motorcycle/public transit, fares, schedules and live traffic are not invented. A public-transport information section points to Google Maps. |
| Results | Dedicated Route Summary shows destination, mode, provider-returned distance and estimated duration, plus Google Maps. Friendly Route unavailable cards replace technical failure presentation. No fallback straight-line route is generated. |
| Popups | Prominent destination name and application category/known Tourism Type; compact View Details and Plan Route actions; grouped Google Maps, Street View and Satellite links. Existing URL encoding, coordinate validation and external-link protections remain. |
| Trip Bag | Separated compact destination rows with category/type/address, View and Remove. Clear Bag is secondary and asks for confirmation when needed; Save as Trip is primary. Close is a small labelled X. Existing real authenticated save flow and browser selection state are preserved. |
| Assistant | Left cream assistant bubbles, right brick user bubbles, bounded conversation area and bottom composer with compact Send. Clear Conversation is secondary; sources are expandable. No fabricated timestamps. Actual Gemini, conversation/context, errors, CSRF and clear handlers remain unchanged. |
| Typography/titles | Inter is loaded from Google Fonts and used by the user interface, forms, headings, chat, map and auth. Sora remains for the wordmark. Destination names are bold dark titles, not ordinary underlined links. |
| Labels/buttons | Compact primary/secondary/tertiary hierarchy; fewer competing controls. Map wording is consistent. Removed visible revision/ranking implementation wording while retaining hidden revision/security fields. |
| Landmark | Dashboard uses exactly: “The Santa Rosa Arch is one of the city's recognizable landmarks and serves as a symbolic gateway to Santa Rosa, reflecting the city's identity as the Lion City of the South.” No City Tourism destination descriptions were edited. |

## Verification

- **TEST VERIFIED:** [231 focused Python tests passed](focused-tests.json), zero failures/errors. Coverage includes map/routes, provider handling, search, trips/bag, Assistant, settings/profile, auth/password policy and itinerary flows. The full suite was not rerun. [Detailed output](focused-tests.txt).
- **TEST VERIFIED:** All six runnable JavaScript test files passed: **40 runner-counted cases** plus standalone recovery and personal-state assertions. Three new routing tests cover the dedicated summary, safe failure card and missing starting-point handling. [Output](javascript-tests.txt).
- **BROWSER VERIFIED, ISOLATED FIXTURES:** **24 interaction checks, 16 captures, zero uncaught JavaScript errors and no horizontal overflow** at 1440px, 768px and 390px. Checks include one/multiple-place bags, remove/clear/cancel/save, Saved/Visited, destination and map-point selection, popup links, success/failure summaries, chat send/response/clear, Events removal including old reminder state, settings and mobile More. [Results](browser-results.json), [screenshots](screenshots/).
- **LIVE VERIFIED:** Current public Dashboard/map/login render with Inter at desktop/mobile sizes. The real map displays **19 published coordinate-backed markers** and structured popups. Configured routing modes contain only Driving. `/events` redirects to Dashboard. No Events links, page overflow or uncaught JS exceptions in the live captures. [Live browser results](live-browser.json).
- **LIMITED BY PROVIDER/DATA:** The real OSRM request timed out. RosaGo displayed Route unavailable and a valid Google Maps destination fallback; it did not draw fabricated geometry or display raw HTTP/provider codes. Successful summary/geometry behavior was verified with explicit isolated test-provider responses, not represented as live routing success.
- **LIVE VERIFICATION PENDING:** Real-account trip writes and cloud Gemini send/clear were not exercised. The browser fixture uses the actual Flask POST/redirect/conversation flows with isolated service doubles and fake test identities. It cannot modify real Supabase records. Production Gemini and trip services were not replaced with mocks or browser storage.

The development server was refreshed to load the cleanup. In-memory sessions/recovery state from the old process require a fresh login or link. The normal application remains on `http://127.0.0.1:5000/`. The separate loopback fixture server is an audit tool, not an application authentication mechanism.

## Files and preservation

[files-and-preservation.json](files-and-preservation.json) lists the **31 modified existing application/test files** (including seven test files) and the new production stylesheet `static/css/ux-cleanup.css`. Main groups:

- `app.py`, `user_features.py`: Transport/Events redirects and existing public Tourism Type in marker presentation.
- Shared fonts, navbar/navigation/mobile/footer, route controls and settings/Smart Options partials.
- Map, Assistant, Dashboard, Explore/detail, library copy, itinerary review/preview and privacy templates.
- `design-tokens.css`, `site.css`, new `ux-cleanup.css`, `map.js`, `user-ui.js`.
- Focused map/routing/navigation/feature tests and this audit folder.

**72 protected files match their pre-cleanup hashes**, including catalog data, coordinates/metadata, migrations, recommendation/selection algorithms, authentication/password internals and provider/service implementations. No SQL was executed; no schema, records, publication states, classifications, coordinates, migrations or recommendation ranking were changed. Existing real search, Add to Trip continuation, trips, planner, AI/weather actions, Leaflet and external map actions remain.

`git diff --check`, staging verification and the exact `git status --short --branch` output are recorded in [git-verification.json](git-verification.json), [diff-check.txt](diff-check.txt) and [git-status.txt](git-status.txt). Nothing was staged, committed or pushed; earlier intentional worktree changes remain.
