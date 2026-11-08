# Run the 98-destination preview locally

> Superseded launcher instructions: [INTEGRATED_CATALOG_PREVIEW.md](INTEGRATED_CATALOG_PREVIEW.md). The normal `--app app` launcher now supports the preview flag on the same port; the separate launcher below is retained as historical/offline-tool documentation. Earlier statements that `app` rejects the flag are no longer current.

The preview is implemented and tested in the existing User Explore/detail UI.
It does not publish anything. Remote deployment remains **NO-GO**.

## Why normal Flask still shows 35 destinations

`app.py:places_list` calls `search_published`, which pages through
`PlacesService.list_published`. The latter selects `public.places` with
`status = published`; it does not load the CSV or local review files. The
owner export contains 35 Published rows. This is not a 35-record display limit.
`places_detail` also uses the published-only Supabase reader. The public
`/api/places` used by browser features obtains its data through the same service.

Normal card images come from each stored `image_url`. The 79 local proposed
attachments have not been uploaded or assigned to Supabase. NULL/unavailable
stored covers therefore use the existing placeholder. Merely placing images
in the repository does not update database URLs. This behavior is preserved.

## Enable the isolated preview

In a VS Code PowerShell terminal at the RosaGo repository root, stop an older
Flask process with **Ctrl+C** if needed. Then run:

```powershell
$env:ROSAGO_CATALOG_PREVIEW = 'true'
$env:FLASK_SKIP_DOTENV = '1'
.\.venv\Scripts\python.exe -m flask --app catalog_preview:create_app run --host 127.0.0.1 --port 5001 --no-debugger --no-reload
```

Open:

- Explore: **http://127.0.0.1:5001/places**
- Planner simulation: **http://127.0.0.1:5001/user/planner**
- Example simulation: **http://127.0.0.1:5001/user/planner?interest=dining&stops=6**
- Example held-photo detail: **http://127.0.0.1:5001/places/nuvali-sand-courts**

Use **View Details** on any of the 98 cards for its corresponding local detail
page. Search/category links and the Appearance toggle work. There is no need
to log in. These are public catalog preview views, not access to protected
User/Admin data. No Supabase URL, key, password or session secret is needed.

`FLASK_SKIP_DOTENV=1` prevents the Flask CLI from loading the normal `.env` into
this preview process. Neither environment file is edited. The launcher requires
the OS environment's `ROSAGO_AUTH_MODE` to be unset or `development`; it rejects
production/Render environments and non-loopback `FLASK_RUN_HOST`. Do not change
production credentials/security mode to make a preview start. Use a fresh local
development terminal if an existing terminal has production overrides.

Use **catalog_preview:create_app**, not **app**, while the flag is true. The normal
launcher explicitly rejects the preview flag before constructing a Supabase
client, preventing a silent mixture of hosted and preview data. If port 5001
is occupied, stop that process or select another unused loopback port and use
the corresponding URL. Do not bind to `0.0.0.0` or put this behind a proxy.

## Disable and return to normal mode

Press **Ctrl+C** in the preview terminal, then:

```powershell
Remove-Item Env:\ROSAGO_CATALOG_PREVIEW -ErrorAction SilentlyContinue
Remove-Item Env:\FLASK_SKIP_DOTENV -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload
```

Open **http://127.0.0.1:5000/places**. Normal mode continues to use the existing
configuration and published-only Supabase catalog. It will still show the
hosted Published set until separately approved database changes occur. If either
environment variable had a custom value before these instructions, restore that
value instead of removing it. No hosted writes are part of either preview step.

## What the preview displays

- All **98** source records, in CSV order, including Draft/unresolved records.
  A permanent preview banner distinguishes them from the hosted catalog.
- **65** first-batch candidates labelled “Proposed Published — not applied”; the
  other **33** labelled Draft with expandable pending decisions. The 81 accepted
  locations remain accepted; a Draft may be held only for a content/alias decision.
- Four supported description proposals are rendered and marked **awaiting
  approval**, rather than silently filling the source or database.
- Proposed specific categories/legacy parents and the merged resort key render
  without activating the unapproved registry in the normal application.
- **82 local photo candidates**: 79 proposed attachments plus the already
  prepared local candidates for the three preserved hosted covers. The latter
  are marked as local previews; the actual existing hosted covers remain
  unchanged in every database change proposal. No Supabase images are fetched.
- **16 placeholders**: 14 without matching photos, Nuvali Sand Courts' incorrect
  photo held unassigned, and Winner Badminton Court's held identity candidate.
  No held image endpoint is made available for those two records.

The preview reads the completed, source-bound first-batch package, image mapping,
initial image review and proposed category registry. It checks review/CSV hashes
and safe file paths; it does not rescan, decode, sanitize or regenerate images,
rematch destinations, or rerun CSV field validation. The original CSV, downloaded
images, staged files and reviewed manifests are read-only inputs. If an input
hash differs, stop for review rather than deleting the checks.

Local images are served only from their assigned manifest paths under
`local_catalog/image-staging/`; arbitrary files, credentials, original source
image folders and the full review directory are not exposed as a web directory.

## Planner scope and safety boundaries

The Planner simulation uses only the **65 first-batch candidates**, proposed
legacy-parent category matching and Local/NULL/Common priority, with a choice
of 3/6/9/12 suggestions. It reuses the same cards/details/images. It is a
presentation simulation, **not** the production personalization, itinerary
scheduler, weather or routing engine. No real trip/draft, preference, account,
Admin membership or authentication session is created. Unresolved/Draft-held
records remain visible in Explore but are excluded from suggestions.

The normal protected Planner, account and itinerary routes are not registered
in this separate preview app. All non-GET/HEAD requests are rejected, as are
remote hosts/clients and forwarded-proxy headers. The preview does not weaken
the actual auth routes, CSRF, provider guards or RLS. Its CSP blocks browser
connections; normal personal-state/account/trip scripts are not loaded and it
does not use real account cookies. External fonts are skipped so a system/local
font fallback works offline. Theme persistence remains browser-local.

Production authentication, provider authority and Auth restore/replay remain
unqualified. Preview success does not qualify publication or deployment.

## Verification and changed files

**73 focused offline tests passed**: 66 existing normal catalog/layout/itinerary
regressions plus seven new preview tests. Coverage includes all 98 detail pages,
82 assigned image references/16 placeholders, held images, filters/simulation,
no provider client on a mistaken normal launch, read-only/loopback restrictions,
path traversal and no authentication or save endpoints.

**13 real headless Edge checks passed** at 1440px desktop and 390px mobile:
98 cards, visible image loading, navigation, no horizontal page overflow,
appearance switching/persistence, held-court placeholder, simulation suggestions
and no external page resources. A fresh browser profile, loopback-only fixture
and deny-only outbound proxy were used. No sign-ins occurred. Owned browser and
servers were stopped after testing.

- [Browser results](preview-browser-v2/results.json)
- [Desktop screenshot](preview-browser-v2/desktop.png)
- [Mobile screenshot](preview-browser-v2/mobile.png)

Implementation changes: `catalog_preview.py`; preview-only CSS/navigation/status
partials; guarded branches in the shared base, Explore/detail and place-visual
templates; the three-line normal-launch guard in `app.py`; preview unit/browser
test tools. Other pre-existing workspace changes are preserved.
The complete stage file hashes and preserved-input checks are recorded in
`catalog-preview-local-results.json`. No hosted records/settings/Storage,
migrations, deployment, commits or pushes changed.
