# RosaGo Admin Phase 2: destination management review

Completed 1 November 2026 (Asia/Manila). References: [Admin audit](../AUDIT.md)
and [Phase 1 report](../phase1-dashboard/REPORT.md).

**Implemented the supported catalog-review operations. Destination writes remain
unavailable.** The existing repository grants Admin catalog SELECT access only;
it provides no authorized destination mutation RPC or application write policy.
Under this task's no-schema-change constraint, enabling Save/Create/Publish/Archive
would require inventing or bypassing an authorization capability. None was added.

## 1. Architecture and operations inspected

Reviewed Admin routes, authentication/authorization, `admin_places_service.py`,
`Place`/`PlacesService`, destination templates, Phase 1 dashboard service, numbered
migrations, Tourism source rules, coordinate checks and weather-sidecar identity
validation. Baseline: **36 Admin tests passed** before changes.

| Operation | Before | Phase 2 result |
| --- | --- | --- |
| List destinations | Read-only status filter and simple management cards | Responsive management table/cards, complete summary, literal search and combined filters. |
| Inspect destination | Core fields and weather lookup | Full available Tourism provenance/raw hours, coordinate state, weather and publication details. |
| Open Edit | Editable-looking preview with disabled save controls | Explicit read-only field inspection; inputs are readonly and selects disabled. |
| Create | Blank Add preview without write support | Explicit creation-unavailable page; no invented defaults or active create action. |
| Save/update | Unsupported | Not implemented; POST/PUT/PATCH/DELETE remain 405. |
| Publish/archive/restore/delete | Unsupported | No active actions, fake confirmation dialogs or permanent deletion. |
| Weather editing | Repository-curated sidecar only | Read-only exposure/provenance; no file writer. |

All reads use the existing `places` table through the verified request-owned client.
No second catalog/database was introduced. Catalog filtering operates on a bounded
transient read of that same table, not on an Admin-maintained copy or import file.

The list reads complete batches of 200 with exact counts and an explicit maximum
of 2,000 records, then filters and displays 25 rows per page. Incomplete/truncated
responses, duplicate identities, changed totals, malformed values and an oversized
catalog are unavailable, never displayed as complete partial counts. Query text is
matched literally in Python; it is never interpolated into PostgREST OR/filter syntax.

## 2. Files changed

| File | Change |
| --- | --- |
| `admin_places_service.py` | Coordinate/type/category values on list records; optional full Tourism detail projection; shared metadata validation; complete catalog summary, literal filtering, paging and query validation. Retains the existing bounded page-read API. |
| `admin_routes.py` | Strict search/filter argument parsing, complete list service integration, preserved pagination filters and Tourism-enabled detail reads. Authentication and login/logout behavior unchanged. |
| `templates/admin/places.html` | Administration header, actual all-catalog summaries, GET search/filter form, responsive management table, explicit read-only state and precise pagination. |
| `templates/admin/place_detail.html` | Basic, Tourism, location, weather, publication and record-information sections; safe existing map link where eligible. |
| `templates/admin/place_form.html` | Grouped read-only Edit preview, controlled provenance, unchanged recorded values and explicit creation blocker. |
| `static/css/admin.css` | Compact management/filter/table styling, structured mobile records, metadata badges, detail layout and readonly controls in both themes. |
| `tests/test_admin_destinations.py` — new | Twelve focused service and route tests for filtering, exact-complete reads, metadata, coordinate validation, shared User/Admin values and rejected mutations. |
| `tests/test_admin_places.py` | Update existing projections/HTTP fixtures for coordinates, optional Tourism fields and exact-complete list requests. |
| `tests/test_admin_frontend.py` | Update detail fixtures and assertions for honest read-only/Create-unavailable presentation. |
| `tests/test_admin_authorization.py` | Empty catalog HTTP fixture now supplies its exact zero count, required by the complete list contract. |
| This directory | Live browser verification script/results, 22 screenshots, report and Git status. |

