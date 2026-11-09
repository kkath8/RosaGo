# Admin workspace settings — local implementation

Completed 8 November 2026. Remote deployment remains **NO-GO**.

## Implemented preferences

The redesigned Settings page uses rounded, responsive cards with burgundy,
gold, blue and green accents, Inter typography, native switches, segmented
density controls and labelled dropdowns. Existing account/password links and
the CSRF-protected Admin logout form are available alongside read-only workspace
information, Help and Audit Logs.

| Preference | Actual effect |
| --- | --- |
| Light/Dark | Existing shared `theme.js` preference, immediate and unchanged |
| Comfortable/Compact | Admin table cell padding, preserving readable type and touch controls |
| Reduce animations | Removes Admin transitions, animation and animated active movement; OS reduced motion remains respected |
| Catalog review alerts | Shows/hides the existing Dashboard review card when its count is known; review lists and unavailable warnings remain available |
| Successful action confirmations | Shows/hides only existing server flash messages categorized as successful; errors, warnings and security messages are never opted out |
| Destination order | Existing catalog order, Newest/Oldest by creation timestamp, or case-insensitive Name A–Z |
| Destinations per page | 10, 25 or 50 actual records, sorted/filtered before pagination |
| Default destination status | All, Published, Draft or Archived on a bare destination-management visit |
| Time | 12-hour or 24-hour display for tagged Admin record timestamps |
| Date | Day Month Year, Month Day Year or ISO-style Year-Month-Day display |

Save Preferences is required for the Admin-specific choices. Theme remains
immediate using its existing controls and storage key. Unsaved changes are
identified. A success message appears only after a synchronous storage write
and exact read-back confirmation; failed or ignored writes do not replace active
preferences. Cross-tab changes synchronize display controls and are labelled
as cross-tab changes rather than a new local save.

## Scope and safety

The new `rosago.admin.preferences.v1` entry contains only validated presentation
and catalog-default enums/booleans. It contains no account identity, session,
password, token or authorization data, and never acts as an access authority.
Malformed/oversized/unsupported storage falls back to defaults. Browser storage
does not synchronize between devices or accounts. Anyone using the same browser
profile shares these local appearance choices.

Catalog defaults populate same-origin GET query parameters. Explicit query
parameters take priority; an explicit All-status selection is preserved. Sorting
and page-size controls are also present on Destinations and work without saved
preferences. The browser may perform a same-origin replacement navigation to
apply saved defaults. Current filters are not silently changed on a cross-tab
preference update. View All explicitly clears the status filter.

The server independently validates sort/page-size values, rejects duplicated
or unsupported query fields, retains fresh Admin authorization and RLS-backed
request-owned access, and keeps the existing bounded full-catalog consistency
checks and 2,000-record cap. Creation timestamps are additionally projected only
for creation-date sorting. Equal creation dates retain stable slug ordering.
Sorting precedes display pagination; summary counts remain for the full catalog.
No schema, index or RPC change is required.

Date formatting uses the explicit **Asia/Manila** timezone for supported,
timezone-qualified record timestamps: Audit Logs, User creation dates,
destination Created/Updated, Dashboard and Insights observation times. Raw
`datetime` attributes and full original audit-detail timestamps are preserved.
Ambiguous or invalid timestamps retain their server-rendered fallback. No stored
timestamp, audit entry or timezone metadata changes.

## Deferred / deliberately scoped

- Application version display: omitted because no reliable RosaGo application
  release-version source was found. The authority service's package version is
  not used as an application version.
- Page-size preference applies to Destinations. Existing User-directory and
  Audit pagination sizes remain fixed.
- Notification controls cover the two existing supported UI categories above.
  No email, SMS, push, background monitoring, new alert events, account-wide sync
  or global system/security controls were added.
- Time/date preference applies to the supported recorded timestamps listed
  above; unrelated forecast date strings retain their existing presentation.

## Modified source and tests

- `admin_places_service.py`
- `admin_routes.py`
- `static/css/admin.css`
- `static/js/admin-preferences.js` (new)
- `templates/admin/settings.html`
- `templates/admin/head_assets.html`
- `templates/admin/places.html`
- `templates/admin/base.html`
- `templates/admin/dashboard.html`
- `templates/admin/audit_logs.html`
- `templates/admin/insights.html`
- `templates/admin/place_detail.html`
- `templates/admin/users.html`
- `tests/test_admin_preferences.js` (new)
- `tests/test_admin_destinations.py`
- `tests/test_admin_utilities.py`
- `tests/test_admin_dashboard.py`
- `tools/check_admin_appearance.py`

New evidence: this README, `browser-results.json`, four
`settings-{1440,360}-{light,dark}.png` screenshots and the existing checker's
Dashboard/Audit screenshot series, all inside `docs/admin-settings/`.
Previous UI/security evidence was preserved.

## Verification

- **139 Admin tests passed:**
  `.venv/Scripts/python.exe -m unittest discover -s tests -p test_admin*.py -q`
- **13 preference/theme tests passed:**
  `node --test --test-isolation=none tests/test_admin_preferences.js tests/test_theme.js`
- **96 browser layout/theme checks passed:** 16 Admin page renderings in both
  themes at 360, 768 and 1440px. No page-level horizontal overflow or uncaught
  JavaScript errors/unhandled rejections recorded.
- Real Edge verified save/read-back, unsaved feedback, navigation persistence,
  reflected controls, actual GET catalog defaults, explicit filter overrides,
  compact table padding, 24-hour/ISO Audit formatting, untouched original audit
  timestamps, reduced motion, review-card visibility and visible errors while
  successful confirmations are hidden. Both thrown writes and silently ignored
  writes produced error feedback without changing active preferences.
- Server tests verified creation/name sorting over the full catalog, stable
  ties, actual 10/50-row pagination, preserved filter links/counts, rejection of
  invalid/duplicate query values, invalid creation-date fail-closed behavior,
  unavailable review-state visibility and unchanged Admin authorization.
- Pure JavaScript tests cover invalid/oversized/blocked storage, exact supported
  types, cross-tab clearing, timezone/midnight handling, date formats, original
  timestamps, catalog redirects and explicit selections.
- Existing theme, table semantics/disclosures, header menus, keyboard focus,
  Quick Management layout, disabled states and photo controls remain passing.
- Desktop/mobile screenshots reviewed. Inter uses the existing web-font source;
  offline screenshots use fallback fonts because external requests are blocked.
- `git diff --check` passed for changed tracked files.

Repeat browser checks with
`.venv/Scripts/python.exe tools/check_admin_appearance.py`.
The fixture loads no `.env`, uses synthetic sessions and mocked providers, serves
GET-only loopback pages, and denies external browser traffic. Catalog query
requests run through the actual local Flask route with synthetic data. No browser
form POSTs or live sign-ins occurred. This is offline qualification, not live
provider or deployment acceptance.

No hosted project, account, Auth setting, SQL, RLS policy, session/recovery control,
User styling or deployment configuration changed. No deployment, commit or push
occurred. Preserved Linux build-result SHA-256:
`b3645b00f1ebe1a724e96ccf8d0f9831ef98cb1e627d27d5249b7d73f10a470d`.

Restart the local Flask process to load the route/service changes, then
hard-refresh an already-open Admin page. Use Save Preferences for the new Admin
choices. No database or environment configuration changes are required.
