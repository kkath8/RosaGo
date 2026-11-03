# RosaGo final test baseline

Completed 3 November 2026, Asia/Manila. Scope: the seven stale expectations and
two fixture issues identified in [the final review](../final-review/REPORT.md).

**CLEAN: 1,003 Python tests passed, 0 failures, 0 errors. All nine JavaScript test
files passed. Production code changed: NONE. Database unchanged; 0012/0013 unapplied.**

## 1. Original baseline and correction scope

Original verified baseline: **994 passed / 7 failed / 2 errors**, 1,003 total.
The current full suite still contains 1,003 tests. None was removed or skipped to
obtain this result. Two obsolete Tourism test names were updated to describe their
corrected contracts; their coverage remains in the suite.

Before editing, the nine review findings were checked against current production
routes/templates, the approved policy versions, and existing current behavior
tests. Corrections were limited to nine test methods across these six files:

- `tests/test_login_dashboard_redirect.py`
- `tests/test_map_routes.py`
- `tests/test_final_ui.py`
- `tests/test_functional_completion.py`
- `tests/test_trip_routes.py`
- `tests/test_tourism_transition.py`

The exact task-only diff, including originally untracked tests, is saved in
[test-corrections.diff](test-corrections.diff). The pre-task test source and file
hashes are also retained as review evidence. Existing unrelated worktree edits
were preserved.

## 2. Seven stale tests corrected

### 1. Alerts unavailable/empty presentation

Test: `test_final_ui.FinalUiTests.test_planning_modes_use_existing_actions_and_unsupported_controls_are_removed`.

Old expectation: the old unavailable-weather phrase and saved-trip reminder-window
copy appeared in Alerts HTML. The current Alerts screen uses a Notifications list
and a separate weather section, as confirmed by the final review and template.

Correction: assert the unavailable message inside the actual weather section, an
empty JSON notification payload, and the meaningful “No notifications right now.”
empty state. Existing Planner/manual-trip forms, CSRF and no-unexpected-service-call
checks remain. No fake notifications or weather values were added.

### 2. Recommendations submit directly to Preview

Test: `test_functional_completion.PlannerSelectionFlowTests.test_review_reaches_recommendations_selection_and_persisted_preview`.

Old expectation: Recommendations must submit to a separate Selection page before
Preview. The approved current screen instead selects destinations in the
recommendations form and posts directly to `itinerary_preview_build` at `/preview`.
The existing personalized-recommendations UI tests explicitly assert this contract.

Correction: inspect the actual named recommendations form, POST target and exact
CSRF/revision fields, then drive that direct Preview POST. Retain successful
redirect, one persistence call, `preview_ready` state, selected destination IDs and
rendered Preview assertions. Also verify revision advances to 3 and a refresh does
not persist another preview. The old Selection route was not changed or removed.

### 3. Hostile Map payload and current shared scripts

Test: `test_map_routes.MapRouteTests.test_hostile_marker_text_cannot_break_json_or_create_markup`.

Old expectation: exactly five scripts. The current shared User shell intentionally
adds the theme and account-management scripts, producing seven scripts for this
populated Map.

Correction: assert the exact approved external script identities and one JSON map
bootstrap rather than the outdated count. Preserve hostile name/address round-trip,
no injected image, no literal `<` in the JSON bootstrap, escaped HTML, and readable
destination-list checks. Extra injected scripts still fail the exact allowlist.

### 4. Map layout and theme asset expectations

Test: `test_map_routes.MapRouteTests.test_shared_layout_conditional_local_assets_and_active_map`.

Old expectation: the pre-theme stylesheet list and old script order/count.

Correction: include the approved shared theme stylesheet and current script
identities. Assert the theme executes before paint, other executable scripts are
deferred, and the single map JSON element has its expected attributes. Conditional
Leaflet loading, empty-map behavior, focus/navigation, active state, routing form,
referrer policy, no inline handlers/unsafe URLs and private-data exclusions remain.

