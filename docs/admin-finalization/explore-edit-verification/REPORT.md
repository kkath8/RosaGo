# Admin Explore — Existing Destination Editing Verification

Verified **2026-11-06, Asia/Manila**. Scope: local implementation and offline fixtures. Production deployment remains on hold.

**Result: existing destination editing works in isolated tests. One form-state bug was fixed. GO for controlled manual use with isolated test data; live destination writes remain unapproved.** No live login, Supabase request, database/Storage write, email, external API request or deployment was performed.

## 1. Current editing functionality

The Admin interface calls the shared catalog **Destinations**. User Explore reads that same catalog through its published-only services; there is no separate Explore destination table to maintain.

1. Open `/admin/places` and choose **Edit Destination** on a row, or open its details and choose **Edit Destination**.
2. The link addresses `/admin/places/<slug>/edit`. The server reads that exact slug with the authenticated Admin's request-owned client. Missing records return 404; selection query parameters are rejected.
3. GET prepopulates the current record and its `expected_updated_at` concurrency marker. It performs no mutation or upload.
4. POST uses action **`edit`**, the URL's slug, the version marker, same-origin admission and session-bound CSRF. It does not call the creation endpoint. The SQL contract locks the selected row and updates by its existing ID; name changes do not regenerate the ID or slug.
5. A successful save returns 303 to the same destination's detail page. A fresh User Explore/detail read uses the updated published record.

Relevant existing components: [routes](../../../admin_routes.py), [management service](../../../admin_management_service.py), [Admin reads](../../../admin_places_service.py), [edit form](../../../templates/admin/place_form.html), [details](../../../templates/admin/place_detail.html), [photo service](../../../admin_photo_service.py), [public catalog](../../../places_service.py), [publication/mutation SQL](../../../migrations/0012_admin_management.sql), [audit wrapper](../../../migrations/0013_admin_destination_audit.sql), and [environment extension](../../../migrations/0014_destination_environment.sql). These are source contracts; their presence does not prove the hosted database has those exact definitions applied.

| Field | Existing support / verification |
| --- | --- |
| Name, description, category, address | Prepopulated and editable. Required text/category validation remains enforced. Renaming preserves identity. |
| Latitude/longitude | Prepopulated and editable as a pair, or both blank. Numeric, finite and geographic bounds are enforced; no geocoding is performed. |
| Environment | Editable when the existing environment feature is enabled: Indoor, Outdoor, Mix of Both, or Not recorded/NULL. Disabled when unavailable; no feature configuration was changed. |
| Tourism information | Existing optional fields are prepopulated when enabled. Raw hours remain unverified source text. Source provenance is not accepted as an editable identity field. |
| Cover photo | Current image shown; leave upload empty to retain, select replacement to upload, or explicitly select removal. One cover photo, not a multi-photo gallery. |
| Publication status | Shown on the edit form. Changed through separate **Destination Details → confirmation → POST** actions, not a status field submitted with an ordinary edit. Injecting `status` into the edit form is rejected. |

Publication rules remain: draft → published or archived; published → draft or archived; archived → **draft** through Restore. Editing an archived record does not publish or restore it. Draft/archived destinations remain excluded from User Explore/public detail reads. An already-open browser page needs a refresh; there is no realtime push synchronization claim.

## 2. Confirmed bug and smallest fix

**Bug:** the edit form forgot an explicit **Remove the saved photo when saving** selection after server-side validation failed.

Reproduction using an existing fixture with a photo:

1. Load its rendered edit form.
2. Select photo removal and submit invalid destination text.
3. The server correctly rejects the save without changing data, but previously returned an unchecked removal checkbox.
4. Correcting only the text and resubmitting could silently retain the photo instead of carrying out the intended removal.

**Fix:** one template-line change preserves `checked` when a rejected POST contains the validated `remove_photo=1` choice. GET forms remain unchecked. Removal still happens only after a valid, authorized save; no image is deleted merely by displaying the form.

