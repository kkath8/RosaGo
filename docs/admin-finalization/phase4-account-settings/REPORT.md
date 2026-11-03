# RosaGo Admin Phase 4: Account, Settings, Help and About

Date: 1 November 2026 (Asia/Manila). Built on the existing [Admin audit](../AUDIT.md)
and [Phase 1](../phase1-dashboard/REPORT.md), [Phase 2](../phase2-destinations/REPORT.md)
and [Phase 3](../phase3-insights/REPORT.md) implementations.

## Pages and architecture

| Route | Behavior |
| --- | --- |
| `/admin/account` | Read-only own-account name/email, current Admin role/access, existing recovery-email entry and existing logout action. |
| `/admin/settings` | Light/Dark appearance using the same RosaGo theme behavior and storage key. |
| `/admin/help` | Operational guide with keyboard-accessible native disclosure groups and working workspace links. |
| `/admin/about` | Compact factual system/purpose/integration information; no runtime configuration dump. |

All four pages require existing normal authentication and fresh Admin membership.
They support GET/HEAD/OPTIONS only. Extra account-selection/query parameters are
rejected. Account uses `get_own_profile(g.auth)` with the existing request-owned
client and own-row RLS; other utility pages need no profile/catalog query.

Main navigation remains exactly Dashboard, Destinations and Catalog Insights.
Utility pages belong in the top-right account menu, with active utility links:
Account, Settings, Help, About RosaGo, existing View User Side, and POST Logout.
The generic A/Admin header identifies the mode without making an extra own-profile
request on every Admin page. The Account page identifies the actual signed-in Admin.

## Files changed

| File | Change |
| --- | --- |
| `admin_routes.py` | Four protected GET utility routes; safe own-account display projection and optional-name fallback. |
| `templates/admin/base.html` | Account utility links/current-page state; compact Admin label; Settings-specific location for the existing theme live status. |
| `templates/admin/account.html` — new | Own identity and existing security actions; no edit/save form. |
| `templates/admin/settings.html` — new | Shared Light/Dark controls and visible persistence feedback. |
| `templates/admin/help.html` — new | Concise operational disclosure guide. |
| `templates/admin/about.html` — new | Factual system information and capability limits. |
| `static/css/admin.css` | Bounded account menu, utility-page widths, compact identity rows, settings and guide styling in both themes. |
| `tests/test_admin_utilities.py` — new | Nine focused security/account/settings/menu/help/logout tests. |
| This directory | Report, live browser script, `browser-results.json`, 31 screenshots and Git status evidence. |

No changes to `admin_auth.py`, Admin/User logout logic, normal-auth stores,
password/OTP/recovery implementation, profile service, shared theme script/tokens,
destination services, recommendations, geographic logic or data/migrations.

## Account information and supported actions

Account displays only:

- Display name from the caller's existing first/last profile names, when supplied.
- The verified caller's email from the existing authenticated context.
- Administrator role and Authorized access, established by the current Admin boundary.

The route passes only display strings/flags to Jinja, not the profile object,
profile UUID, authenticated context, session handle or security claims. Names/email
are autoescaped. A missing name is Not provided; an optional profile-read failure
shows Temporarily unavailable while retaining the verified signed-in email.

Account details are intentionally read-only. The existing User profile service has
an own-name update operation, but this phase explicitly prohibits user updates, so
no Admin name editor or fake Save control was introduced. There are no signup/last
login/session-age claims derived from unsupported or mismatched timestamps.

Change Password links to the existing `/forgot-password` recovery-email flow. Admin
and User authentication share that account architecture; no separate password API,
credential display or recovery bypass was added. Verification does not submit a
recovery email or change any password/user record.

Delete Admin Account, session management, other-user resets, membership management,
impersonation and unsupported profile edits are omitted.

## Settings and theme

Appearance alone is implemented: Light and Dark. These buttons use the existing
`data-set-theme` controls, `theme.js`, theme assets and `rosago.theme.v1` preference.
There is no second theme implementation, new storage key or account-level setting.
The choice applies to Admin and User pages on this browser and follows the same
validation, light default, blocked-storage feedback and cross-tab synchronization.

On Settings, the visible page owns the single `data-theme-status` live region;
the header retains its static device hint. This lets the existing shared script
update visible Settings feedback without modifying User theme behavior. Both sets
of header/page buttons still reflect the selected theme through the existing script.

No travel interests, traveler type, budget, transportation, pace or personal-state
scripts are included. Table density/page-size placeholders were not added.

## Help and About content

Help covers Dashboard count scopes; review-only Destinations; Catalog Insights and
Needs Attention; Published/Draft/Archived states; Local/Common/Unclassified;
distinct RosaGo/Tourism categories; coordinate requirements; all five exposure
classes; raw-hours limitations; account/appearance and sign-out.

