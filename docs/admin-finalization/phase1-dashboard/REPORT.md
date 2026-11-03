# RosaGo Admin Phase 1: shell and dashboard

Completed 1 November 2026 (Asia/Manila). Scope: Admin shell, dashboard, responsive
presentation, shared Light/Dark integration, and read-only existing-data aggregation.
The implementation follows [the Admin audit](../AUDIT.md).

## Architecture

The existing `/admin` blueprint, normal-auth session, fresh `rosago_is_admin()`
membership check and request-owned Supabase client remain authoritative.
The dashboard keeps `destination_counts()` for its four exact status counts and
adds `published_catalog_health()` for a complete published-catalog health read.
Only allowlisted public catalog fields are queried; no account/trip table reads
or new database capabilities were introduced.

Health queries request exact counts, read at most 200 rows per page in stable slug
order, and reject incomplete pages, duplicate identities, changing totals,
malformed values and catalogs over 2,000 published records. Such failures display
health as unavailable while preserving independently available status counts.
This does not reuse the recommendation system's 100-candidate limit.

The shell loads the existing RosaGo design tokens, Inter/Sora font include,
pre-paint theme script and theme stylesheet. Admin-specific CSS adapts the surfaces,
controls, badges and existing destination pages to those tokens. `admin.js` manages
only disclosures: closing other menus, outside clicks and Escape/focus return.
It does not implement another theme preference or access personal User state.

## Files changed in this phase

| File | Change |
| --- | --- |
| `admin_routes.py` | Dashboard-only health integration and Asia/Manila observation timestamp. Existing authentication, authorization, login/logout and destination routes retain their behavior. |
| `admin_dashboard_service.py` — new | Validated, bounded, read-only published-catalog health aggregation. |
| `static/css/admin.css` | Shared visual tokens, Inter UI/Sora wordmark, compact sticky header, 16px cards, 8px controls, responsive dashboard/table layout and dark styling for all existing Admin surfaces. |
| `static/js/admin.js` — new | Accessible disclosure handling; no network or mutation behavior. |
| `templates/admin/base.html` | Shared header, supported navigation, appearance menu, generic Admin avatar/account menu and existing secure logout form. |
| `templates/admin/dashboard.html` | Summary metrics, Catalog Health, Quick Management, separate status/type tables, observation time and unavailable states. |
| `templates/admin/head_assets.html` — new | Shared Admin font/token/theme assets. |
| `templates/admin/login.html` | Reuse Admin head assets; forms/auth behavior unchanged. |
| `templates/admin/access_error.html` | Reuse Admin head assets; denial behavior unchanged. |
| `tests/test_admin_dashboard.py` — new | Eleven focused aggregation, dashboard, navigation, theme-asset and security tests. |
| `tests/test_admin_places.py` | Existing HTTP fixture recognizes the additional read-only health projection. |
| This directory | Report, offline preview server, browser checks, measured results, Git status and 19 screenshots. |

No User templates, shared theme script/tokens, recommendation/geography logic,
catalog records, coordinate values, weather/Tourism classifications or historical
migrations were changed during this phase. Other changes visible in Git predate
this task and remain intact.

## Admin navigation

- Desktop: RosaGo wordmark and ADMIN badge, Dashboard, Destinations, Appearance,
  and generic Administrator account disclosure.
- Mobile: compact brand/appearance/avatar controls and a keyboard-operable Menu
  containing only Dashboard and Destinations.
- Active page is marked visually and with `aria-current="page"` on dashboard and
  existing destination pages.
- Account disclosure contains View User Side, the existing Change Password recovery
  entry and the existing POST logout form with its normal-session CSRF token.
- Quick Management links to `/admin/places`, `/admin/places?status=draft`, and the
  real dashboard's `catalog-health` section. No dead placeholder links were added.

Users, Trips/Insights, Analytics, System/Weather, Audit Logs and Admin profile-edit
pages were not created or advertised. The audit does not establish existing safe
cross-user access, and these routes are outside Phase 1.

## Dashboard metrics and their sources

