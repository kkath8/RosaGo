# RosaGo Admin finalization: oversight audit and implementation plan

Audit date: 1 November 2026 (Asia/Manila). Scope: current local working tree,
including existing uncommitted work. This is an inspection and planning deliverable;
none of the proposed features or database changes have been implemented.

The Admin foundation is a protected, read-only catalog workspace. The highest
priority is to complete its catalog data model and management interface, then
introduce narrowly authorized, audited destination writes. Cross-user account and
trip reporting requires separate backend authorization work. User-side pages and
browser-local personal state must not become Admin data sources.

## 1. Current Admin architecture

- Flask registers the `admin` blueprint from [admin_routes.py](../../admin_routes.py)
  in [app.py](../../app.py), with `/admin` as its prefix.
- [admin_auth.py](../../admin_auth.py) layers fresh membership authorization over
  the normal authenticated request context; it removes `g.auth` during rendering.
- [admin_authorization_service.py](../../admin_authorization_service.py) calls
  `rosago_is_admin()` using the request-owned authenticated client.
- [admin_places_service.py](../../admin_places_service.py) performs bounded,
  validated catalog reads and exact status counts. It has no write operations.
- Admin has its own HTML shell and [admin.css](../../static/css/admin.css), and
  reuses the shared icon macro. There is no dedicated Admin JavaScript module.
- Public destination discovery uses `PlacesService` and `Place`; Admin uses
  separate `AdminPlace`/`AdminPlaceDetail` types with fewer fields.
- Weather exposure is a reviewed JSON sidecar, not part of the `places` table.

Architecture gaps: no Admin write service/RPC, no destination-management audit
store, no cross-user account projection, no aggregate trip service, and no shared
Admin theme integration. Existing disabled controls are previews, not working CRUD.

## 2. Existing Admin routes

All routes also receive Flask's normal HEAD/OPTIONS behavior where applicable.

| Route | Explicit methods | Current behavior |
| --- | --- | --- |
| `/admin/login` | GET, POST | Normal password sign-in followed by fresh membership check; signed-in nonmembers get an explanatory denial. |
| `/admin/logout` | POST | CSRF/origin-protected local normal-session revocation and cookie cleanup. Membership is deliberately unnecessary for logout. |
| `/admin` | GET | Four destination counts: total, published, draft, archived. |
| `/admin/places` | GET | Status filtering and offset pagination; 25 rows ordered by unique slug. |
| `/admin/places/new` | GET | Add Destination preview, with disabled save/publish buttons. |
| `/admin/places/<slug>` | GET | Read-only destination details, weather exposure lookup, disabled lifecycle actions. |
| `/admin/places/<slug>/edit` | GET | Prefilled Edit Destination preview; nothing can be saved. |

All destination routes use `admin_required`. Destination POST attempts currently
return 405. There are no Users, Insights, Analytics, System/Weather, Audit Logs,
or Admin Account routes. Unknown/repeated filter arguments, unsupported statuses,
and noncanonical/out-of-range offsets are rejected.

## 3. Existing Admin templates

| Template in `templates/admin/` | Purpose and limitation |
| --- | --- |
| `base.html` | Fixed desktop sidebar, Admin badge, topbar, Dashboard/Destinations links, View User Side and logout. No shared fonts/theme includes. |
| `dashboard.html` | Real status metrics, unavailable state, destination-management link, preview Add action. |
| `places.html` | Two-column management cards with status badges and View/Edit links; status filters and Previous/Next. No search or category/type/coverage filters. |
| `place_detail.html` | Core destination fields, timestamps, image URL as text, weather exposure; no Tourism fields or stable destination ID. |
| `place_form.html` | Core field previews using a display group, not a submit form; no Tourism fields or weather editor. |
| `lifecycle.html` | Explains draft/published/archived states; does not change state. |
| `login.html` | Separate Admin sign-in page and existing recovery link. |
| `access_error.html` | Membership/authorization error page without granting access. |
| `catalog_error.html` | Missing-record and provider-unavailable presentation. |

The Add/Edit headings and links can suggest capabilities beyond the disabled
controls. Until writes are complete, retain explicit preview/read-only labeling.
The catalog-error title also contains a literal question-mark separator that
should be normalized during presentation work.

## 4. Existing Admin services

`destination_counts()` makes four exact HEAD requests. It rejects missing,
negative, Boolean, malformed or noninteger counts; errors are unavailable, never
invented zero. Each count is a separate statement, so the cards are not one
consistent database snapshot.