### 5. Inherited Profile navigation

Test: `test_trip_routes.TripRouteTests.test_reads_forms_account_link_and_unavailable_place`.

Old expectation: the literal “My Trips” must exist in the child Profile template's
source. Profile now inherits that link from shared navigation.

Correction: GET the real Profile route with an isolated own-profile read double,
then assert a rendered “My Trips” link targets `/user/trips`. Its no-store behavior
is checked. The existing trip/read/edit/unavailable-place/privacy assertions remain;
no source text is inserted into the production template to satisfy the old test.

### 6. Historical transition hashes versus current policy contracts

Old test:
`test_tourism_transition.TourismTransitionTests.test_protected_weather_ranking_selection_and_0011_files_unchanged`.

Current name:
`test_protected_transition_data_unchanged_and_current_policy_versions`.

Old expectation: recommendation/selection source must forever match the hashes
captured before the approved Tourism/geographic policy changes. The review showed
that the data/migration baselines still match, while those policy files intentionally
evolved to the versions documented by the Admin audit.

Correction: retain the original checksum assertions for immutable transition data
and 0011, including the existing documented weather identity reconciliation rule.
Explicitly account for all four protected paths so no unknown baseline entry is
silently ignored. Check the approved current ranking and selection policy versions
instead of replacing historical source hashes with today's digests. The original
transition plan, original hashes, metadata file and migration were not edited.
Current behavior is verified by the corrected policy test below and existing
recommendation/geography suites.

### 7. Tourism Type affects priority, not category eligibility or score

Old test:
`test_tourism_transition.TourismTransitionTests.test_recommendation_scores_and_selection_do_not_read_tourism_type`.

Current name:
`test_tourism_priority_preserves_category_scores_and_eligibility`.

Old expectation: adding Tourism metadata cannot affect the entire ranking result
or selection. That conflicts with the approved Local → unclassified → Common policy.

Correction: verify category eligibility, category scores and matched signals stay
unchanged while Tourism priority follows the approved three-tier order. Check
deterministic UUID tie ordering, category variety and Common-category retention.
An in-memory unclassified fixture explicitly verifies the NULL tier and a
single-stop selection preferring Local. It remains NULL after the operation.
No catalog record, metadata or coordinates were written.

## 3. Two fixture/environment corrections

### Login-to-Dashboard fixture

Test:
`test_login_dashboard_redirect.DashboardLoginRedirectTests.test_normal_login_lands_on_existing_authenticated_dashboard_and_profile_remains`.

Cause: the login fixture isolates external storage and uses a simplified client
and synthetic identity. It mocked `list_user_trips`, but the Dashboard now calls
`list_dashboard_upcoming_trips`, reaching an unsupported real trip-service contract.

Correction: double the exact current dashboard reader locally and assert it is
called once. Keep real login/session handling, redirect to `/`, Dashboard rendering,
authenticated status and retained Profile access. No authentication or trip-service
contract was weakened; no exception was caught to hide an invalid fixture.

### Direct Map rendering context

Test:
`test_map_routes.MapRouteTests.test_shared_template_autoescaping_remains_enabled`.

Cause: calling Jinja `template.render` directly bypassed Flask context processors,
omitting the shared `website_settings` required by the User shell.

Correction: use Flask `render_template_string` inside the existing request context
for the inherited title test. Shared context now comes from the same pipeline as
normal Flask rendering. The hostile-title autoescaping and shared-script assertions
remain; production templates were not given fallback values to mask the fixture.

## 4. Production code changes

**NONE**, including no testability-only production adjustment.

The pre-task manifest covers 330 tracked/untracked non-documentation files. Only
the six intended test files differ afterward; all other checked source, static
assets, catalog data, historical evidence inputs and migration files retain their
original bytes. See [preservation-check.json](preservation-check.json) and the
before/after hash manifests. No new skip, broad exception handler or production
behavior change was introduced.

## 5. Targeted results