It explicitly states that Unclassified is not Common, Unknown is not assumed to
be Outdoor, and Needs Attention flags are data quality review items rather than
errors. Missing coordinates limit location features without removing an otherwise
eligible recommendation. Curated exposure is not a safety/live-weather guarantee.

About identifies RosaGo's Santa Rosa itinerary purpose, the catalog/City Tourism
metadata source, OpenStreetMap/Leaflet map, Open-Meteo weather, geographic-aware
recommendation behavior and Gemini's supported interpretation/explanation role.
It states that Gemini does not define destination metadata. Provider names are
integration information, not uptime/availability claims. No API keys, environment
values, internal endpoints, credentials, model identifiers or Auth internals appear.

## Logout and security

Logout uses the unchanged `/admin/logout` POST form and existing normal-session
CSRF token and exact-Origin validation. Membership revocation still cannot prevent
the caller from signing out. Logout revokes this application's local normal session,
clears browser-session authority and redirects to `/admin/login`; it does not claim
provider-wide sign-out of every device.

Automated tests verify correct logout, local-store revocation and denied access to
all four utility pages and the three workspace pages afterward, without catalog
or profile queries. They also exercise the unchanged User `/logout` route and its
existing 303 redirect/revocation behavior. Existing Admin tests retain wrong/missing
CSRF, wrong/missing Origin, extra-field and logout-failure coverage.

Admin-only boundaries, own-row profile RLS, safe provider errors, private/no-store
headers, same-origin protections and template-authority isolation are unchanged.
No authentication/recovery credentials or private User data are displayed. Existing
required CSRF form fields remain. The new routes offer no profile/catalog mutation.

## Tests

Baseline: **61 existing Admin tests passed**. Current focused Admin run:
`.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_admin*.py'`
— **70 passed**. The existing shared theme tests also pass: `node tests/test_theme.js`
— **6 passed**, including invalid/blocked storage and cross-tab behavior.

New tests cover unauthorized redirects, nonmember denial before profile reads,
safe own-name/email display and escaped text, no Auth/profile objects in template
values, missing names/profile failure, rejected selection parameters/methods,
single visible theme live region, no travel controls, valid account links and
unchanged main navigation, factual guide terminology, no configuration exposure,
Admin logout and post-logout denial, and unchanged User logout.

The full massive application suite is not repeated. No live record mutation is
used to test functionality.

## Browser verification

**103 live checks passed with 31 screenshots and zero browser runtime errors.**
The user signed in locally to the real Flask application; no credentials were
requested in chat, inspected, or injected by a fixture. Evidence is recorded in
[`browser-results.json`](browser-results.json) and [`screenshots/`](screenshots/).

Dashboard, Destinations, Catalog Insights, Account, Settings, Help and About were
checked at **1440px and 390px, each in Light and Dark** (28 page captures). Every
capture had no page-level horizontal overflow, the Inter font loaded, the Admin
identity remained present, and the header controls did not overlap the brand.
Utility pages stack cleanly at 390px. Screenshots were visually reviewed for
readable text, established theme colors, compact cards and usable controls.

Settings switches updated the visible persistence status and remained selected
after reload. Main navigation remained the same three links. The account menu
opened using the keyboard, showed all four working utility routes, and closed with
Escape while returning focus. Mobile main navigation remained usable. Help's
weather disclosure opened and the required Unknown/Outdoor terminology was checked.
Two additional screenshots show the keyboard-open account menu at both widths.

The script then clicked the existing Admin Logout button once. Logout returned to
`/admin/login`, removed the Admin shell, and showed the sign-in form (the final
screenshot). Navigating to **all seven protected routes afterward redirected to
Admin sign-in**, without showing protected content. No catalog/profile/password
update was submitted. The original theme preference was restored before logout.

The local app remains available. The verification browser is deliberately left
signed out, with a fresh Admin login available through the existing login page.
Account screenshots contain only the signed-in Admin's allowed own identity;
the machine-readable result records pass/fail and layout measurements, not identity
values, tokens, cookies, credential values or network headers.

## Database and Git status

No SQL, migrations, schema/grant changes, destination updates, user-record updates,
Tourism changes or weather/coordinate changes. The optional Account name fetch is
an existing own-profile read. Theme persistence is presentation-only device storage.

The intentional worktree is preserved. No stage, commit, push, reset, restore or
Git clean operation is performed. Phase files remain unstaged/untracked; final
short status is captured in `git-status.txt`. `git diff --check` passed; Git emitted
existing line-ending notices and an unreadable `.pytest_cache` directory warning.
Neither warning represents a whitespace-check failure or a staged change.

ROSAGO ADMIN PHASE 4 ACCOUNT SETTINGS: READY FOR LIVE VERIFICATION
