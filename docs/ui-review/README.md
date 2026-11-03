# RosaGo global user UI integration

Implemented on the existing `dev` worktree without staging or committing. The entire supplied `RosaGo – Santa Rosa Smart TourismUI.html` was re-inspected, including its later CSS passes. Source SHA256: `b62d343d62e68c6620a4d117dfd11a121e250573ce95206adccda733c9887c5c`.

The earlier desktop header retained `flex-direction: column` from the legacy `.site-nav`. The Explore overrides changed other flex properties without resetting that direction. A remaining sidebar layout and conditional header structure also mixed two shells. The replacement uses one shared header everywhere: logo/search/profile/account utilities above a horizontal navigation row. `site.css` explicitly owns the row direction. The Explore stylesheet no longer defines the global shell.

The shared design follows the prototype's final brick/gold palette, warm paper background, compact white header, 1180px content area, rounded cards, subtle shadows, form controls, badges, tables, footer, and breakpoint behavior. Auth and normal pages import the same local token file. The prototype's embedded Santa Rosa arch photograph was extracted into a local asset for the dashboard and auth welcome panels. Font stacks retain the prototype families with system fallbacks; no new remote font dependency was added.

| Files changed during this integration | Purpose |
|---|---|
| `templates/base.html` | One global user shell, one header include, one main region; Explore CSS remains conditional. |
| `templates/partials/navbar.html` | Compact two-row header; existing routes, active states, account actions and authentication branches retained. |
| `templates/user/assistant.html` | Presentation classes for user/assistant message bubbles; existing message text, reference links and forms retained. |
| `static/css/design-tokens.css` (new) | Shared final prototype colors, type stacks, shadows and auth aliases. |
| `static/css/site.css` | Replaces the sidebar system with global components and layouts for all normal user pages. |
| `static/css/tourism.css` | Explore and place extensions; removes conflicting global header/shell rules. |
| `static/css/auth.css` | Uses shared tokens, arch welcome panel, consistent rounded controls/cards and responsive auth/legal layouts. |
| `static/img/santa-rosa-arch.jpg` (new) | Photograph extracted directly from the supplied prototype. |
| `tests/test_public_layout.py` | Updates shared-header expectations and safe synthetic fixtures. |
| `tests/test_final_ui.py` | Adds a cross-page contract for one header and the exact real navigation targets. |
| `tests/test_map_routes.py` | Gives the image-exclusion assertion a valid sentinel URL instead of `None`; the minimal map-payload assertion is preserved. |
| `docs/ui-review/` (new) | Offline screenshots, layout measurements, protected-file hashes, full worktree status and this report. |

Other templates already modified in the starting worktree were preserved. Their integration is through the shared stylesheet and shell; this task did not rewrite their route actions or business logic. The existing toolbar, footer, category artwork, weather partials and destination data bindings remain in use. No JavaScript was modified during this integration. The status entry for `static/js/map.js` predates this task and its starting hash is unchanged.

| Page family | Result |
|---|---|
| Dashboard/home | Arch photograph hero, readable overlay copy, quick actions, gold-accent information cards and destination/trip sections. Existing real-data and signed-out/empty states remain. |
| Explore | Shared compact header, 250px category rail, responsive card grid and category art. Published-only data, filters and Tourism Type/Category display remain. |
| Place details | Shared shell, split visual/details layout, readable Tourism and hours tables, weather information and existing conditional trip/map actions. Stacks on small screens. |
| Planner/itinerary | Matching planning-mode cards, progress indicators, choice controls, forms, destination rows and advisory/explanation/adjustment blocks. |
| Trips | Responsive trip cards, form controls, headings, destination rows and wrapping actions across list/new/add/detail/edit views. |
| Map | 340px list/control rail and flexible canvas on desktop; one column on small screens. Leaflet DOM hooks, hidden states, popup actions and routing JavaScript remain unchanged. |
| Transport | Shared headings, responsive cards, badges, forms and existing disclosures. No routes, fares or schedules added. |
| Assistant | Distinct chat bubbles within shared cards, message form and existing source links. Gemini/context/security behavior unchanged. |
| Alerts | Shared advisory and weather cards with existing request-driven checks and saved-trip reminders. |
| Settings/profile | Responsive account panels, field groups, labels, controls and actions. Existing read-only email and validation behavior remain. |
| Auth/legal | Shared palette/type/controls; photo welcome panel on auth pages; readable centered legal cards. Required indicators, verification controls and legal wording retained. |
| Errors/empty states | Shared heading, card, notice, button and footer styling inherited through the normal user shell. |

At 860px and below, major layouts stack and the utility row wraps. Main navigation and category filters scroll within their own rows. At phone widths cards and form choices stack and actions wrap. Keyboard focus, semantic form controls, skip link, hidden behavior and reduced-motion styling remain available. Admin has a separate stylesheet and shell and was not redesigned.

Browser evidence uses real Flask/Jinja rendering with offline service doubles and local catalog snapshots. No live account or database was accessed. Chrome DevTools emulation captured 11 pages at each of 1365×1000, 768×1024 and 390×844: dashboard, Explore, Enchanted Kingdom detail, Planner, trips, populated map, Settings, Login, Register, Terms and Privacy. All 33 measurements show the intended viewport width and no page-level horizontal overflow. Every normal user header measures 134px on desktop, has exactly one horizontal navigation row, and ends where main begins; main content has 24px top padding. Explore measures `250px 902px`, details `597px 543px`, and the map `340px 820px` on desktop; these become one column on smaller screens. See [raw layout measurements](layout-metrics.json).

