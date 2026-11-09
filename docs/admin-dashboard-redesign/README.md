# Admin dashboard visual redesign

Local implementation and verification: 8 November 2026. Deployment remains **NO-GO**.

## Completed

- Kept the sidebar, dashboard structure, calculations, links and existing actions.
- Added coordinated statistic-card colors: emerald Published, gold Draft,
  lavender Archived, blue Total, rose Users, teal Trips, coral Needs Attention.
  Each uses themed tints, rounded icon containers, bolder numbers and 20px corners.
- Refined panel borders, shadows, progress bars, status badges and spacing.
- Removed the decorative heading description, repetitive visible summary/status
  captions, and redundant quick-action descriptions. Publication meanings remain
  available to screen readers. Important warnings, scope labels, unavailable
  states, review explanations and data limitations remain visible.
- Configured Inter consistently across Admin, including the wordmark and audit
  IDs. Admin now requests only Inter from the existing Google Fonts provider;
  the User font include is unchanged. System fallbacks remain for unavailable
  fonts. Offline browser screenshots use these fallbacks because external font
  requests are deliberately blocked; actual Inter downloading was not tested.
- Made shared Admin action controls pill-shaped, preserving semantic variants,
  focus outlines, disabled behavior and embedded password-control sizing.
- Made Appearance a 44px circular icon-only toggle beside the account dropdown.
  It retains the existing Dark-mode accessible name/state, tooltip, storage key,
  Settings synchronization and keyboard support. No new theme script was added.
- Refined sidebar navigation spacing and rounded active highlights.

## Files modified in this task

- `static/css/admin.css`
- `templates/admin/base.html`
- `templates/admin/dashboard.html`
- `templates/admin/head_assets.html`
- `tests/test_admin_dashboard.py`
- `tools/check_admin_appearance.py`

New evidence files:

- `docs/admin-dashboard-redesign/README.md`
- `docs/admin-dashboard-redesign/browser-results.json`
- `docs/admin-dashboard-redesign/1440-light.png`
- `docs/admin-dashboard-redesign/1440-dark.png`
- `docs/admin-dashboard-redesign/360-light.png`
- `docs/admin-dashboard-redesign/360-dark.png`

Earlier workspace changes and earlier `docs/admin-appearance` evidence were preserved.

## Tests and limits

- **133 Admin regression tests passed:**
  `.venv/Scripts/python.exe -m unittest discover -s tests -p test_admin*.py -q`
- **8 shared-theme tests passed:**
  `node --test --test-isolation=none tests/test_theme.js`
- **96 real-Edge layout/theme checks passed:** 16 synthetic Admin page renderings
  in both themes at 360px, 768px and 1440px. No page-level horizontal overflow or
  uncaught JavaScript errors/unhandled promise rejections were recorded.
  Run `.venv/Scripts/python.exe tools/check_admin_appearance.py` to repeat.
- Browser checks passed for Enter/Space theme switching, navigation and reload
  persistence, Settings synchronization, icon-only 44px toggle size, configured
  Inter family, pill buttons, profile-menu opening, Escape and focus restoration,
  visible focus, disabled hover/active behavior, photo selection/cancellation and
  reduced motion.
- Computed sampled Dashboard button and statistic-label contrast passed **4.5:1**
  in both themes. This is focused contrast testing, not a complete accessibility audit.
- Screenshots reviewed at desktop and mobile sizes.
- `git diff --check` passed for changed tracked files.

The browser fixture uses no `.env`, no real account and no live provider calls.
It renders via Flask's test client with synthetic sessions and mocked responses,
then serves GET-only snapshots on loopback with external browser traffic denied.
It recorded no browser form POSTs. Hosted writes and live login behavior were
not tested. Existing offline regression tests cover action and authorization contracts.

No database queries, statistics logic, permissions, authentication, hosted
projects, SQL, deployment configuration or User styles changed. No sign-ins,
deployment, commits or pushes occurred. The preserved Linux build-result SHA-256
remains `b3645b00f1ebe1a724e96ccf8d0f9831ef98cb1e627d27d5249b7d73f10a470d`.

Hard-refresh an already-open Admin page. Restart the local Flask process first
if it is caching templates. No database or configuration changes are required.