No changes were made to User pages, `place_model.py`, `places_service.py`,
recommendation/geography modules, authentication/OTP/recovery code, dashboard
behavior, database migrations or destination/curation data in this phase.

## 3. Destination list features

- Search by destination name, address, RosaGo category (including the Industrial
  Tourism display label) or available Tourism category. Matching is case-insensitive
  literal substring matching, with a 150-character bound.
- Combine publication status, RosaGo category, Local/Common/Not classified, and
  with/missing coordinate filters. Applying filters resets pagination; page links
  preserve the selected search and all filters. Clear Filters returns to the full list.
- Complete all-catalog summary for Published, Draft, Archived, Local, Common and
  missing coordinates. These are not counts from the currently visible page.
- Desktop columns: destination/address, RosaGo category, Tourism Type, Tourism
  category, coordinate state, publication status and compact View/Edit preview actions.
- Below 1,000px, rows become structured management cards with explicit field labels.
  No tourist imagery or Explore cards were reused.
- NULL Tourism Type displays **Not classified**. Disabled Tourism metadata displays
  **Unavailable**, and its filter is omitted rather than pretending NULL values exist.
- Empty results, unavailable data, current matching count and page boundaries are
  explicit. No unsupported Create/Publish/Archive/Restore buttons were advertised.

## 4. Details, read-only fields and publication workflow

Details separate RosaGo Category from original Tourism Category. Available Tourism
fields include exact Local/Common/NULL, raw opening/closing text, current hours
status, source label and worksheet row. Raw values, asterisks and source whitespace
are preserved; there is no new verified-hours state or automatic classification.

Location shows the recorded pair or **Coordinates not yet provided.** A published,
located, non-test destination can link to the existing RosaGo Map with its slug.
Draft/archived destinations do not link to a public feature that excludes them.
No geocoder, routing request or coordinate generator is called by Admin details.

Weather Exposure uses the existing exact-identity `for_place()` lookup and source
provenance partial. Known Indoor/Covered/Mixed/Outdoor values and Unknown remain
unchanged. A name/category/address mismatch continues to resolve to Unknown.
Future weather administration should retain reviewed source evidence and identity
binding through a separately designed curation workflow, not request-time JSON writes.

Publication explains the actual state: Draft is not public; Published is available
through published-catalog services; Archived is retained but inactive in normal User
results. State changes and confirmations are omitted because no safe action endpoint
exists. No permanent deletion is implemented.

**All destination fields are intentionally read-only in this phase**, including
basic text, categories, coordinates, Tourism values/source and publication status.
The Edit preview permits inspection/copying of recorded values, not editing that
cannot be saved. Source/provenance and weather exposure remain controlled review
data. No dirty-form warning is installed because the controls cannot be changed
through the UI. The preview contains no destination submit form; the only POST
form is the existing secure shell Logout form.

## 5. Validation and security

Server-side validation covers both filter inputs and returned catalog values:

- Exact allowed query keys; no repeated values; canonical bounded integer offsets;
  bounded literal search with control/surrogate rejection.
- Publication: only published/draft/archived; RosaGo Category: existing seven-category
  enum; Tourism filter: Local/Common/unclassified; coordinates: with/missing.
- Names 1–150 characters, address 1–500, description 1–3,000, with existing trim rules;
  supported slug format and timezone-aware timestamps.
- Finite numeric latitude −90…90 and longitude −180…180; Boolean/nonfinite/out-of-range
  values rejected; both coordinates present or both NULL.
- Shared `PlacesService` Tourism validator: exact Local/Common/NULL;
  unverified/verify_required/not_supplied/NULL hours statuses; bounded raw text and
  provenance; integer source row 2–1,048,576. Raw source text is not normalized.
- Escaped display of catalog/search/source text; no raw HTML interpretation,
  user-controlled database expression or external image fetch.

