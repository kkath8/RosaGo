# RosaGo Budget / Dashboard / Weather UX

Verified 2026-11-01 (Asia/Manila) in the current dev worktree.

## Changes

- **Budget before:** A per-person expense calculator with a separate transport amount and optional per-person cap.
- **Budget after:** A total group budget, traveler count and immediate per-person allowance. Five editable suggested allocations (30/25/20/15/10), editable by percentage or PHP amount. Saving requires allocation amounts to match the total budget exactly. Integer-centavo arithmetic and deterministic rounding conserve the full total, including uneven-centavo budgets. Changing the total scales the current proportions.
- Optional named/category expenses subtract from the appropriate allocation. The summary shows total budget, planned expenses, remaining budget, per-person allowance and Within/Near/Over budget status. Near budget starts at 90% of the entered total; this is a planning signal, not a financial guarantee. Category overages are identified separately from overall over-budget status.
- No destination prices, transport fares, admission costs or other expenses are supplied or inferred. Suggested percentages are explicitly editable planning allocations, with the requested disclosure.
- Save budget plan retains the existing explicit-save approach in browser-local, user-scoped storage. Unsaved edits are labeled. The optional `budgetPlan` extension preserves the old `budget` data and old backups. Migration converts former per-person values to group amounts; unclassified old expenses go into Emergency / Extra, and transport stays Transportation. Original old calculator data remains intact. Unrelated local-state updates no longer reset an unsaved plan.
- The optional saved-trip selector uses existing read-only trip metadata, displays name/date, and never changes the itinerary. Direct account visits establish their verified browser-storage scope without relying on another tab; the response is private/no-store. Guest personal planning still works. No traveler count is inferred from unreliable metadata.
- **Dashboard before:** A large My Trips block with recent-created text links, a large weather panel, a Location card and another map panel.
- **Dashboard after:** A compact Upcoming Trips preview with at most three dated trips, ordered soonest first and excluding past/undated trips. A new bounded service read uses the existing owner/date projection and RLS architecture, with no schema changes. Names are plain headings with proper compact View Trip buttons. The empty state points to Planner. Destination counts are omitted because the existing metadata read does not supply a trustworthy count.
- Weather occupies the narrower side of the lower overview (approximately 35%, trips 65%). Mobile stacks trips before weather. Current condition, temperature, high/low and rain probability come from the existing weather API. View forecast leads to Alerts #weather. Dashboard source/licensing prose, the Location card and redundant map card are removed. Map & Transportation retains its existing location behavior.
- **Notifications:** Ordinary city weather is informational, not a source of weather notification cards or unread badges. The existing city weather detection still supplies one short practical advisory in the full Weather summary. Future saved trips with a concern from the existing `forecast_review` can generate a trip-weather notification linked to that trip. No forecast thresholds or classifications changed. An out-of-range future trip gets a neutral Forecast not available yet status with name/date and View Trip. No monitoring or push delivery is claimed. The prior Alerts missing-context JSON guard is preserved.

## Real application verification

The user signed in normally in the visible verification browser. Checks used the actual running Flask app on http://127.0.0.1:5000 with real account/trip/weather reads, without fixture service replacements.

**59 real browser checks passed**, no JavaScript exceptions:

- PHP 5,000 / 2 travelers -> PHP 2,500 per person.
- Default allocation amounts -> PHP 1,500 / 1,250 / 1,000 / 750 / 500, totaling PHP 5,000.
- Both percentage and amount edits update the paired controls. An unbalanced allocation blocks Save with an exact amount to adjust.
- Food expense PHP 600 -> Food remaining PHP 900.
- Food expense PHP 2,000 -> category overage PHP 500.
- Expense PHP 5,500 -> overall Over budget by PHP 500.
- An unrelated local-state update preserves the unsaved expense draft.
- Save and reload retain total, travelers, expense and selected real trip.
- Direct Budget entry after removing the previous sessionStorage scope still gets the verified account scope.
- Saved-trip metadata before/after was identical. All captured app requests were GET; no server mutation requests were sent.
- Both Light/Dark, at 1440px and 390px: Budget, Dashboard and Alerts render without horizontal page overflow. Audited text contrast passed. Existing logo/artwork/photographic overlays, disabled controls and translucent backgrounds are excluded from automated contrast checks; screenshots supplement the audit.
- Dashboard showed the actual two upcoming trips in visit-date order, with the maximum-three contract intact. View Trip opened an actual corresponding detail page with HTTP 200. View forecast reached the full Weather section.
- Alerts contains no ordinary city-weather notifications. The actual future out-of-range trip has neutral status. The bell matches unread, non-dismissed notification cards.

Original browser plan, read/dismiss state and theme were restored after temporary verification edits. The actual server and signed-in browser remain running. A late restart overlapped one sign-in; the final verification was performed after a fresh sign-in against the final code.

Empty-trip rendering, the maximum-three rule, invalid service rows, weather-provider timeout fallback and future in-range trip-weather notifications were tested through focused offline regression fixtures. No live trip records were deleted or changed to force those states. Live weather was available during browser verification.

Evidence: `live-results.json`, `budget-*.png`, `dashboard-*.png`, `alerts-*.png`.

## Tests

- Focused Python: **65 passed + 37 subtests passed**.
- After adding the private-cache assertion, the two Budget page tests passed again.
- Budget arithmetic JavaScript: **9 passed**.
- Personal-state JavaScript: existing and new migration, validation, scope, cached-state and persistence assertions passed.
- Theme JavaScript: **6 passed**.
- Syntax checks for budget-ui.js and user-ui.js passed.
- The full regression suite was not run.

```text
.venv/Scripts/python.exe -m pytest tests/test_budget_page.py tests/test_dashboard.py tests/test_dashboard_upcoming.py tests/test_public_layout.py tests/test_user_features.py tests/test_alerts_routes.py tests/test_alerts_presentation.py tests/test_alerts_live_regression.py tests/test_settings.py -q -p no:cacheprovider --tb=short
node tests/test_budget_plan.js
node tests/test_personal_state.js
node tests/test_theme.js
node --check static/js/budget-ui.js
node --check static/js/user-ui.js
.venv/Scripts/python.exe docs/budget-dashboard-weather/live_checks.py
git diff --check
git status --short --branch
```

## Files changed in this task

- `app.py`, `trip_service.py`, `user_features.py`: bounded upcoming-trip read, shared trip-weather presentation, Budget account scope/cache handling.
- `templates/index.html`, `templates/library/budget.html`, `templates/user/alerts.html`.
- New `static/css/budget-dashboard.css` and `static/js/budget-plan.js`, `static/js/budget-ui.js`.
- `static/js/personal-state.js`, `static/js/user-ui.js`.
- New `tests/test_budget_page.py`, `tests/test_budget_plan.js`, `tests/test_dashboard_upcoming.py`.
- Updated `tests/test_dashboard.py`, `tests/test_public_layout.py`, `tests/test_alerts_presentation.py`, `tests/test_personal_state.js`.
- Intentional verification scripts, results, screenshots and this report under `docs/budget-dashboard-weather/`.

## Preserved boundaries and git

No SQL, migrations, schema, destination catalog, Tourism metadata or trip-record changes. Recommendation ranking, Planner/itinerary adjustment, Gemini, authentication/OTP/recovery architecture, Profile model, Explore/Save/chooser, Map and Assistant scrolling were preserved. Existing auth helpers are reused for the Budget page; no authentication policy was altered.

`git diff --check` passed. Existing LF/CRLF conversion warnings remain. Branch `dev...origin/dev`; the whole existing worktree has 67 tracked modified files and 124 untracked entries, zero staged changes. No stage, commit or push. Full status: `git-status.txt`.
