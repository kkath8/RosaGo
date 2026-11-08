# Preview all 98 destinations in normal Flask

This is the current launcher. A separate preview server is **not required**.
The existing `app.py` now supports the development-only local catalog option.
Remote deployment remains **NO-GO**.

## Enable

Stop Flask with **Ctrl+C**. In PowerShell at the repository root:

```powershell
$env:ROSAGO_CATALOG_PREVIEW = 'true'
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload
```

Open:

- **Explore:** http://127.0.0.1:5000/places
- **Simulation:** http://127.0.0.1:5000/preview/planner
- **Example:** http://127.0.0.1:5000/preview/planner?interest=dining&stops=6
- **Held-photo detail:** http://127.0.0.1:5000/places/nuvali-sand-courts

Use View Details on any card for its normal `/places/<slug>` URL. Search,
categories and Appearance work. No login is needed to inspect public Explore
or the clearly labelled simulation. The real `/user/planner`, saved trips and
Admin pages retain their original authentication checks and routes.

The normal application loads its existing `.env` configuration as before; no
credential or session setting is replaced. `FLASK_SKIP_DOTENV=1` is not needed
for this integrated launcher. If it remains set from the earlier standalone
instructions, you may remove that temporary override:

```powershell
Remove-Item Env:\FLASK_SKIP_DOTENV -ErrorAction SilentlyContinue
```

Only the preview flag changes; no environment file is edited. Preview requires
the existing auth mode to be development and rejects production/Render settings,
remote clients/hosts and forwarded proxy headers. Do not weaken a configured
production/shared-session mode to enable it. This feature is for the current
local development app only. Do not use `0.0.0.0`, a public tunnel or a proxy.

## Disable

Stop Flask with **Ctrl+C**, then restart the same app with the flag removed:

```powershell
Remove-Item Env:\ROSAGO_CATALOG_PREVIEW -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload
```

An explicit `$env:ROSAGO_CATALOG_PREVIEW = 'false'` also disables it. If you
previously added the flag to `.env`, remove it there or use explicit false.
Default is disabled. Restart is required because the catalog is loaded once
and the application routes/hooks are selected at startup.

Normal `/places` then returns to `PlacesService` and the existing Supabase
Published catalog, including stored image URLs. No preview files are read and
the two extra preview routes are absent when disabled.

## Behavior and safeguards

- **Same Flask application and port:** normal User/Admin endpoint registrations,
  service objects, authentication decorators and session interfaces are retained.
  The integration reuses the completed preview renderers, images and templates;
  it does not replace `rosago_places` or register a published-only service that
  returns Drafts to real itinerary operations.
- **Explore/details only use local data:** `/places` and `/places/<slug>` show all
  98 researched records with the existing User card/detail UI. The page banner,
  Draft/unresolved badges, proposed descriptions/categories and not-applied
  publication labels remain visible. There are 65 first-batch candidates and
  33 held records in this review. The 81 sound locations remain accepted.
- **Images:** 82 prepared local candidates are displayed: the 79 proposed
  attachments plus local preview candidates for the three preserved hosted
  covers. The stored covers and their final assignment mapping are unchanged.
  Sixteen placeholders remain, including the unassigned Nuvali Sand Courts and
  held Winner Badminton Court image. No photos were reprocessed or uploaded.
- **Simulation is separate from protected planning:** `/preview/planner` offers
  the existing category-based first-batch visual simulation with Local/NULL/Common
  priority and 3/6/9/12 suggestions. It is not personalized scheduling, live
  weather or routing and has no save action. `/user/planner` is still the real
  authenticated Planner; a preview flag never grants access to it.
- **No data-changing operations while enabled:** all non-GET/HEAD requests are
  rejected before real mutation handlers, including destination/Admin edits,
  trip/draft saves, account changes, sign-in and routing POSTs. The existing
  User/Admin logout endpoints are exceptions so their normal CSRF/authentication
  and provider/session revocation behavior remains available. Account-completion
  callbacks that could change Auth state are also paused. Disable preview to
  resume normal write/sign-in behavior. This restriction is shown in User/Admin
  workspace banners; routes are not deleted or replaced.
- **Normal reads remain normal:** Admin catalog, dashboard, library/API and
  protected User pages keep their existing services/permissions. They may read
  the configured Supabase project; they do not receive simulated records.
  Public preview browsing itself makes no Supabase calls. The whole application
  is not represented as an offline replacement for those normal pages.
- **No session bypass:** existing realm/session before-request checks run before
  local catalog dispatch. Invalid Admin cookies still fail, and logged-out access
  to the real Planner/trips/Admin still redirects to login. The preview uses
  synthetic, non-UUID presentation IDs and omits real save/personal-state scripts
  on preview pages. Browser-local library state is not populated from the CSV.
- **Loopback-only and fail closed:** production/Render startup is rejected before
  provider client construction. The host, peer address and proxy-header checks
  apply to the app while preview is enabled. Preview responses are no-store and
  use a self-only CSP with connections disabled. The normal static endpoint is
  preserved; the new image route serves only the prepared assignment allowlist.

The old standalone factory remains available for offline tests, but is not the
launcher needed for this workflow. No schema, CSV matching, category approval,
image assignment, publication status, authentication provider or session authority
was changed. Provider authority/Auth restore-replay remains a deployment blocker.

## Verification

**67 focused offline tests passed**, with network connections blocked, including:

- Normal app preview-on/off initialization, 98 cards and local images/details.
- Unchanged normal service objects and route inventory (only two new read routes).
- Protected real Planner/Admin, invalid-cookie rejection and existing logout gate.
- Mutation/sign-in denial, loopback/proxy restrictions and disabled-input loading.
- Existing normal catalog, public layout, Admin authorization and login/recovery
  referrer/security regressions.

**14 real headless Edge checks passed** on the normal Flask app at desktop and
mobile sizes: all 98 cards, image loading, navigation, no horizontal overflow,
theme persistence, held photo, simulation and zero SDK operations. The browser
test used synthetic SDK configuration, a fresh profile, an owned loopback server
and a deny-only outbound proxy. No real sign-in/provider operation occurred.
The owned browser and server were stopped after testing.

- [Browser results](preview-browser-integrated/results.json)
- [Desktop screenshot](preview-browser-integrated/desktop.png)
- [Mobile screenshot](preview-browser-integrated/mobile.png)

Implementation files: `app.py`, `catalog_preview.py`, shared base/card/detail and
preview navigation templates, the Admin workspace notice, integrated preview
tests and the existing browser checker. Only conditional UI/dispatch integration
was added; earlier unrelated workspace changes are preserved. The stage manifest
is `integrated-catalog-preview-local-results.json`.

No hosted changes, migrations, image uploads, publication, deployment, commits or
pushes occurred. Successful Linux build evidence and prior security/catalog/image
artifacts remain preserved. Remote deployment remains **NO-GO**.