Screenshots include [desktop dashboard](dashboard-1365.png), [desktop Explore](explore-1365.png), [desktop detail](detail-1365.png), [desktop Planner](planner-1365.png), [desktop Login](login-1365.png), [phone Explore](explore-390.png), [phone detail](detail-390.png), and [phone Settings](settings-390.png). All other screenshots follow the same page-width filename pattern. The map screenshots show the surrounding layout and safe interactive-map fallback: file-origin snapshots do not reproduce a live same-origin Leaflet session. Real tile loading, routing providers, authenticated data and external services require the live checklist below. They are not claimed as browser-verified here.

Focused verification passed:

- 232 route/template/auth tests: `test_public_layout`, `test_places_routes`, `test_final_ui`, `test_user_profile`, `test_trip_routes`, `test_map_routes`, `test_settings`, `test_ai_routes`, `test_alerts_routes`, `test_routing_routes`, `test_registration`, `test_password_reset`, `test_email_verification`, `test_callback`, `test_itinerary_quiz_routes`, `test_itinerary_preview_routes`, `test_itinerary_recommendations`.
- 75 additional preservation/layout checks: `test_final_ui`, `test_tourism_metadata`, `test_tourism_weather_identity`, `test_itinerary_weather`, `test_itinerary_adjustment`, `test_itinerary_selection_policy`, `test_recommendation_engine`. This group includes three layout checks also exercised in the 232-test run.
- `node tests/test_verification_frontend.js`: 3 passed, including resend deadline behavior.
- `node tests/map_routing.test.js`: 11 passed, including explicit routing, stale responses, geolocation consent, Leaflet fallback, coordinate validation, Google/Street View/Satellite actions and hostile-text handling.
- `git diff --check`: exit 0. Existing Git CRLF notices are informational. Git also reports an existing permission warning for `.pytest_cache`; no user files were altered to suppress it.

The final entire regression suite was not run. An initial map test exposed an invalid `None` image sentinel and was corrected as described above. An initial test command mistakenly named a JavaScript file as a Python module; the corrected Python and direct Node runs passed. The sandboxed Node test runner and browser needed alternative execution: direct Node worked; hidden isolated Chrome was automatically approved. Temporary browser profiles and rendered HTML fixtures were removed after capture.

Supabase records/schema were untouched. No SQL, migrations or Tourism transition scripts were executed or created. All 84 starting hashes covering root Python application/services, catalog data, migrations, JavaScript and admin templates match the starting worktree; see [protected-file evidence](protected-files.json). Ranking and selection policy are unchanged, Local/Common remains display metadata, and weather classifications/provenance remain unchanged. Auth, OTP, PKCE, CSRF, trip logic, Gemini and administrative authorization were not modified. No staging, commits, pushes, resets, restores or cleaning were performed. The complete `git status --short --branch` output is saved in [git-status.txt](git-status.txt); its many unrelated modifications and untracked files were already intentional work in progress.

Inspect the live application in this order, first around 1365px and then at tablet/phone widths. Existing backend behavior should remain the same throughout.

| Order | Page | Visual/interaction acceptance |
|---|---|---|
| 1 | Dashboard `/` | Compact two-row header; arch hero, quick actions, consistent cards, real signed-in trips where available. |
| 2 | Explore `/places` | Horizontal navigation, desktop category rail, destination grid; filters scroll on mobile and preserve real categories/data. |
| 3 | Enchanted Kingdom detail | Split artwork/details, Tourism/hours/weather tables and action buttons; single column on phone. |
| 4 | Kanin Club detail | Matching dining artwork/details; raw hours and null-coordinate map conditions remain truthful. |
| 5 | Planner | Paired planning-mode cards, matching primary/secondary actions; original start/manual actions work. |
| 6 | Preferences | Step indicator, consistent labeled controls and category choices; readable stacked fields. |
| 7 | Review | Shared heading/cards, summary rows, aligned edit/continue actions. |
| 8 | Recommendations | Destination rows, category chips and selection controls; original selection rules. |
| 9 | Preview | Day cards, stops, advisories, AI explanations, adjustment and weather-proposal forms/actions. |
| 10 | My Trips | Responsive trip cards, empty state; open new/add/detail/edit flows and check matching forms/actions. |
| 11 | Map `/map` | Desktop list/control rail plus Leaflet canvas; phone stacking; verify pins/popups, route controls, Google Maps, Street View and Satellite in a live session. |
| 12 | Transport | Matching cards, typography, controls and existing availability notices. |
| 13 | AI Assistant | User/assistant bubbles, source links and message form; configured Gemini submission works. |
| 14 | Alerts | Consistent weather/reminder cards; request-driven refresh and existing unavailable states. |
| 15 | Settings | Account/preferences panels, consistent selects, labels and save actions. |
| 16 | Profile `/user` | Matching account sections, name fields and read-only email/validation states. |
| 17 | Login/logout view | Photo welcome panel, clean form card and required indicators; account/logout controls align beside profile when available. |
| 18 | Register | Matching auth card, readable name/password fields, required markers, legal links and validation. |
| 19 | Verify Email | Matching auth layout; OTP input, resend timer and attempt interval retain real behavior. |
| 20 | Terms `/terms` | Readable centered legal card and existing legal text/navigation. |
| 21 | Privacy `/privacy` | Same legal typography, spacing and existing content. |

Also inspect Forgot Password, Reset Password and Verified during a safe real recovery/verification flow. Confirm their common styling without bypassing or manufacturing an auth state.

ROSAGO FULL SYSTEM UI: READY FOR LIVE VERIFICATION