`list_destinations()` projects `name, slug, category, status, address, updated_at`.
`get_destination()` adds description, coordinates, image URL and creation time.
Both validate response structure and values; `_execute()` disables retries and
sanitizes provider failures. The detail type does not include `id` or any Tourism
columns. Add a stable UUID to the future management contract rather than using a
mutable slug as write identity.

`load_weather_catalog().for_place(place)` is already used by Admin detail. It
checks slug plus exact name/category/address before returning known exposure.
Admin has no service to inspect weather-provider status or compute coverage.

## 5. Current authentication and authorization

Evidence: `admin_auth.py`, `admin_authorization_service.py`, `admin_routes.py`,
`auth_helpers.py`, `normal_auth_flask.py`, `normal_auth_coordinator.py`, and
migrations 0008/0009 and their design notes.

- Admin sign-in uses the existing normal-auth adapters and server-side session
  store; it does not create a separate privileged session or service-role client.
- The browser holds an opaque session reference. Credentials and refresh handling
  stay in the normal-auth architecture. Cookie identity/role flags are not authority.
- Every protected Admin request checks current membership using a zero-argument
  RPC and accepts only a literal Boolean result. Denied membership returns 403;
  authorization-provider failures return a fixed 503.
- `admin_memberships` grants authenticated callers only own-row SELECT. The
  predicate is SECURITY INVOKER with an empty search path. Membership provisioning
  and revocation are trusted-operator tasks, not registration/profile actions.
- Migration 0009 adds only an Admin SELECT policy on `places`; it does not permit
  INSERT/UPDATE/DELETE. Published-only public reads remain in place.
- Login validates exact fields, no files, one value per field, a 30-minute CSRF
  token and exact Origin. Logout validates the normal-session CSRF and Origin.
- `render_admin_page()` hides request authority from Jinja. Admin responses receive
  `Cache-Control: private, no-store` and `Referrer-Policy: same-origin` in `app.py`.
- Revoked members can still log out. Logout revokes local normal authority; do not
  label it as global sign-out of every provider/device session.

Deployment status is not established by source files. Some migration headers/design
notes say review-only/unapplied and older notes predate the separate Admin login.
The code is authoritative for route behavior; a future operator check must establish
actual deployed policies, grants, membership and schema. No SQL or live Admin login
was performed for this audit.

## 6. What Admin already supports

Fresh authenticated membership checks, read-only all-status catalog access when
0009 is deployed, exact status counts, bounded pagination, status filtering,
core destination detail inspection, nullable coordinate display, weather exposure
inspection, lifecycle explanations, escaped catalog text, explicit test-record
disclosures, private error handling, normal logout and the existing recovery entry.

Basic responsive rules exist: the fixed sidebar becomes a stacked mobile section
below 700px, detail/list columns collapse, and metrics collapse at small widths.
Source inspection does not establish browser-level accessibility or overflow quality.

## 7. Missing features and priority

1. **P0 — catalog management foundation:** stable IDs; complete Tourism projection;
   classification/location/weather coverage; practical table/list filtering;
   explicit read-only versus writable states; deployed-schema verification.
2. **P0 — secure writes and audit:** validated create/update/publication actions,
   database authorization, stale-edit detection, transactional audit, and lifecycle
   confirmations. A styled Save button is insufficient.
3. **P1 — shared visual identity:** Inter interface, Sora wordmark, shared palette,
   consistent borders/radii, Light/Dark support and usable mobile management.
4. **P1 — operational read-only views:** recommendation inputs, catalog analytics,
   current city weather and effective weather-metadata coverage.
5. **P2 — protected aggregates and account oversight:** minimal Users and aggregate
   Trips/Insights only after narrowly scoped backend capabilities exist.
6. **P2 — Admin account:** own name/email display, optional own-name edit, appearance,
   recovery link and existing logout. No travel-preference controls.

## 8. User-side features that need Admin oversight

