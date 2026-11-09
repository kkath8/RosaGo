# Admin appearance and controls — local verification

Implemented 8 November 2026. Remote deployment remains **NO-GO**.

The header Appearance control is now a native toggle button in its original
position. Its stable accessible name is “Dark mode”; `aria-pressed` communicates
whether Dark Mode is enabled. Decorative sun/moon icons show the current theme,
and the tooltip names the next action. Enter and Space work natively.

It extends the existing `theme.js` preference (`rosago.theme.v1`), including
before-paint restoration, Settings synchronization, cross-tab synchronization,
and honest feedback when browser storage is unavailable. The existing shared
User/Admin appearance preference is preserved; no User styles were changed.

Admin buttons now share rounded corners, spacing, typography, focus outlines,
shadows and subtle hover/active states. Existing action classes select burgundy
primary, neutral secondary, gold appearance/selected, or red destructive styles.
Standard controls have a 44px minimum height, with the existing larger login
submit and embedded password control fitted to their contexts. Disabled controls
do not move or acquire hover styles; hidden controls remain hidden. Reduced
motion is respected. Existing forms, navigation, CSRF and permission checks are
unchanged.

## Files changed for this task

- `templates/admin/base.html`: replace Appearance menu with a direct toggle and live feedback.
- `static/js/theme.js`: opt-in direct toggle support using the existing preference.
- `static/css/admin.css`: consolidate superseded button rules into scoped control styles.
- `tests/test_theme.js`: toggle, persistence, storage failure, synchronization and disabled-control coverage.
- `tests/test_admin_dashboard.py`: update the header contract to the requested toggle.
- `tests/test_admin_utilities.py`: check semantic toggle attributes and the single Settings status region.
- `tools/check_admin_appearance.py`: repeatable isolated Edge checks.
- `docs/admin-appearance/README.md`: this report.
- `docs/admin-appearance/browser-results.json`: sanitized browser results.
- `docs/admin-appearance/1440-light.png`, `1440-dark.png`, `360-light.png`, `360-dark.png`: synthetic dashboard screenshots.

The workspace contained earlier changes before this task. This list describes
this task only; it is not an inventory of all outstanding repository changes.

## Verification

- `node --test --test-isolation=none tests/test_theme.js`: **8 passed**.
- `.venv/Scripts/python.exe -m unittest discover -s tests -p test_admin*.py -q`: **133 passed**.
- Focused suites `test_settings.py`, `test_public_layout.py`,
  `test_login_referrer_policy.py`, `test_independent_sessions.py`: **64 passed**.
- `.venv/Scripts/python.exe tools/check_admin_appearance.py`: **96 layout/theme checks passed**
  (16 actual Admin page renderings, Light/Dark, 360/768/1440px), no page-level
  horizontal overflow. Includes login, Dashboard, catalog, new/edit/detail,
  publication confirmation, Users, Trips, Insights, System, Audit, Account,
  Settings, Help and About. Uses synthetic records only.
- Real-browser checks passed for Space/Enter toggling, navigation/reload
  persistence, Settings synchronization, profile dropdown opening, Escape/focus
  restoration, keyboard focus visibility, photo selection/cancellation,
  reduced motion and disabled hover/active states in both themes.
- Computed text contrast of sampled Dashboard primary/secondary/Appearance
  buttons is at least **4.5:1** in both themes. This is focused verification,
  not a full accessibility audit of every page and state.
- Screenshots reviewed at desktop and mobile sizes.
- `git diff --check` passed for changed tracked files.

The browser harness does not load `.env`. It renders through Flask's test client
with synthetic sessions and mocked provider responses, then serves GET-only
snapshots on an ephemeral loopback port. Browser external traffic uses a deny
proxy. **No browser form POSTs or live sign-ins occurred.** Edge requires the
local browser execution permission in environments that restrict child browsers.
No hosted project, SQL, accounts, infrastructure or security configuration changed.
No deployment, commit or push was performed.

The preserved Linux build result file
`docs/production-readiness/remote-evaluation/linux-build-results.json` still has
SHA-256 `b3645b00f1ebe1a724e96ccf8d0f9831ef98cb1e627d27d5249b7d73f10a470d`.

## Local operator action

Hard-refresh an already-open Admin page to load the updated assets. No Flask
configuration, database operation or live sign-in is required for these changes.
