# RosaGo Auth / Alerts / Explore UX verification

Completed 2026-11-01 (Asia/Manila), current `dev` worktree. Prior theme, Profile, Planner, itinerary, catalog, and Assistant work was preserved.

1. **Login movement:** Desktop auth shell is fixed to the viewport. The form column owns its vertical scrolling; the photo column cannot be stretched by form content. Hero copy is anchored to its bottom inset with CSS. No positioning JavaScript was added. Across 36 measurements (three auth pages, two themes, six states), headline movement was **0px**. States included empty, email, password, Show/Hide, long field errors and long login-status errors. The existing real Login submit validation was also exercised without sending credentials.
2. **Signup/Forgot:** Same independent-column layout and stable hero passed for Register and Forgot Password. Mobile remains stacked and passed no-overflow checks.
3. **Alerts:** One Notifications section and one Santa Rosa Weather section. Cards show notification kind, title, trip name/date where applicable, short copy, useful action and Dismiss. New cards have a badge and highlighted border/background; read cards use the normal surface. Duplicate weather signals on the same date are combined for display only. Existing detection rules remain unchanged.
4. **Open replacement:** View Trip uses the corresponding saved-trip detail URL. View Weather targets `/user/alerts#weather`. Both were clicked and their destinations verified in running Flask. Unknown/invalid destinations receive no action. Generic Open and primary Mark Unread actions were removed.
5. **Bell:** The bell links to Alerts. Counts include unread, non-dismissed notifications only. Browser checks verified opening a notification, Mark all as read, and dismissing an unread notification. Clear dismissed removes only dismissed entries from the loaded list and retains device suppression; active notifications remain. Zero unread hides the badge. Cross-tab storage synchronization remains, and cached pages reread device state on `pageshow` so back/forward cannot restore an older count.
6. **Weather:** Current temperature/condition, today's rain chance/high/low when returned, one advisory, and three forecast cards use existing WeatherSnapshot data. Useful future-trip weather cards use compact text. An out-of-range date shows the requested friendly message. Provider attribution/retrieval details appear in one collapsed About weather information disclosure. The unavailable state is explicit. Shared weather logic and thresholds are untouched.
7. **Explore sidebar:** Removed the aside and two-column filter/results layout. Controls precede full-width results.
8. **Search/filter:** Wide backend GET search, requested placeholder, compact category pills above the grid. Selected category stays brick/white; query state persists when switching categories. Real Flask public catalog search for CIBO narrowed to one destination, and clicking Dining retained the query and result. Existing weather/sort/Saved-only controls remain.
9. **Grid:** Browser-measured columns were 4 at 1440px, 3 at 1100px, 2 at 800px, and 1 at 390px. Cards have equal row height and bottom-aligned compact actions. Names remain the strongest text. Category, Tourism fields, address and excerpt are preserved. No page overflow was observed.
10. **Save:** Save/Unsave were clicked on the actual public Flask Explore page in both themes. Neither navigation nor scroll position changed. Existing Save behavior was retained.
11. **Add to Trip:** Remains directly on cards. The real chooser loaded selectable existing-trip options through running authenticated Flask QA routes in both themes. No trip was created or modified during verification.
12. **Light/Dark:** Login, Register, Forgot, Explore and Alerts were checked in both themes. Theme selection, navigation and explicit reload persistence passed. Existing theme CSS/JS were not duplicated or changed. Text contrast checks passed on the touched pages; the existing logo artwork is excluded, as are photo/illustration overlays, translucent backgrounds and disabled controls from the automated text audit. Screenshots supplement the audit.
13. **Browsers:** **148 checks passed** (93 core + 55 additional), with no JavaScript exceptions. Normal app.py ran on port 5000 for actual public auth/Explore/catalog checks. Authenticated Alerts/chooser used the actual Flask application routes and templates on loopback 5086 with established test auth/store/service fixtures, not pre-rendered static HTML. Its QA-only session route exists solely in `docs/auth-alerts-explore/flask_qa.py`; it was not added to production. The isolated server was stopped after verification. The normal server remains available on 127.0.0.1:5000.
14. **Tests:** **146 Python tests + 153 subtests passed**. Focused coverage includes auth, Alerts route/service/presentation, weather shapes, trip links, settings visibility, published backend search/category filtering, Explore Save markup, chooser and public layout. Theme JS (6), registration JS (9), recovery checks and personal-state assertions passed, including the new cached-page notice-state regression. JS syntax checks passed for user-ui.js and personal-state.js. Earlier test assertions for the superseded sidebar/Alerts sections and two stale Profile welcome-text assertions were updated without removing behavioral/auth security checks.
15. **Files changed in this task:**
    - `app.py`, `user_features.py`: presentation notification serialization shared by Alerts HTML and API.
    - `static/css/auth.css`, `static/css/tourism.css`, new `static/css/alerts.css`.
    - `static/js/user-ui.js`, `static/js/personal-state.js`.
    - `templates/places/list.html`, `templates/user/alerts.html`.
    - `tests/test_alerts_routes.py`, new `tests/test_alerts_presentation.py`, `tests/test_explore_save_ui.py`, `tests/test_settings.py`, `tests/test_login.py`, `tests/test_personal_state.js`.
    - Intentional scripts, JSON evidence, screenshots and this report under `docs/auth-alerts-explore/`.
16. **Limitations:** Headless Chrome cannot verify the browser-native saved-login autofill dropdown. Form content growth and viewport independence were measured, including deliberately oversized error text. Login-status errors used display-only samples, not real credential failures. Authenticated Alerts and chooser actions were verified using isolated test services; no real signed-in account was available. Weather screenshots contain clearly documented test-fixture dates/values, not a claim about today's forecast. Production rendering still uses the real existing Open-Meteo service and invents no values. The chooser was opened and selected, but its database-writing submit was intentionally not exercised.
17. **Database:** No SQL, Supabase schema, migration, record or catalog changes. No production database mutations were made. Existing unrelated migration files were preserved.
18. **Ranking:** Recommendation ranking, Planner/itinerary logic, Gemini architecture, weather thresholds/metadata, Tourism classifications, auth/OTP/recovery architecture and Profile model were unchanged.
19. **Git:** `git diff --check` passed. Branch `dev...origin/dev`; 67 tracked modified files and 117 untracked entries in the whole existing worktree, zero staged changes. No staging, commit or push. Full status is saved in `git-status.txt`. Existing LF/CRLF and inaccessible `.pytest_cache` warnings did not report whitespace errors.

Verification commands:

```text
.venv/Scripts/python.exe -m pytest tests/test_alerts_routes.py tests/test_alerts_presentation.py tests/test_alerts_service.py tests/test_user_features.py tests/test_explore_save_ui.py tests/test_interaction_polish.py tests/test_public_layout.py tests/test_places_routes.py tests/test_trip_chooser.py tests/test_settings.py tests/test_login.py tests/test_registration.py tests/test_password_reset.py -q -p no:cacheprovider --tb=short
node tests/test_theme.js
node tests/test_personal_state.js
node tests/test_registration_frontend.js
node tests/test_recovery_frontend.js
node --check static/js/user-ui.js
node --check static/js/personal-state.js
.venv/Scripts/python.exe docs/auth-alerts-explore/browser_checks.py
.venv/Scripts/python.exe docs/auth-alerts-explore/extra_checks.py
git diff --check
git status --short --branch
```