| User feature / evidence | Management counterpart |
| --- | --- |
| Explore `/places`, place details, `/api/places`; `places_service.py`, `place_search.py`, `templates/places/` | Manage the same published catalog, descriptions, application category, source and publication status. |
| Map `/map`, `/api/route`; `routing_service.py`, `static/js/map.js` | Coordinate coverage and missing-pin queues; never assign city-weather coordinates to destinations. Routing availability is separate from coordinate availability. |
| Planner/recommendations; `recommendation_engine.py`, `itinerary_selection_policy.py`, `itinerary_geography.py` | Read-only quality view of eligible inputs, Tourism tiers and coordinate gaps. No per-user recommendation manipulation. |
| Weather review; `itinerary_weather.py`, `weather_proposal.py`, `destination_weather_metadata.py` | Effective curated exposure coverage and city-provider availability; no automatic exposure/category inference. |
| Real saved trips; `trip_service.py`, `user_features.py` | Aggregate stored trip and destination-membership usage only after a protected aggregation boundary exists. |
| Alerts; `alerts_service.py`, `user_features.py`, `/user/alerts` | City weather and provider availability; no private trip reminders or individual read/dismiss states. |
| Profile/settings; `profile_service.py`, `settings_service.py`, `static/js/account-management.js` | Minimal account directory only with authorized projection; own Admin account controls can reuse own-profile service. |
| AI explanations/adjustments; `gemini_service.py`, `assistant_store.py` | Configuration/availability disclosure if useful, not conversation inspection or AI-controlled Tourism classifications. |

Current recommendation behavior must stay intact: interest eligibility first;
Local → unclassified → Common priority; category coverage; incremental geographic
comparison of comparable located candidates; deterministic UUID ties; practical
visit ordering. Missing-coordinate candidates remain eligible. No repeated OSRM
calls are part of selection. Gemini may explain or interpret supported requests,
but does not assign Local/Common or supply invented locations/hours/exposure.

Ranking is `category-interest-tourism-v2`; selection is
`pace-count-category-tourism-cluster-v3`. Persisted preview compatibility uses the
separate `category-interest-v1` wire identifier. An Admin policy explanation must
not change any of these constants or imply that their identifiers are equivalent.

## 9. User-only features that must not be exposed

Keep Saved Places, Visited Places, private notes, Trip Bag, personal Budget Planner,
travel/default preferences, personal itinerary editing, and personal alert
read/dismiss state outside Admin. `static/js/personal-state.js` stores these in
browser-local scoped state; no organization-wide reporting dataset exists for them.
Do not collect them to populate Admin analytics.

Names are in `profiles`; email is authoritative in Auth. Profile bio/home/city,
avatar options and travel defaults include local-only presentation data, not an
account directory. `settings_service.py` also keeps display settings in the
browser session. Neither store is an Admin oversight source.

Assistant history is bounded process-local state keyed by verified user and auth
session in `assistant_store.py`. It must remain private and must not be scraped
or persisted for an Admin conversation view. Operational aggregates, if added,
must exclude prompts, answers, private notes, trip names and user identifiers.

## 10. Data/backend availability and feature matrix

Availability meanings:

- **A:** data/service exists within the current authorized boundary. A new Admin
  projection, calculation or page may still be needed; this does not mean the UI exists.
- **B:** underlying records exist, but a new restricted backend aggregation or
  projection/authorization capability is required. Existing Admin queries cannot
  safely provide it across users.
- **C:** no reliable existing dataset or supported capability. Do not fabricate it.

“Schema change” includes new database functions, policies or grants, even if no
new table columns are necessary. All deployment claims remain conditional on
operator verification of the target environment.