The regression failed before the template fix (`None != '1'` for the returned checkbox control). After the fix, the test serializes the returned form, corrects only the invalid name, saves, and verifies that the intended record's image reference is cleared while the other destination remains unchanged.

No incorrect-record update, duplicate-on-edit, publication leakage or edit-link/prepopulation bug was reproduced. No route, SQL, authorization, session configuration or upload-service change was needed.

## 3. Files changed in this task

| File | Change |
| --- | --- |
| [templates/admin/place_form.html](../../../templates/admin/place_form.html) | Preserve the photo-removal checkbox after a failed POST; the only application change. |
| [tests/test_admin_explore_edit.py](../../../tests/test_admin_explore_edit.py) | Seven focused behavior tests using two pre-existing, distinct destination fixtures and rendered-form submissions. |
| [verify_offline.py](verify_offline.py) | Focused/relevant-suite runner reusing the established credential-scrubbing, dotenv-disabled, socket-blocking harness. |
| This directory's report/evidence | Sanitized before-fix and final results. |

The workspace already contained other uncommitted changes, including the environment form control. Those were preserved and are not changes introduced by this task. No staging, commits or pushes occurred. Documentation Python/JSON artifacts are ignored by existing repository rules; the report is retained by those rules.

## 4. Tests and results

Command from the repository root:

```powershell
.\.venv\Scripts\python.exe docs/admin-finalization/explore-edit-verification/verify_offline.py
```

**Final result: 176 tests passed; zero failures, errors or skips, in 14.16 seconds.** The suite spans 14 modules: new existing-row editing coverage, Admin management/photos/photo SQL/authorization/login/destinations/audit/frontend, environment, public routes/services/client and independent sessions.

| Requested behavior | Evidence |
| --- | --- |
| Existing destination loading | Follow actual list/detail edit links; compare rendered basic, tourism, coordinate, environment, saved-photo and version controls with the selected pre-existing row. GET produces no writes. |
| Detail editing/saving | Submit rendered form with changed name, description, category, address, coordinates and environment. Verify redirect, reread and current values. |
| Validation | Reject empty required fields, unknown categories/environment, NaN/out-of-bounds/incomplete coordinates, forged ID/slug/status, selection query parameters and missing records. Existing suite also covers lengths, extra/duplicate fields, CSRF/Origin and upload limits. |
| Photo management | Actual SDK request construction against a mocked Storage transport; replace with a newly generated Storage URL, retain on text-only edit, detach on removal, and check User detail output. Invalid files and unauthorized uploads are rejected by existing photo tests. |
| No duplicate destination | Both rows exist before editing. Verify total row count stays two, every attempted update uses action `edit` and the selected slug, and replaying an old form cannot create a record or overwrite newer state. |
| Authorization | Membership-denied Admin credentials return 403; uncertain membership returns 503; User-only/unauthenticated Admin realm redirects to Admin login. No edit/upload occurs. Existing tests cover session-bound CSRF, exact origin and forged role flags. |
| Published Explore synchronization | Refreshed `/places`, `/places/<slug>` and `/api/places` show changed published information; the public model retains updated coordinates and photo. |
| Archive behavior | Edit an archived fixture without changing its status; public detail stays 404 and it is absent from Explore/API. GET Restore only displays confirmation; confirmed Restore produces draft, still hidden. |
| Unrelated records/relationships | Compare the other destination's complete record before/after; preserve target ID, slug, creation time, status, image on text-only saves and source provenance. SQL review confirms identity-scoped UPDATE rather than INSERT for editing. Actual foreign-key enforcement was not executed in a database. |
| Corrected bug | Failed validation makes no changes; returned removal choice remains checked; corrected resubmission detaches only the intended record's image reference. |

Evidence: [before-fix results](before-fix-results.json) (seven focused tests, one confirmed regression failure), [final results](isolated-results.json) (176 passing tests), and the [new tests](../../../tests/test_admin_explore_edit.py). Early fixture-development issues were corrected before the recorded before-fix run; they were not classified as application bugs.

