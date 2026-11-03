# RosaGo Admin Phase 3: Catalog Insights

Date: 1 November 2026 (Asia/Manila). References: [Admin audit](../AUDIT.md),
[Phase 1](../phase1-dashboard/REPORT.md), [Phase 2](../phase2-destinations/REPORT.md).

## Data sources and architecture

Added one Admin-only GET page, `/admin/insights`, labeled **Catalog Insights** in
both desktop and mobile navigation. It uses the same authorized `places` table
read as Destination review, existing Tourism columns, and the existing curated
weather sidecar. There is no new catalog, analytics store or chart dependency.

The Phase 2 complete reader is now shared as `read_catalog()`. It retains exact
page counts, stable slug ordering, validation, duplicate rejection, 200-row database
batches and an explicit 2,000-record ceiling. Insights adds the existing
`tourism_hours_status` column to that projection when Tourism metadata is enabled;
it does not issue one detail request per destination. Destination review retains
its previous projection and filters. Incomplete/oversized/inconsistent reads show
an unavailable page, never partial numbers presented as complete.

`admin_insights_service.py` calculates distributions and flags in memory for this
request only. Existing normal authentication, fresh Admin membership, request-owned
client and template-authority isolation remain the boundary. No provider, AI,
geocoder, routing, account directory or private trip query is invoked.

## Files changed

| File | Change |
| --- | --- |
| `admin_insights_service.py` — new | Scoped distributions, percentages, category/type matrix, map readiness, effective exposure, hours statuses and bounded attention results. |
| `admin_places_service.py` | Extract complete shared catalog reader; optional validated hours-status projection; retain current review/detail contracts. |
| `admin_routes.py` | Admin-protected GET Insights route, strict scope/issue/page validation, pagination links and observation time. |
| `templates/admin/insights.html` — new | Operational coverage page with accessible count/bar labels, distributions, readiness, lists and attention filters. |
| `templates/admin/base.html` | One supported navigation link and active state for Catalog Insights. |
| `static/css/admin.css` | Scoped insight bars, compact metrics/tables, attention rows and responsive header/layout adjustments. |
| `tests/test_admin_insights.py` — new | Thirteen focused calculation/read/route tests. |
| This directory | Report, read-only browser script/results/screenshots and Git status evidence. |

No changes to recommendation/geography logic, User pages, weather service or
classification files, Tourism values, coordinates, authentication or migrations.

## Scope, metrics and calculations

Default scope is **Published destinations**. The GET selector supports Published,
All, Draft and Archived. Changing scope resets attention pagination. Publication
Overview always reports all visible catalog records and labels that denominator;
all other distributions/readiness indicators use the selected scope.

Each percentage is `count / selected-scope total × 100`, rounded to one decimal
place. Publication percentages instead use the all-catalog total. Empty denominators
produce 0.0%, with explicit empty-state text. Rounded percentages may not sum to
exactly 100.0. Counts are current observations, not trends or behavioral analytics.

| Metric | Calculation |
| --- | --- |
| Publication | Actual published/draft/archived values across the complete authorized catalog. |
| Category | Counts of categories actually present in the selected scope; absent categories are not invented as chart rows. |
| Tourism Type | Exact Local, Common and NULL counts; NULL is Unclassified. |
| Category × Tourism Type | Exact Local/Common/Unclassified counts for each observed scoped category. |
| Coordinates | Valid complete stored pairs versus NULL pairs in scope. |
| Map-ready | Scoped records that are published, non-test, and have stored coordinate pairs. |
| Exposure | Existing Indoor/Covered/Mixed/Outdoor/Unknown values returned by identity-bound weather lookup. |
| Hours | Existing unverified/verify_required/not_supplied/NULL statuses, with NULL shown separately as Status not assigned. |

Disabled Tourism metadata is **Unavailable**, not a mass of NULL classifications.
An unavailable curation file makes exposure counts unavailable and suppresses
weather attention flags; it does not fabricate zero classified or all Unknown.

## Recommendation readiness interpretation

Shows coordinates available/missing, Tourism Type assigned/unclassified and weather
exposure classified/unknown. These are coverage indicators, not a score, ranking
editor or guarantee of visit feasibility.

The explanation retains interest/category eligibility, Local → unclassified → Common
priority, category variety and available-coordinate grouping/visit ordering. Missing
coordinates do not disqualify an otherwise eligible destination. Weather exposure
supports itinerary weather review; it is not represented as a recommendation weight.
There are no boost controls, ranking weights or personal itinerary operations.