| Metric | Source | Scope/availability |
| --- | --- | --- |
| Published | Existing exact HEAD count on `places` filtered `status=published` | All visible published destinations under current Admin authorization. |
| Draft | Existing exact HEAD count, `status=draft` | All visible drafts. |
| Archived | Existing exact HEAD count, `status=archived` | All visible archived records. |
| Total destinations | Existing exact HEAD count without status filter | All visible publication statuses. |
| Local / Common | Exact-complete health dataset, `tourism_type` | Published destinations; primary cards appear only when Tourism metadata is enabled and the health read succeeds. |
| Tourism Type not assigned | Count of actual NULL `tourism_type` values in that dataset | Published destinations; disabled metadata is unavailable, never interpreted as all NULL. |
| With/missing coordinates | Valid complete latitude/longitude pairs in that dataset | Published destinations; no invented or independently verified-location claim. |
| Weather classified / unknown | `load_weather_catalog().for_place(row)` applied to that dataset | Published destinations; exact slug/name/category/address binding, not raw JSON row totals. |

Tourism columns follow the existing `ROSAGO_TOURISM_METADATA_ENABLED=true` feature
flag. If disabled, Tourism counts are explicitly unavailable and the dashboard
retains the four publication summary cards. Missing columns or malformed data
produce an unavailable health section without exposing provider errors.

An unavailable weather curation file produces unavailable weather counts, not zero
classified/all unknown. A valid file with no matching known classifications can
correctly produce zero classified. Existing identity mismatches remain unknown;
the implementation never repairs sidecar identities or classifications.

Status counts are all-status metrics; quality/type metrics are clearly labeled
published-only. Counts are separate reads, not a transactionally consistent snapshot.
The display reports an observation time in Asia/Manila and discloses separate reads.
There are no historical trends or manufactured percentages.

## Intentionally omitted metrics and features

Registered users, global trip/itinerary counts, destination popularity, generation
events, recent Admin activity, private notes/preferences, AI histories, provider
uptime/response-time charts and official emergency status are omitted.
No durable Admin audit log exists, so no Recent Activity feed is shown.

No live weather panel was added: the existing weather getter may initiate a provider
request when its cache expires. Phase 1 does not add that request to dashboard loads
or inspect private cache internals to pretend a provider-health monitor exists.
Curated exposure coverage requires no weather-provider network call.

Destination create/edit/publish/archive controls remain existing disabled previews.
No CRUD, user management, analytics pages, audit persistence or schema work was added.

## Responsive and Light/Dark verification

Actual rendered Flask pages were inspected in headless Microsoft Edge using an
isolated temporary browser profile and a GET-only loopback preview server. HTML is
generated through existing authenticated test clients and the real service/template
pipeline with network-guarded test transports. **Screenshot numbers are fixture
data, not live Supabase totals.** No production account was logged in or provisioned.

| Viewport | Light | Dark | Evidence |
| --- | --- | --- | --- |
| 1440px dashboard | Passed | Passed | Six compact summary cards, two-column sections, desktop active navigation. |
| 768px dashboard | Passed | Passed | Three-column summaries, stacked content sections, compact header. |
| 390px dashboard | Passed | Passed | Two-column summaries, single-column panels, contained tables and native mobile navigation. |
| 320px dashboard | Overflow check passed | Saved dark preference | Extra narrow-width check; no horizontal page overflow. |
| 1440px/390px destination list | Passed | Passed | Existing listing and active Destinations navigation retained. |
| 1440px/390px destination detail | Passed | Passed | Existing fields, weather panel and disabled publication actions retained. |
| 1440px/390px destination edit preview | Passed | Passed | Existing controls/form layout readable; mutation buttons remain disabled. |

The final browser run passed **55 checks**, captured **19 screenshots**, and recorded
no JavaScript runtime exceptions. Inter loaded in all measured views. Header groups
did not overlap; page scroll widths remained within the viewport. The browser also
checked the single existing theme preference/persistence, themed secondary-button
surfaces, active navigation, valid actions, account-menu Escape/focus return, native
mobile-menu keyboard activation and disabled mutation controls.

Light and Dark share the User theme key `rosago.theme.v1`, its default, storage-failure
handling and cross-tab synchronization. No personal state scripts or User navigation
are loaded by the Admin shell. Login/error pages also load the same saved theme.

Key screenshots:

- [1440px Light](screenshots/dashboard-1440-light.png)
- [1440px Dark](screenshots/dashboard-1440-dark.png)
- [768px Light](screenshots/dashboard-768-light.png)
- [768px Dark](screenshots/dashboard-768-dark.png)
- [390px Light](screenshots/dashboard-390-light.png)
- [390px Dark](screenshots/dashboard-390-dark.png)
- [390px mobile menu](screenshots/dashboard-390-dark-menu.png)
- [Existing destination page, 390px Dark](screenshots/destination-detail-390-dark.png)

Machine-readable measurements and checks: [browser-results.json](browser-results.json).
Reproduction: run `preview_server.py` from the project virtual environment, start
an isolated headless Edge CDP session on port 9235, then run `browser_checks.py`.
The preview binds only to `127.0.0.1:5068` and exposes GET requests only.

## Security verification

Existing Admin boundaries remain unchanged: unauthenticated redirect, nonmember
denial, fresh membership/revocation, private/no-store responses, fixed provider
errors, template authority isolation, same-origin and CSRF checks, and restricted
read-only database clients. Tests verify nonmembers never reach catalog aggregation.

The new service reads only `places`, through the authenticated request-owned client,
using explicit field projections and no retries. The new JavaScript performs no
fetches, Auth admin calls or private-data access. The avatar is a generic Admin
initial, not a new profile lookup. No access/refresh/recovery token, OTP, password/hash,
private trip, browser-local preference or conversation data is exposed.

Automated tests and isolated browser fixtures verify application behavior; they do
not establish deployment RLS or schema state. In particular, all-status Admin counts
still depend on the preexisting 0008/0009 deployment described by the audit.

## Test results

| Command / suite | Result |
| --- | --- |
| `python -m unittest discover -s tests -p 'test_admin*.py'` before changes | 25 passed. |
| Same Admin command after changes | 36 passed. |
| `test_public_layout.py` | 19 passed; an existing unclosed-static-file ResourceWarning was emitted. |
| `node tests/test_theme.js` | 6 passed, including invalid/blocked storage and cross-tab behavior. |
| `test_itinerary_geography.py` | 8 passed. |
| `test_tourism_weather_identity.py` | 7 passed. |
| `test_login.py` | 26 passed. |
| `test_user_profile.py` | 20 passed. |
| `test_trip_routes.py` | 23 passed, 1 unrelated current-worktree failure; see below. |
| Offline Edge browser checks | 55 passed, 19 screenshots, no runtime exceptions. |
| `git diff --check` | Passed (exit 0); existing CRLF conversion warnings only. |

The trip-suite failure is
`TripRouteTests.test_reads_forms_account_link_and_unavailable_place`: it asserts
that the literal text `My Trips` occurs directly in `templates/user/index.html`.
That existing Profile template is already modified in the user's worktree and
inherits User navigation from shared templates. Neither that file nor this test
was changed in Phase 1. The failure is documented rather than changing unrelated
User implementation or tests to make this Admin task green.

The Node `--test` subprocess runner hit the sandbox's `spawn EPERM` restriction;
running the existing test file directly with Node passed all six tests. Edge also
needed permission to run outside the process sandbox for browser IPC; it used a
dedicated temporary profile, not the user's browser session.

## Database status and known limitations

No SQL was executed, no migrations were created/applied, no schema/grants were
altered, and no Supabase/destination/classification/coordinate/weather records were
modified. Application code adds read-only catalog queries when Dashboard loads.
Live deployed Admin access and current catalog totals remain to be verified with
an existing authorized account.

Health's 2,000-row bound is explicit: larger/incomplete/inconsistent reads show
unavailable rather than partial counts. Multi-page reads and four status counts
are not a single snapshot. Tourism metadata must be enabled/deployed; recorded
coordinate pairs have no independent verification provenance flag. Sidecar identity
drift still requires separate human curation. Fonts use the existing remote font
include with system fallbacks if unavailable. Native disclosures remain usable
without Admin enhancement JavaScript.

## Git status

The preexisting large intentional worktree was preserved. Phase changes are
unstaged; no stage, commit, push, reset, restore or clean operation was performed.
Full short status captured in [git-status.txt](git-status.txt). The Admin files that
were already modified remain modified; new service, script, test, asset partial
and evidence files remain untracked. Git also reported an existing permission
warning when inspecting `.pytest_cache`; it did not block diff validation.

ROSAGO ADMIN PHASE 1 DASHBOARD: READY FOR LIVE VERIFICATION