These validate reads and filter inputs. No write-validation or successful-update
test is claimed: a mutation endpoint was deliberately not implemented. Unsupported
methods return 405 for both members and nonmembers, without calling catalog services.
Read pages still require normal authentication and fresh Admin membership; nonmembers
receive 403 before catalog reads. Provider failures remain sanitized and pages private.

Existing CSRF, same-origin, login/logout, session revocation, template authority
isolation, Supabase RLS, OTP and recovery behavior is unchanged and covered by existing
Admin/login tests. No service-role client, membership bypass, account directory,
private notes, browser-local travel preferences or AI histories were added.

## 6. User-side propagation and recommendation safety

Admin and User services read the **same `places` table**. The enriched Admin service
reuses the existing Tourism metadata validator. A focused test verifies that Admin
and public `Place` models return identical name/category/address/location and all
Tourism values from the same record. Existing public-only publication filtering is
unchanged; archived records remain outside normal User discovery.

There was no allowed update to propagate in this phase. No real record was edited
as a test, and no successful-CRUD propagation claim is made. Future authorized
mutations must write that same table and preserve the existing public service contract.

Recommendation code and policy were untouched: category/interest eligibility,
Local → unclassified → Common priority, deterministic tie-breaking, category
coverage and incremental geographic grouping/visit ordering remain intact.
Gemini is not called to determine any catalog value. NULL does not become Common;
missing coordinates do not become invented locations. No weather/source metadata
was changed to improve the UI or tests.

## 7. Live read-only verification

Started the real local Flask app at `http://127.0.0.1:5000`. The user signed in with
an existing Admin account in a separate verification browser. Checks used that
authorized session against the real app and current catalog; they did not inject
an Admin session or use mocked authentication for live evidence. No credentials,
cookies, tokens or network headers were inspected or saved.

Live catalog summary observed during verification:

| Scope: all visible catalog statuses | Count |
| --- | ---: |
| Total | 48 |
| Published | 34 |
| Draft | 2 |
| Archived | 12 |
| Local | 9 |
| Common | 11 |
| Missing coordinate pair | 17 |

These are observed values, not UI constants. Local/Common and missing-location
counts include all statuses, as labeled in the list; the Phase 1 dashboard's
published-only quality metrics retain their separate scope.

| Requested destination | RosaGo / Tourism distinction | Coordinates | Weather |
| --- | --- | --- | --- |
| Enchanted Kingdom | Attraction; Local; Theme Park / Recreation | 14.281947, 121.095394 | Mixed, with existing source provenance. |
| Kanin Club | Dining; Common; Filipino Restaurant | NULL pair | Unknown. |
| Arambulo Ancestral House | Heritage; Not classified; Tourism category/source not supplied | NULL pair | Unknown. |

Enchanted Kingdom's raw hours remained `11:00 AM*` / `8:00 PM*`, unverified,
source worksheet row 2. Kanin Club remained `10:00 AM*` / `10:00 PM*`, unverified,
row 19. Arambulo's missing Tourism data stayed unset. Nothing was inferred from names.

Final live browser run: **55 checks passed**, **22 screenshots**, no runtime
exceptions, and 20 observed local document responses were HTTP 200. Checked the
list at 1440/768/390px in Light and Dark; the three requested detail pages and
Enchanted Kingdom's read-only Edit preview at desktop/mobile in both themes;
real combined filters and searches; all publication states; native mobile keyboard
navigation; no page overflow; and the existing Phase 1 Dashboard. Inter loaded.
The original theme was restored after verification, and viewport emulation cleared.

The browser script only navigates via local GET requests and changes presentation
controls. No destination POST/PUT/PATCH/DELETE, save, publication action, geocoding,
weather write or AI action was performed. Screenshots show viewport evidence;
complete document widths and full detail-section observations are recorded in
[browser-results.json](browser-results.json). Very tall form screenshots required
viewport capture rather than the browser's unreliable full-page compositor.

