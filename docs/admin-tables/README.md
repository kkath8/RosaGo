# Admin tables — local UI verification

Completed 8 November 2026. Remote deployment remains **NO-GO**.

## Changes

All existing Admin tables now use the same scoped table component: Inter font
stack, 14px body text, semibold tinted column headers, consistent cell padding
and dividers, subtle alternating/hover/focus rows, rounded 16px containers and
contained horizontal scrolling. Regions are keyboard focusable and labelled;
column and row headers remain semantic. Old mobile catalog card transforms
were replaced with semantic scroll tables. Existing button variants remain.

This covers Audit, Destinations, Users, Trips, Insights, System/Weather and the
Dashboard distribution tables. Added Activity History and User Management
headings; renamed Destination records to Destination Management. Existing
section titles were retained for already-labelled aggregate tables. Trip data
remains the existing aggregate views.

Audit rows show compact dates/times, prominent actor and destination names,
secondary emails, labelled action badges, resulting status and an accurate
field-count summary. **“N fields submitted” counts the recorded submitted field
names; it does not claim that N values changed.** No before/after values are
invented. Publication-only events retain their status-change description.

Native View Details disclosures retain complete available audit information:
audit, actor and destination IDs; destination slug; full timestamp; action;
resulting status; readable field descriptions and exact submitted field names.
Names/emails and destination links remain in the row. Missing actor/destination
fallbacks remain. Identifiers are removed from the compact row presentation,
not from the rendered data. A scoped Admin script brings opened detail panels
fully into the horizontal scroll region; native disclosures also work without
JavaScript using manual scrolling. No new API requests are needed to expand.

## Modified files

- `static/css/admin.css`
- `static/js/admin.js`
- `templates/admin/audit_logs.html`
- `templates/admin/dashboard.html`
- `templates/admin/insights.html`
- `templates/admin/places.html`
- `templates/admin/system.html`
- `templates/admin/trips.html`
- `templates/admin/users.html`
- `tests/test_admin_audit.py`
- `tools/check_admin_appearance.py`

New evidence under `docs/admin-tables`: this README, `browser-results.json`,
dashboard screenshots `1440-light.png`, `1440-dark.png`, `360-light.png`,
`360-dark.png`; audit screenshots `audit-light.png`, `audit-dark.png`, and
`audit-{1440,360}-{light,dark}-expanded.png`.

## Results

- **134 Admin tests passed:**
  `.venv/Scripts/python.exe -m unittest discover -s tests -p test_admin*.py -q`
- **96 browser layout/theme checks passed:** 16 synthetic Admin page renderings
  at 360/768/1440px in Light/Dark. No page-level horizontal overflow or uncaught
  JavaScript errors/unhandled rejections recorded. All rendered tables use the
  scoped component, focusable scroll containment and explicit column headers.
- Keyboard opening/closing and full disclosure content passed in all six
  viewport/theme combinations, including all 13 recorded field names and the
  complete IDs/timestamp in the long-field fixture. Detail panels fit and align
  inside their scroll region on mobile. Native focus indicators remain visible.
- Existing audit tests pass for filters, pagination, escaping, complete field
  descriptions, actor attribution, missing/deleted identities, unavailable
  states, read-only behavior and permission enforcement. Added assertions prove
  IDs/fields are retained in initially closed disclosures, and empty field lists
  produce an honest publication-status summary.
- Existing theme persistence, header dropdown, Quick Management order/grid,
  reduced-motion, disabled-button and photo-selection checks remain passing.
- Desktop and mobile screenshots reviewed. `git diff --check` passed.

Repeat the browser checks with
`.venv/Scripts/python.exe tools/check_admin_appearance.py`.
This fixture loads no `.env`, uses synthetic sessions and mocked provider
responses, serves GET-only snapshots on loopback, and denies external browser
traffic. No browser form POSTs or live authentication occurred. The configured
Inter web font uses the existing Google Fonts source; offline screenshots use
the fallback font because external requests are blocked. These focused checks
are not an exhaustive accessibility audit or a live integration test.

No database queries, audit logging, records, permissions, security policies,
hosted projects, User styles or deployment configuration changed. No SQL,
sign-ins, deployment, commits or pushes occurred. Previous evidence remains
preserved, including Linux build result SHA-256
`b3645b00f1ebe1a724e96ccf8d0f9831ef98cb1e627d27d5249b7d73f10a470d`.

Hard-refresh an already-open Admin page. Restart local Flask first if templates
are cached; no database or environment configuration changes are required.