## Geographic coverage

The page distinguishes recorded coordinate coverage from public map eligibility.
All-status views can include located archived/test records, so those are excluded
from the separate map-ready count. There is no new claim that every numeric stored
pair has independent verification provenance.

The missing-coordinate preview shows at most ten actual destinations, with category,
Tourism Type, publication status and View Destination links. The displayed total
is exact for the scope. View All Missing Coordinates opens the existing working
Destination filter with the same publication scope. No coordinates are added or
replaced; no geocoding or Gemini call is made.

## Weather and hours coverage

Weather uses `load_weather_catalog().for_place(place)`: slug, name, category and
address must match the curated record. A missing/stale identity remains Unknown.
Unknown never means Outdoor and is not inferred from category/name. The known
curated-exposure list is bounded to ten rows with links to existing provenance on
Destination detail. The sidecar is not edited.

Hours supplied but not independently verified remain Unverified. Verification
required and Not supplied use their existing explicit statuses. A NULL status is
not automatically classified as Not supplied. Raw strings and `*` values remain
unchanged on Destination details; the page does not parse or promise opening times.

Operational Context identifies Santa Rosa, Laguna and Open-Meteo as the existing
weather configuration. It explicitly does not check current provider availability.
No weather-provider call is added for decoration, and provider failure cannot make
this page fail. It does not access private cache internals or claim measured uptime.

## Needs Attention rules

Flags are deterministic data-quality review items, not errors. Each destination
appears once with all its applicable flags:

| Flag | Condition |
| --- | --- |
| Missing coordinates | Valid catalog row has a NULL coordinate pair. |
| Tourism Type unclassified | Tourism metadata enabled and actual `tourism_type` is NULL. |
| Hours require verification | `tourism_hours_status == verify_required`. |
| Hours supplied but unverified | Status is `unverified`. |
| Hours not supplied | Status is `not_supplied`. |
| Hours status not assigned | Tourism metadata enabled and status is NULL. |
| Weather exposure unknown | Valid curation file available and effective exposure is Unknown. |
| Draft destination | Actual publication status is draft. |

Unavailable inputs do not generate inferred flags. Issue selection is a real GET
filter; its option counts are computed in the selected scope. Results retain stable
slug order and display ten destinations per page. Links preserve scope and issue.
Issue counts can overlap; the All flags count is unique destinations, not the sum
of flags. Every item links to the existing Admin detail page.

## Intentionally omitted analytics and future feasibility

No registered-user totals, private user information, trip titles/notes, AI histories,
Saved/Visited places, preferences, personal alert state, popularity, visits,
generation counts, recent administrative activity, uptime percentages or trends.
No Users/Analytics/Audit Logs/Trips navigation placeholders were added.

Future aggregate trip totals and destination membership usage are feasible from
`trips`/`trip_places`, but the current services and RLS are owner-only. They require
separately reviewed Admin-authorized aggregation and privacy definitions; counting
the Admin's own trips is not a global statistic. There is no reliable lifetime
generation-event dataset. No privileged queries or new telemetry are introduced.

## Tests

Baseline: 48 existing Admin tests passed. Final focused Admin run:
`.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_admin*.py'`
— **61 tests passed**. This includes the existing Dashboard, destination-review,
login/logout and authorization checks plus thirteen new Insights tests. Python
compilation checks passed. The full application suite was not repeated.

The new tests cover scoped/global counts, percentages, observed-only categories,
Tourism matrix and NULL semantics, stored versus public map coverage, all exposure
classes, identity mismatches, unavailable curation, distinct hours statuses,
deterministic multi-flag attention, bounded previews/pagination, complete reads
beyond 100 candidates, strict enums, authentication/membership, safe links,
unavailable/empty states, shared theme/mobile assets and no mutation forms.
They also assert the weather getter is never called, even when it would fail.
Existing Admin suites cover Dashboard and Destination review regression.

## Browser verification

The real local Flask app was restarted to register the route. The user signed in
again through the existing Admin login because the development session store is
process-local. Browser checks used that signed-in session and actual catalog data;
no Admin identity was injected and no passwords, cookies, tokens or network headers
were inspected or saved.