Evidence:

- [Destinations, 1440px Light](screenshots/destinations-1440-light.png)
- [Destinations, 1440px Dark](screenshots/destinations-1440-dark.png)
- [Destinations, 768px Light](screenshots/destinations-768-light.png)
- [Destinations, 390px Dark](screenshots/destinations-390-dark.png)
- [Enchanted Kingdom, 1440px Light](screenshots/enchanted-kingdom-1440-light.png)
- [Kanin Club, 390px Dark](screenshots/kanin-club-390-dark.png)
- [Arambulo, 390px Light](screenshots/arambulo-ancestral-house-390-light.png)
- [Read-only Edit preview, 1440px Light](screenshots/edit-preview-1440-light.png)
- [Read-only Edit preview, 390px Dark](screenshots/edit-preview-390-dark.png)

The real local server and signed-in verification window are left available for
the user's review. No production/deployment configuration was changed.

## 8. Tests

| Focused suite | Result |
| --- | --- |
| `test_admin*.py`, baseline | 36 passed. |
| `test_admin*.py`, final | **48 passed**. |
| `test_places_routes.py` | 23 passed. |
| `test_places_service.py` | 16 passed. |
| `test_itinerary_recommendations.py` | 12 passed. |
| `test_itinerary_geography.py` | 8 passed. |
| `test_personalized_recommendations.py` | 5 passed. |
| `test_login.py` | 26 passed. |
| `test_map_routes.py` | 9 passed; 2 failures and 1 error tied to existing User template/test assumptions. |
| Live browser checks | 55 passed. |
| `git diff --check` | Passed, exit 0; existing CRLF conversion warnings only. |

New Admin tests cover all filter types/combinations and requested search fields,
NULL versus unavailable metadata, stable complete pagination and filter links,
read-only detail/preview rendering, raw source preservation, malformed enums,
coordinates/ranges/pairs, escaped catalog text, unpublished map-link exclusion,
consistent User/Admin record values, authorization and denied mutation methods.

The three Map-suite issues are outside changed Admin files:

1. `test_shared_layout_conditional_local_assets_and_active_map` expects only the
   older stylesheet list, omitting the existing shared theme stylesheet.
2. `test_hostile_marker_text_cannot_break_json_or_create_markup` expects five scripts,
   while the current User shell contains seven.
3. `test_shared_template_autoescaping_remains_enabled` renders the inherited User
   template directly without the existing `website_settings` context.

Neither the User templates nor those tests were changed to mask these results.
The other map route/data tests pass. The full massive suite was not run.

## 9. Database status, limitations and next boundary

No SQL was executed; no schema, migration, grants or records were changed. No
migration 0010/0011 or transition/import SQL was rerun. No live mutation was used
to probe permission or test CRUD. The repository exposes no supported destination
write capability; deployed ACLs were not independently enumerated through SQL.

The main blocker remains an authorized destination mutation boundary. Enabling
actual updates/create/publication later requires a separately reviewed backend
authorization/concurrency design and explicit permission to deploy the necessary
database capability. Persistent audit architecture remains a later phase as
requested. This phase neither creates it nor uses its absence to weaken permissions.

The 2,000-record limit is explicit; multi-page reads are not an atomic snapshot.
Tourism columns require the existing deployment feature flag. Weather editing
remains reviewed curation, and coordinate verification provenance is still not a
separate database field. No dirty-form workflow, mutation confirmation or successful
update test is installed before a real save operation exists.

## 10. Git status

The existing large intentional worktree is preserved. No stage, commit, push,
reset, restore or Git clean operation was performed. Changes remain unstaged;
the new test and report/evidence directory remain untracked. Captured short status:
[git-status.txt](git-status.txt). Git's existing `.pytest_cache` inspection permission
warning did not block tests or diff validation.

ROSAGO ADMIN PHASE 2 DESTINATION MANAGEMENT: READY FOR LIVE VERIFICATION