| Feature | Current state | Admin need | Data available? | Schema change? | Recommended action |
| --- | --- | --- | --- | --- | --- |
| Total/published/draft/archived | Four exact counts already displayed | Dashboard and drilldowns | A: `places` | No, if 0008/0009 deployed | Retain; label total as all statuses, not active. |
| Local/Common/unclassified | Public model supports it; Admin projection omits it | Counts, badges, filters | A: 0011 columns when deployed/enabled | No new columns; verify 0011 | Extend explicit projection; never infer unset as Common. |
| Category distribution | Core category available | Dashboard/analytics | A: `places.category` | No | Aggregate complete authorized data, not one 25-row page. |
| Coordinate present/missing | Detail pairs displayed | Quality queues and recommendation oversight | A: `places` pairs | No | Count complete valid pairs; label recorded coordinates, not independently verified. |
| Weather exposure coverage | Detail sidecar lookup only | Effective known/unknown/unavailable counts | A: sidecar plus matching catalog identities | No for read-only coverage | Use `for_place()`; distinguish unavailable sidecar from known zero. |
| Core destination edit/create | Preview only, GET routes | Save validated records | A fields; B write capability | Yes: write authorization/RPC and audit storage | Implement only with audited, authorized transaction. |
| Raw Tourism hours/status/source | Stored in model, absent from Admin | Human review and correction | A if 0011 deployed | No new columns; writes need above boundary | Preserve raw text; offer only existing statuses. |
| Publication/archive/restore | Status read; actions disabled | Explicit lifecycle actions | A state; B mutation | Yes: same write/audit capability | Prefer archive over delete; confirm user-visible effects. |
| Weather metadata editing | Reviewed repository file | Curation workflow | A records, no runtime editor | No for repository workflow; yes if future DB-backed editor | Keep runtime read-only initially; do not write deployment files from requests. |
| Registered-user count | Not available to Admin | Optional operational metric | B: `auth.users`, not `profiles` count equivalence | Yes: narrow count capability | Defer; never expose Auth rows wholesale. |
| Minimal Users directory | No screen/service; profiles own-only | Identifier, names, optional email/status | B: protected Auth/profile projection | Yes: restricted function/permissions | Return an exact allowlist, bounded pagination; no account actions initially. |
| Saved-trip count | Own-user trip service only | Cross-user aggregate | B: `trips` | Yes: aggregate capability | Count existing persisted trips; define deletion/window semantics. |
| Destination popularity | No Admin query | Stored trip-membership counts | B: `trip_places` + catalog | Yes: aggregate capability | Label “trips containing destination,” not visits or recommendation impressions. |
| Trip category usage | No Admin query | Aggregate catalog categories in saved memberships | B: `trip_places` + `places` | Yes: same aggregate capability | Distinguish current category from historical category at save time. |
| Generation activity/history | Current draft state/revision exists | Optional activity metrics | C for lifetime event count; B for current draft-state counts | New events needed for history; RPC for state totals | Do not treat revision, previews or saved trips as generation event counts. |
| Current city weather | Public service/API exists | System weather panel | A: `WeatherService` | No | Show real source/time or unavailable; use existing cache. |
| Provider uptime/history | No durable monitor | Optional future monitoring | C; latest weather availability is A | Storage/telemetry for history | Show “available/unavailable on latest check,” not uptime percentages. |
| Administrative activity | No domain audit store | Recent changes and actor/target history | C until introduced | Yes: audit table + protected reads/writes | Build alongside first destination mutation. |
| Admin own account | Normal Auth and own profile available | Own name/email, appearance, recovery/logout | A | No for own-profile reuse | Keep membership management and travel settings out. |
| Local personal data | Browser-local/session/private chat | No Admin need | C for central analytics; private by design | None recommended | Exclude from Admin. |

Dashboard defaults: publish the four existing status counts; add Local/Common/
unclassified, coordinate and effective weather counts only after complete-data
aggregation is implemented. Prefer published destinations as the default quality
denominator, with an explicit all-status filter. Every tile must identify its
scope and observation time; missing capability must not appear as zero.

## 11. Database/schema gaps and source-data limits

| Existing source | What it establishes | Gap/constraint |
| --- | --- | --- |
| `0001_profiles.sql` | UUID, nullable first/last names, profile creation time; own SELECT/name UPDATE | No email/account status; profile creation is not necessarily Auth signup time. |
| `0002_places.sql` | Catalog, statuses, coordinate pair/range checks, timestamps, published public SELECT | No application writes; original category constraint omits industrial and original published check requires coordinates. |
| `0003_trips.sql` | Owner-private trips and memberships; unique trip/place membership; restricted deletes and mutations | Admin membership does not grant cross-user visibility. No visit telemetry or historical category snapshot. |
| `0004`–`0007`, `0010` | Draft/preferences/preview lifecycle and itinerary foundations under own-user RLS | No Admin aggregate authorization or durable generation-event log. |
| `0008`/`0009` | Membership predicate and Admin all-status catalog SELECT | No catalog write rights, user directory or global trip read rights. |
| `0011_places_tourism_metadata.sql` | Type/category/raw hours/status/source/source row | Existing metadata foundation, not a new schema requirement if deployed. No verified-hours status. |
| `data/santa_rosa_places/publish.sql` | Separate reviewed transition drops published-coordinate requirement and adds industrial support | Lives outside numbered migrations; target environment may differ from original schema. Never rerun it as part of Admin UI startup. |
| Tourism transition plan/review SQL | Reviewed import proposal and provenance | Review artifacts are not the runtime catalog or a transaction audit log. |
| Weather JSON sidecar | Exposure and verification provenance with identity binding | No DB-backed editor, version history UI or automatic identity repair. |

The local `places.json` is an older 28-record publication artifact: 9 heritage,
4 industrial, 6 attraction, 9 shopping; all coordinates are NULL. These are file
contents, not current Supabase counts. The review-only Tourism plan has 20 rows
(9 Local, 11 Common); it is also not a runtime distribution.