**63 live read-only browser checks passed**, with **22 viewport screenshots**, no
runtime exceptions and 18 observed local document responses at HTTP 200. Verified:

- Catalog Insights at 1440px, 768px and 390px in Light and Dark.
- Dashboard, Destinations and Enchanted Kingdom details at desktop/mobile in both themes.
- Exactly three supported Admin navigation links with active highlighting.
- Scope changes, real attention filters/pagination and working destination links.
- Category counts summing to scoped totals and percentages within 0–100%.
- GET-only page forms, native mobile keyboard navigation, readable bars and no
  page-level horizontal overflow or brand/action overlap.

Observed current catalog values (not hardcoded application constants):

| Metric | Published scope | All-record scope |
| --- | ---: | ---: |
| Records | 34 | 48 |
| Stored coordinate pairs | 19 | 31 |
| Missing coordinate pairs | 15 | 17 |
| Tourism Type assigned | 18 | 20 |
| Local | 7 | 9 |
| Common | 11 | 11 |
| Unclassified | 16 | 28 |
| Indoor | 2 | 2 |
| Covered | 0 | 0 |
| Mixed | 1 | 1 |
| Outdoor | 0 | 0 |
| Unknown exposure | 31 | 45 |
| Hours unverified | 16 | 18 |
| Hours verification required | 2 | 2 |
| Hours not supplied | 0 | 0 |
| Hours status not assigned | 16 | 28 |

Publication Overview reports 34 published, 2 draft and 12 archived across all 48
records regardless of the selected quality scope. Published categories observed:
Attractions 5, Dining 6, Heritage 9, Industrial Tourism 4, Nature 1, Shopping 9.
Accommodation is absent from this scope and is not added as a zero-value category.
It appears in All scope because an actual archived catalog record uses it.

The browser restores the starting theme and clears viewport emulation afterward.
The real server and signed-in browser remain available at
`http://127.0.0.1:5000/admin/insights`. No catalog mutation was submitted.

Evidence and reproduction script:

- [Measured checks and all scope distributions](browser-results.json)
- [1440px Light](screenshots/insights-1440-light.png)
- [1440px Dark](screenshots/insights-1440-dark.png)
- [768px Light](screenshots/insights-768-light.png)
- [390px Light](screenshots/insights-390-light.png)
- [390px Dark](screenshots/insights-390-dark.png)
- [Weather coverage, mobile Dark](screenshots/weather-coverage-390-dark.png)
- [Needs Attention, mobile Dark](screenshots/needs-attention-390-dark.png)
- [Existing Dashboard](screenshots/dashboard-1440-light.png)
- [Existing Destination review](screenshots/destinations-390-dark.png)
- [Existing Destination detail](screenshots/destination-detail-1440-light.png)
- [Read-only browser verification script](browser_checks.py)

Screenshots show viewport evidence; complete document dimensions are also measured
to detect overflow. The browser script uses the isolated verification browser's
local CDP port 9236, local GET navigation, screenshots and presentation controls.
The app performs only its existing authorized catalog/membership reads.

## Database, security and limitations

Read-only aggregation only. No SQL, migration, schema/grant change, catalog update,
Tourism/coordinate/weather change or destructive operation is part of this phase.
Destination CRUD remains unavailable. The new route supports GET/HEAD/OPTIONS only.

All insights remain behind existing verified authentication and fresh Admin
membership checks. Query keys, repeated values, scope, issue and canonical page
numbers are validated before catalog access. Existing private/no-store headers,
safe errors, CSRF/logout and request-authority removal during Jinja rendering remain.
No secrets, tokens, auth metadata or private account/trip fields are projected.

The shared reader's 2,000-row ceiling and non-atomic multi-page reads remain explicit
limitations. The catalog/curation state can change between observations. Empty,
unavailable and Unknown are separate states. Coverage cannot establish opening,
cost, routing feasibility, safety or destination popularity.

## Git status

The large intentional worktree is preserved. No staging, commit, push, reset,
restore or Git clean operation is performed. Phase changes remain unstaged and
new service/template/test/report files untracked. Short status is captured in
[git-status.txt](git-status.txt). `git diff --check` passed (exit 0); existing CRLF
conversion notices and the preexisting `.pytest_cache` inspection permission warning
do not indicate patch errors.

ROSAGO ADMIN PHASE 3 CATALOG INSIGHTS: READY FOR LIVE VERIFICATION