| Direct correction group | Result | Evidence |
| --- | --- | --- |
| Login fixture, Map rendering fixture, two stale Map tests | 4 passed | `targeted-map-login.txt` |
| Alerts, direct Preview flow, inherited Profile navigation | 3 passed | `targeted-user-ui.txt` |
| Transition data/policy boundary and Tourism priority | 2 passed | `targeted-tourism.txt` |
| Total previously unsuccessful cases | **9/9 passed: 7 stale tests + 2 fixture issues** | Same test count retained |
| Relevant User suites | **129 passed** | `relevant-user-tests.txt` |

Relevant User coverage includes all six affected modules plus personalized
recommendations/UI, Preview routes, geography, Alerts routes and Profile behavior.
These runs completed before the full Python run.

## 6. Admin results

**85 passed**, no failures/errors. Command:

```text
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_admin*.py"
```

Evidence: [admin-tests.txt](admin-tests.txt). No Admin test or implementation change
was needed for these corrections.

## 7. Complete Python suite

The complete suite was run **once after targeted/Admin/relevant User checks passed**:

```text
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"
```

**1,003 run, 1,003 passed, 0 failures, 0 errors, 0 skipped.** Runtime: 63.567 seconds;
process exit 0, `OK`. Evidence: [full-python-suite.txt](full-python-suite.txt).

The result retains the original 1,003-test count and covers current security,
authorization, publication, metadata, recommendation/geography, weather, AI,
itinerary, User UI, session/auth and Admin contracts. No test was disabled to make
the baseline clean. This is offline test verification, not live database deployment.

## 8. JavaScript results

All **9 existing JavaScript test files passed**, **0 failed**. Production JavaScript
and JavaScript tests were unchanged. Each file was run directly with `node`.

| File | Reported tests | Result |
| --- | ---: | --- |
| `map_routing.test.js` | 16 | Passed |
| `test_budget_plan.js` | 9 | Passed |
| `test_map_frontend.js` | 13 | Passed |
| `test_personal_state.js` | No numeric count emitted | Passed |
| `test_recommendations_ui.js` | 3 | Passed |
| `test_recovery_frontend.js` | No numeric count emitted | Passed |
| `test_registration_frontend.js` | 9 | Passed |
| `test_theme.js` | 6 | Passed |
| `test_verification_frontend.js` | 3 | Passed |

Seven files report **59 passing tests** in aggregate; the other two custom runners
report success without numeric counts. Do not interpret 59 as a complete count
across all nine files. Full output: [javascript-tests.json](javascript-tests.json).

## 9. Whitespace and diff checks

`git diff --check` passed, exit 0. Existing CRLF conversion notices remain.
The task-only before/after diff was inspected, including originally untracked
tests which ordinary `git diff` does not include. Only the nine intended test
methods and necessary test imports changed. No test setup for unrelated modules
was altered. See [test-corrections.diff](test-corrections.diff) and
[diff-check.txt](diff-check.txt).

## 10. Database and migrations

**DATABASE: UNCHANGED. MIGRATIONS 0012/0013: UNAPPLIED.**

No SQL, Supabase changes, live record mutations, catalog edits, Tourism metadata
edits, coordinate changes or weather-metadata writes were performed. Policy probes
use in-memory fixture copies. Clean offline tests do not establish actual target
schema/RLS/ACL/owner or transactional-audit readiness. The separate migration
approval, isolated database checks and deployment sequence in the final review
remain prerequisites.

## 11. Git status and completion

The intentional dirty worktree remains preserved and unstaged. No `git add`,
commit, push, reset, restore or clean was performed. See [git-status.txt](git-status.txt).
The existing `.pytest_cache` inspection warning remains informational. New baseline
documentation and evidence remain untracked alongside the existing work.

Completion: **7/7 stale tests corrected; 2/2 fixture issues corrected; production
code unchanged; full Python suite clean; all JavaScript files passed.**

ROSAGO FINAL TEST BASELINE: CLEAN — READY FOR DATABASE DEPLOYMENT REVIEW