The weather file has 28 records: 25 unknown, one mixed and two indoor. Known rows
describe Enchanted Kingdom, SM City Santa Rosa and Robinsons Sta. Rosa with specific
identity/address values. An offline lookup against the older 28-place seed returns
**28 unknown**, because the required identities do not match. This is intentional
fail-safe behavior, not permission to change identities or classifications. The
Admin coverage page must join against the actual current catalog and distinguish
unmatched/stale identities from effective known exposure. No live coverage count
has been established in this audit.

`Place` has no coordinate verification provenance flag/date. Numeric valid pairs
are existing recorded coordinates; do not invent a “verified coordinates” count.
If independent verification tracking becomes a requirement, propose dedicated
provenance in a later reviewed schema change rather than overloading Tourism source.

Minimum future database work for editable catalog management is authorization/
mutation functions and audit storage. User-directory and global-trip aggregates
are optional, separately scoped database capabilities. No migration is created here.

## 12. Security considerations and proposed audit architecture

Preserve all current auth/session, fresh membership, CSRF, Origin, private caching,
template isolation, RLS, public-only discovery, recovery and OTP boundaries.
Do not add a service-role key to Flask or broaden user-table RLS for convenience.
Never expose passwords/hashes, OTPs, JWTs, refresh/recovery tokens, auth metadata
blobs or private browser preferences through responses, logs, templates or exports.

There is no durable destination-management audit log. `admin_memberships.granted_at`
records membership time only; `places.updated_at` records latest modification time
only. `recovery_diagnostics.py` emits fixed recovery categories and `CallbackLogFilter`
redacts credential-bearing callback query strings. Neither provides Admin actor,
destination target, action and structured change history. Do not repurpose them.

Smallest safe future architecture:

1. Introduce a narrowly scoped destination-mutation RPC/service boundary for
   create, update, publish, archive and restore. Derive actor from authenticated
   identity; independently verify current membership inside the database mutation.
   Allowlist fields and actions; never accept actor/owner/role from the form.
2. Use a reviewed function owner with only necessary privileges, fixed empty
   search path, qualified objects and explicit EXECUTE grants. Keep direct catalog
   writes denied to application roles. If elevated function rights are necessary,
   review them explicitly rather than assuming an invoker RPC can bypass revoked
   write privileges. No dynamic SQL or caller-chosen table/function names.
3. Lock/recheck the destination and require an expected version (a reviewed
   `updated_at` comparison can avoid a new revision column initially). Reject stale
   submissions, missing records and unauthorized states without partial changes.
4. Insert a bounded audit event in the same transaction as the successful change:
   event ID, database timestamp, actor UUID, stable destination UUID, action,
   changed-field names, and bounded allowlisted before/after public values or
   status/provenance summaries. Do not log auth data, request bodies or user trips.
   Preserve the target identity even if catalog lifecycle changes later; no cascade
   that silently erases audit history. Prefer no hard-delete action initially.
5. Audit insertion failure rolls back the mutation. Application roles cannot
   insert/update/delete audit events directly; Admin-only reads are bounded and
   authorized independently. This makes the log append-only for application roles,
   not immutable against trusted database operators. Do not claim otherwise.
6. Do not automatically retry ambiguous mutations. Return safe conflict/unavailable
   messages and require a refresh/recheck; consider a unique request identifier if
   later workflows need replay protection. Use POST/Redirect/GET after confirmed writes.

Confirm archive/publish/restore effects in accessible dialogs, with destination
name/current status and an explicit action. Closing/cancelling must make no write.
Keep saved trip references intact. Current catalog changes can invalidate preview
fingerprints and weather identity matches; warn clearly and require recuration,
without silently rewriting private itineraries or weather metadata.

For Users, propose only an Admin-authorized projection of UUID, nullable name,
email if justified, and explicitly defined creation/verification/status fields.
No generic `auth.users` read policy, arbitrary user lookup endpoint, impersonation,
password reset for others, account deletion or membership editing is in scope.
For trip insights, return aggregates only, suppress small groups where needed,
bound filters/windows and prohibit drilldown to individual owners/trips.

Deployment concerns already present: the normal-auth store is process-local and
`SESSION_COOKIE_SECURE=False` is explicitly marked for local HTTP. Shared-worker
session design and HTTPS cookie configuration require deployment review; this
audit does not change either. Browser theme state conveys no authority.

## 13. Proposed Admin navigation

Desktop: separate Admin sidebar with the existing RosaGo wordmark treatment and
visible **Admin** identifier. Primary links: Dashboard, Destinations, Catalog
Insights, System / Weather. Catalog Insights contains Recommendation Inputs and
Catalog Analytics tabs, avoiding duplicate screens for the same distributions.