Test configuration contains synthetic values only; inherited application environment is cleared and `.env` loading disabled before importing the app. HTTP uses MockTransport and Flask's in-process client, with outbound socket operations guarded. **Outer network-guard attempts: 0; real provider requests: 0.** No real credentials were available to the tests. Raw test logs, credential/header/cookie payloads and provider responses were not saved as durable evidence. Existing assertions also check that protected responses do not leak fixture provider credentials/details. This is offline evidence, not qualification of every production logging sink.

## 5. Storage and data protection

- Photo uploads go through `admin_photo_service.upload_photo` to Supabase Storage's configured `destination-images` bucket using a server-only credential. Unique generated paths and no-upsert upload semantics avoid overwriting old objects. Local image source files do not need manual edits.
- Required Admin membership is checked before management access and checked again before upload. Database mutations keep the caller's authority; the Storage secret does not become a business-database Admin identity.
- Images are decoded/validated/re-encoded; accepted formats are JPEG/PNG/WebP, with 5 MiB and 20-megapixel limits. Browser filenames do not choose Storage paths.
- Empty upload preserves the saved image. Removal clears the destination's URL reference; it does **not** delete the existing Storage object. Archived objects/public URLs may remain downloadable, which is separate from catalog visibility.
- Upload and SQL save are not one transaction. If upload succeeds and the database save fails, an orphan object may remain. Existing messages identify this uncertainty. Cleanup automation was not introduced.
- The edit SQL retains existing destination IDs and updates the selected row; it does not rewrite trip relations. Hosted triggers, ACLs, audit transactions and foreign keys were reviewed as contracts and remain unverified by real execution here.

## 6. Remaining limitations and controlled manual procedure

This task does not establish actual hosted migration/RPC/Storage permissions, live Admin authentication, real upload delivery, database constraints under concurrency, CDN behavior or production readiness. Experimental adapters remain unselected; startup safeguards and session security settings are unchanged. The earlier production NO-GO is unaffected.

The current application maps stale/database mutation failures to a safe **503** response rather than a dedicated conflict status. The isolated stale-version test confirms no overwrite or duplicate; users should reload and compare the record after an uncertain save, not blindly retry. Browser file selections must be reselected after a rejected submission. Published catalog updates become visible on a fresh read, not automatically in an open page.

For a later controlled manual check:

1. Use a separately approved isolated project/database or a synthetic demo backend, two dedicated test destinations, and an authorized Admin session. Do not point this walkthrough at real destination records. Authentication/provider activity and any hosted writes need their own explicit authorization.
2. Record only non-sensitive test IDs/slugs and baseline field values. Preserve a second destination as an unrelated-record sentinel; note target relationships if the isolated database has them.
3. Open Destinations → Edit for the target. Confirm current fields/photo, then change ordinary details and save once. Expected: same ID/slug, no extra row, only the target changes.
4. Refresh User Explore and target details. Expected: current published information and coordinates; the sentinel remains unchanged.
5. Upload a small test photo through the form. Expected: new Storage URL and updated User image; no local asset editing or old-object overwrite. Test text-only retention and explicit removal separately. Only use objects created for this approved test.
6. Exercise the validation regression on the isolated target: choose removal, submit invalid text, confirm the choice survives, correct the text and save. Expected: no write on rejection, intended detachment on valid save.
7. Use only the test target for archive/restore confirmation checks if separately approved. Expected: archive hides it; restore returns to draft, not public. Editing alone never changes publication.
8. In an independent User-only/anonymous client, request the Admin edit route and attempt a synthetic unauthorized form. Expected: denial before catalog mutation/upload. Do not enter another account's credentials or record cookies/tokens.
9. Stop on unexpected privilege, identity change, duplicate, unrelated-record change, provider error or uncertain save. Reload/read back before deciding on a retry; never repair uncertainty by deleting/recreating the destination. Restore only approved fixture fields/status and clean up only newly created test objects after checking references.

**Readiness:** GO for controlled manual verification with isolated data and the existing development configuration. **NO-GO for unapproved live destination writes or any public deployment claim.** No live operation was performed or authorized by this report. Stop pending explicit approval for any hosted write test.
