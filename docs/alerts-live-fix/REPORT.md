# RosaGo Alerts live 500 fix

Verified against the REAL signed-in app at http://127.0.0.1:5000 on 2026-11-01 (Asia/Manila).

1. **Root cause:** A still-running controller used the pre-redesign template context, which omitted `notifications`. Jinja auto-reloaded the newer Alerts template, which unconditionally serialized that missing value. The Python process was older than the controller/presenter source update. The previous isolated checks loaded fresh application code, so they missed this mixed-version runtime. This was not a Supabase trip/date shape failure.
2. **Exact exception:** `TypeError: Object of type Undefined is not JSON serializable`. This was confirmed by the user's live Flask traceback and independently reproduced using the actual development configuration with the old controller context.
3. **Location:** Originally `templates/user/alerts.html:10`, `{{ notifications | tojson }}`; called from `app.py:1686` via `_render_trip_page` at `app.py:820`. The missing value was a Jinja Undefined, not a JSON-native list.
4. **Fix:** Normalize missing/null notification context to an empty list once, then use that same list for both bootstrap JSON and server-rendered cards. The existing current controller still supplies the real notification list. Restarted the stale Flask server using the current dev configuration. Also validated presentation notification dates/kinds and trip destinations: one malformed notification is skipped; an invalid/unavailable trip destination receives no button. No broad exception suppression was added. The simplified Alerts design is preserved.
5. **Regression:** `tests/test_alerts_live_regression.py` removes `notifications` immediately before actual route template rendering, reproducing the exact live mismatch. It now asserts HTTP 200 and valid `[]` JSON. Additional coverage: null/empty payload, one malformed notification alongside valid rows, absent optional action, invalid trip ID, real WeatherService timeout boundary, no trips and undated-trip reminder behavior. Existing future-out-of-range coverage also passes.
6. **REAL HTTP status:** Actual signed-in `/user/alerts`: **200**, repeatedly, including explicit reloads in both themes. The real notices API also returned 200. Final independent response inspection confirmed two real bootstrap rows (weather + saved trip), the friendly outside-forecast message, and collapsed provider details. No auth, weather or trip mocks were used for these live checks. The user signed in normally in a separate visible Chrome session; no credentials were read or recorded.
7. **View Trip:** Clicked the real saved-trip notification, opened its corresponding saved trip detail route, and confirmed HTTP 200. No trip was modified.
8. **View Weather:** Clicked the real weather notification. It reached the Weather section on the same Alerts page and updated the unread count.
9. **Dismiss:** Dismissed one actual unread notification; exactly one card disappeared. Mark all as read also worked. Browser-local state was restored afterward.
10. **Bell:** Count matched actual unread/non-dismissed cards; opening, dismissing and marking all read updated it correctly. Zero unread hid the badge. Original browser read/dismiss state and theme were restored in a finally block.
11. **Weather failure:** The existing WeatherService converts provider timeout into no snapshot. The added regression verifies Alerts remains HTTP 200, shows `Weather information is temporarily unavailable.`, and retains the trip reminder. Live weather was available during verification; the provider was not deliberately disabled in the real application. Thresholds and weather metadata are unchanged.
12. **Tests:** 30 focused Python tests + 18 subtests passed. Theme JavaScript tests and personal-state/unread-state assertions passed. **27 actual signed-in browser checks passed**, with no JavaScript exceptions, plus a final live-response inspection. Screenshots cover Light/Dark at 1440px and 390px. The real existing future trip outside the forecast range displays the short friendly message. See `python-tests.txt`, `theme-tests.txt`, `state-tests.txt`, `live-results.json`, `final-live-response.json` and `real-alerts-*.png`.
13. **Files changed in this fix:** `templates/user/alerts.html`, `user_features.py`, new `tests/test_alerts_live_regression.py`, and intentional reproduction/live-verification artifacts under `docs/alerts-live-fix/`. Existing auth, theme, Explore, Profile, Planner and other worktree changes were preserved. `reproduce_context.py` documents the old-context condition; it renders successfully after the fix.
14. **Database:** Unchanged. No SQL, Supabase schema, migration, destination/trip-record mutations, weather metadata, ranking, Gemini or authentication changes. Live requests used existing read routes. Only temporary browser-local read/dismiss/theme state was changed and restored.
15. **Whitespace:** `git diff --check` passed, exit 0. Existing LF/CRLF warnings remain unrelated to whitespace errors.
16. **Git:** `dev...origin/dev`; 67 tracked modified files, 118 untracked entries in the whole existing worktree, zero staged. No stage, commit or push. Full output is saved in `git-status.txt`.

The actual Flask server and signed-in verification browser remain open for review.

Commands:

```text
.venv/Scripts/python.exe docs/alerts-live-fix/reproduce_context.py
.venv/Scripts/python.exe -m pytest tests/test_alerts_live_regression.py tests/test_alerts_routes.py tests/test_alerts_service.py tests/test_alerts_presentation.py tests/test_settings.py -q -p no:cacheprovider --tb=short
node tests/test_theme.js
node tests/test_personal_state.js
.venv/Scripts/python.exe docs/alerts-live-fix/live_checks.py
git diff --check
git status --short --branch
```