Add Audit Logs when audited writes and protected reads exist. Add Users and
Trips / Insights only after their backend capabilities pass security review.
Do not ship links to dead pages or charts populated with placeholders. Account
menu: own Admin account, Appearance, View User Side, existing Logout.

Mobile: an Admin-specific compact header with a keyboard-accessible navigation
disclosure/drawer and clear current page; no tourist bottom navigation, Trip Bag,
Saved/Visited shortcuts or User account groups. Keep management filters usable,
stack actions where needed and prevent horizontal **page** overflow. Wide tables
may use a labeled contained scroll region or a compact management-row alternative.

## 14. Proposed page-by-page UI structure

Shared shell: include fonts and pre-paint theme behavior; use design tokens rather
than copying User `base.html` (which loads personal state, bag, notifications and
tourist navigation). Current Admin uses Segoe UI, red `#c0392b`, gold `#f1c40f` and
hardcoded white surfaces. User tokens use Inter, Sora for branding, brick red
`#8e3b2c`, gold `#eec35c`, cream `#fffdf8`/`#fdf6e3`, and warm borders.
Reuse those tokens and the radius language, with tighter spacing for management.

Admin currently loads no `theme_head.html` or fonts include. `theme.css` explicitly
targets public/auth components; merely including it cannot theme Admin's hardcoded
surfaces. Add scoped Admin theme styles using the same Light/Dark device preference
`rosago.theme.v1`, its existing light default, storage-failure behavior and tab sync.
Do not introduce a second conflicting theme preference or import tourist page CSS.

| Screen | Concrete structure and actions |
| --- | --- |
| Dashboard | Title/observation scope; status metrics; published quality counts; links to missing coordinates/unclassified/exposure queues; recent audited actions only when backed by events. Optional account/trip totals only after protected aggregates. |
| Destinations | Search and status/category/Tourism-type/location/exposure filters; counts with clear denominators; dense semantic table: name, category, type, status, coordinate coverage, exposure, updated time, View/Edit. Stable pagination and preserved filters. No tourist photos/cards as the primary management layout. |
| Destination detail | Stable ID/slug, lifecycle badge, basic fields, separate application/Tourism categories, Tourism type, raw hours/status, source/provenance, coordinate availability, effective weather provenance, timestamps. Separate Edit and lifecycle actions; no active controls before backend support. |
| Add/Edit destination | Real server-validated form once authorized; Basic, Tourism, Location, Media, Publication sections. Preserve submitted values on validation errors. Type accepts Local/Common/unset; hours status accepts unset/unverified/verify_required/not_supplied only. Coordinate pair optional; show source-based guidance, not invented defaults. Weather stays a separate read-only curation panel initially. |
| Catalog Insights | Published/all-status scope; category and Tourism distributions; missing-coordinate and unclassified queues; effective weather known/unknown/unavailable counts; explanatory deterministic policy. Real count tables first; charts only if useful and backed by the same exact counts. No user simulator or ranking-control sliders. |
| System / Weather | Current Santa Rosa city forecast, provider label, reported/fetched time in Asia/Manila, latest availability and unavailable state. Effective exposure table with evidence links and identity-mismatch reason. Explain city model versus destination exposure; no official emergency-warning claims. |
| Users — deferred | Minimal paginated account table with approved search/filter fields and nullable-state labels. No raw Auth JSON, local travel preferences, secrets, login-as-user or destructive account actions. |
| Trips / Insights — deferred | Scoped totals and aggregated destination/category usage, data period/definition and privacy suppression. No personal trip titles, notes, owner emails, full previews or Edit buttons. |
| Audit Logs — after writes | Filter by time/action/target/actor identifier; paginated event rows and bounded change detail. Show absence as no recorded events, never fabricate backfilled history. |
| Admin Account | Verified caller's display name/read-only email, optional own-name form using existing protected profile service, Light/Dark controls, existing recovery link and POST logout. No travel preferences or role self-service. |
| Login/errors/confirmations | Same typography/theme/brand, explicit Admin labeling, safe fixed errors, focus management, field errors, accessible confirmations, and no disclosure of credentials/provider diagnostics. |

All badges need text, not color alone. Test keyboard operation, visible focus,
200% zoom, long names/addresses, empty datasets, provider failures, and 320/390/768/
1440px viewports in both themes. Translate timestamps explicitly to Asia/Manila
instead of relabeling a stored UTC value as local time.

## 15. Recommended implementation phases

| Phase | Work | Exit criteria |
| --- | --- | --- |
| 0. Confirm deployment contract | Operator verifies deployed migration/policy/grant state, nullable published coordinates, industrial support, Tourism columns and feature flag. Review data-source boundaries and mutation/audit design. | A documented target-schema checklist; no reliance on successful published-only reads as proof of Admin all-status access. No changes are executed by this audit. |
| 1. Complete read-only foundation | Shared Admin identity/theme shell; table-based destination management; stable IDs and Tourism detail projections; bounded search/filters; real catalog/coordinate/effective-weather counts; read-only policy explanation. | Existing security tests pass; complete-data counts; no placeholder metrics; responsive Light/Dark review. This work does not require cross-user data access. |
| 2. Implement audited destination management | Separately reviewed future DB capability and isolated permission tests; validated Python write service; real create/edit forms; publish/archive/restore confirmations; concurrency and transactional audit. | Nonadmins/direct API writes denied; audit and mutation atomic; stale writes rejected; references preserved; no fabricated metadata. |
| 3. Add operations and audit presentation | Catalog Insights/System Weather plus audit table/recent activity using actual events. | Accurate scoped counts, effective sidecar lookup, provider-unavailable states, no emergency or uptime claims. |
| 4. Optional account and trip oversight | Approve exact private-data projections and aggregate definitions; add restricted backend functions and services; then Users/Trips navigation. | No personal itinerary/private-state leakage; isolated DB authorization tests; suppression and bounded aggregation. If deferred, these links stay absent. |
| 5. Final regression and deployment review | Own Admin account controls, accessibility, responsive/theme checks, User-side auth/discovery/planning/trip/weather regression, deployment configuration review. | No weakened authorization, recommendation changes, coordinate/classification imports or undocumented schema assumptions. |

## 16. Exact files likely to change in later implementation

These are future candidates, not changes performed in this task.

| Area | Existing files | Proposed new files if needed |
| --- | --- | --- |
| Admin routes/boundary | `admin_routes.py`, `admin_places_service.py`; `admin_auth.py` only for shared safe display helpers if necessary | `admin_catalog_insights_service.py`, `admin_places_write_service.py` |
| Shared Admin shell | `templates/admin/base.html`, `login.html`, `access_error.html`, `catalog_error.html`, `static/css/admin.css` | `static/js/admin.js`, `static/css/admin-theme.css` |
| Destination workflow | `templates/admin/places.html`, `place_detail.html`, `place_form.html`, `lifecycle.html`, `dashboard.html` | `templates/admin/partials/destination_filters.html`, `templates/admin/partials/lifecycle_confirmation.html` |
| Catalog/system views | `admin_routes.py`; reuse `destination_weather_metadata.py`/`weather_service.py` as dependencies without changing classifications/provider rules | `templates/admin/catalog_insights.html`, `templates/admin/system_weather.html` |
| Auditing | Future reviewed database capability, not an edit to historical migrations | `admin_audit_service.py`, `templates/admin/audit_logs.html`, a separately approved additive migration with filename/number chosen after deployment review |
| Optional cross-user oversight | `admin_routes.py` | `admin_users_service.py`, `admin_insights_service.py`, `templates/admin/users.html`, `templates/admin/trip_insights.html`; separate reviewed restricted DB functions |
| Own Admin account | `admin_routes.py`; reuse `profile_service.py` and normal recovery flow | `templates/admin/account.html` |
| Shared resources | Reference `templates/partials/fonts.html`, `theme_head.html`, `icons.html`, `static/js/theme.js`, `static/css/design-tokens.css` | Prefer scoped Admin additions; change shared resources only if an actual shared defect requires it. |
| App registration/headers | `app.py` only if new service extensions or common response handling require it | None required merely to add routes to the registered blueprint. |
| Documentation | `docs/admin-finalization/AUDIT.md` after decisions; future implementation/verification notes | Deployment checklist and approved data-contract notes. |

Preserve `recommendation_engine.py`, `itinerary_selection_policy.py`,
`itinerary_geography.py`, preview wire contracts, user trip/profile isolation,
recovery/OTP implementation, historical migrations and catalog/curation files.
Do not edit weather JSON or Tourism transition data merely to improve dashboard
coverage. New curation or schema changes are separately reviewed work.

## 17. Tests required

Existing baseline run for this audit:
`.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_admin*.py'`
— **25 tests passed**. These use offline mocks/static checks; they do not prove
live RLS, deployed migrations or browser rendering. No production mutation or
network-based verification was needed.

Required implementation tests:

- Extend `tests/test_admin_authorization.py`, `test_admin_login.py`,
  `test_admin_places.py`, `test_admin_frontend.py`: fresh membership/revocation,
  redirects/403/503, template authority isolation, private headers, strict filters,
  full Tourism projection, nullable coordinates, stable ID and unavailable counts.
- Add `tests/test_admin_places_write_service.py` and
  `tests/test_admin_destination_routes.py`: field allowlists, UUID identity, exact
  Local/Common/unset, raw-hour preservation, coordinate pairing/finite bounds,
  publication transitions, stale edits, CSRF/Origin/repeated/extra-field rejection,
  escaped rendering, sanitized failures and no automatic ambiguous-write retries.
- Add `tests/test_admin_audit.py`: correct actor/target/time/action/change allowlist,
  bounded reads, no secrets, failed-write rollback, audit-failure rollback, preserved
  history and denied direct event modification.
- Add `tests/test_admin_catalog_insights.py` and `test_admin_system_weather.py`:
  complete-data counts, published/all-status denominators, catalogs larger than one
  page, empty versus unavailable, invalid/unavailable/stale-identity sidecars,
  effective exposure versus raw row counts, real provider parsing/cache and no
  substituted sample data. Counts must not silently inherit the recommendation
  pool's 100-candidate ceiling.
- If implemented, add `tests/test_admin_users.py` and `test_admin_trip_insights.py`:
  approved projections only, Auth/profile timestamp distinction, aggregate
  definitions, privacy suppression, filter bounds and no raw user/trip disclosure.
- Add Admin theme/responsive browser checks and `tests/test_admin_theme.js` only
  if new Admin interaction code warrants it. Reuse existing theme checks. Verify
  focus/keyboard, dialogs/cancel, long content, 320–1440px, both themes and storage
  disabled; no page overflow or accidental loading of tourist personal-state UI.
- Run targeted existing recommendation/geography, Tourism identity, weather,
  profile/settings, trip and auth/recovery/OTP regressions after implementation.
  Relevant suites include `test_recommendation_engine.py`,
  `test_itinerary_selection_policy.py`, `test_itinerary_geography.py`,
  `test_personalized_recommendations.py`, `test_tourism_metadata.py`,
  `test_tourism_weather_identity.py`, `test_weather_service.py`, `test_trip_routes.py`,
  `test_user_profile_edit.py`, `test_settings.py`, and existing normal-auth,
  password-reset and email-verification tests.

Before any future DB rollout, run isolated PostgreSQL/Supabase tests under actual
anon/authenticated identities (two normal users, an Admin and a revoked Admin).
Test own versus foreign data, all-status catalog access, mutation authorization,
RPC grants/owners/search paths, audit atomicity, aggregates and denied direct
writes. Privileged fixture setup must not be mistaken for RLS verification. No
SQL test or migration was executed during this inspection task.

## 18. Blockers and decisions for implementation

1. **Live schema/grants unknown:** deployment notes are not proof. In particular,
   missing 0009 can silently make successful counts/listing published-only.
2. **No authorized catalog writes or audit store:** blocks enabling real Save/
   Publish/Archive controls until the future DB capability is reviewed and deployed.
3. **Cross-user oversight unsupported by current permissions:** Users, global trip
   counts/popularity and registered-account totals must remain deferred rather
   than using the Admin's own records or broadening RLS.
4. **Curation identity drift:** weather known rows must match current catalog
   identities; the older seed demonstrably does not. Investigate against the real
   catalog later without silently changing the sidecar or destination values.
5. **Metrics need precise definitions:** active means published; popularity means
   saved-trip membership, not visits; category usage reflects current catalog
   category; draft state is not generation history. Preview-save currently creates
   a trip then memberships via `user_features.save_places()` and may produce a
   partial saved trip. It does not mark an authoritative draft-save event, so do
   not derive successful generations/saves from `saved_at` or revision alone.
6. **Central weather editing is an optional architecture decision:** read-only
   oversight is immediately supportable; runtime file writes are not recommended.
7. **Production auth deployment needs separate review:** HTTPS cookie configuration
   and process-local session storage limit deployment assumptions; preserve the
   existing auth behavior during UI finalization.

Only this audit document was added for the task. Production code, database schema,
records, metadata, coordinates, recommendation logic and Git staging/history were
not changed. No SQL, migrations, Supabase updates, staging, commits, pushes, resets,
restores or cleaning operations were performed.

ROSAGO ADMIN FINALIZATION AUDIT: READY FOR REVIEW
