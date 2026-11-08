# Phase 1D — proposed production Environment write-test plan

**Preparation only. No production record was created or edited.** The recommended approval scope is one new disposable destination, kept Draft throughout functional/security tests, then archived through the existing audited Admin workflow. Existing destinations, including the additional published venue below, are excluded from every mutation and cleanup action.

## Current production read-only review

At **5 November 2026, 11:02:50 Asia/Manila**, a GET-only public request to the configured production project returned HTTP 200 and `Content-Range: 0-34/35`: **35 published destinations**, with 34 NULL Environment and one Indoor. All 34 UUIDs from the earlier published catalog are in the saved 49-row checkpoint; one published UUID is additional.

| Additional destination | Observed value |
| --- | --- |
| Name | **Chowking Sta. Rosa Balibago** |
| UUID | `9c745f18-aebc-43f3-96da-fdd1a9dd787d` |
| Slug | `destination-259a1938b66048a6995604bbfd989a76` |
| Status / category | published / dining |
| Environment | Indoor |
| Photo | Non-NULL existing image_url; exact value retained in local public-read evidence |
| Created | 5 November 2026, 10:52:18.618138 Asia/Manila |
| Updated | 5 November 2026, 10:55:48.775927 Asia/Manila |

These timestamps are later than the 10:40 post-deployment snapshot. They identify the additional record, not who created it or whether it was intended as a test. **It must not be edited, republished, archived, used as a fixture, or have its photo removed.**

The complete public list and current values are saved in [current-published-catalog-readonly.json](current-published-catalog-readonly.json). This uses anonymous public access and cannot enumerate current Draft/Archived records or read private audit history. The full current count is therefore **unverified**; do not assume 50 total records, four audit rows or two Storage objects based on older checkpoints. Obtain a fresh authorized all-status checkpoint before the later write test.

## Approval boundary and baseline

Nothing below is executed by this preparation. Before starting a later approved run:

1. Use normal Admin sign-in with an already authorized account. Record the authenticated actor UUID securely for comparison, never credentials/session tokens. Do not provision an Admin, change membership, use a service key for mutations, or call the unlogged inner function.
2. Confirm the approved deployed app instance already loads the enabled Environment flag. Do not change a flag or silently substitute a different app instance; the Phase 1C observation was a fresh local Flask startup, not a hosted-process inspection.
3. Pause other destination/photo/audit writers for the short verification window. Do not change database grants or policies to enforce this. Obtain and retain a current recovery checkpoint under the normal operational process.
4. Export current all-status destination, audit and Storage evidence. [checkpoint_readonly.sql](checkpoint_readonly.sql) is prepared for a trusted SQL Editor operator; it was not executed. It hashes **every existing field including Environment**, unlike the old migration checkpoint which deliberately excluded Environment. Run with disposable_id NULL before creation; after creation substitute only the returned new disposable UUID. Every existing-row/status/audit checkpoint and all Storage metadata must match thereafter.
5. Record starting counts as N destinations, D Draft, P Published, A Archived, H audit rows, O Storage objects. P is currently observed as 35, but recheck rather than freezing today's count. Confirm the unique marker below is absent in the complete Admin catalog. If it already exists, stop; do not reuse or edit it.
6. Submit creation once, then capture its generated UUID, slug, created_at and updated_at. Require the returned identity to be outside **every pre-test UUID**, and the record's marker and Draft status to match. Pin that UUID/slug for every subsequent request. A name search alone is insufficient authorization to mutate a row.

## New disposable Draft fixture

| Field | Exact proposed value |
| --- | --- |
| Name | `RosaGo Environment Verification - Disposable Draft - ENV-P1D-20261105-01` |
| Category | `nature` |
| Description | `Controlled Environment verification only. Keep unpublished. Not a real visitor destination.` |
| Address | `Disposable test fixture; not a visitor destination.` |
| Latitude / longitude | Both blank, resulting in SQL NULL |
| Environment at creation | Empty Not recorded option, resulting in SQL NULL |
| Photo / remove-photo | No file selected; remove-photo control absent |
| Tourism fields | Blank optional fields, resulting in NULL; no invented provenance |
| Publication | Server-created Draft; do not submit a status field |

Do not request a specific UUID or slug: the existing mutation function generates them. No photo upload means no new Storage object, remote fetch or photo-rights concern. The new row has no map pin and no curated weather metadata; exposure must remain unknown. Do not modify weather files or infer exposure from Environment.

## Exact functional sequence — recommended Draft-only scope

Before every successful edit, reload this Draft's Admin Edit form, verify its pinned identity/status, retain the real CSRF token and exact current expected_updated_at, and preserve every unrelated form value. Use the application route and its audited wrapper, never direct table SQL or a service-role RPC.

| Step | Action on the new UUID only | Expected saved/read value | Audit delta |
| --- | --- | --- | ---: |
| 1 | Create the fixture with Not recorded | Draft; Environment NULL; image_url NULL; Admin detail/Edit show Not recorded | +1 create |
| 2 | Save Indoor | Admin detail, reloaded Edit and authorized database read all show Indoor | +1 edit |
| 3 | Change to Outdoor | Same readers show Outdoor; UUID, slug, created_at, photo, status, coordinates and all other values unchanged | +1 edit |
| 4 | Change to Mix of Both | Same readers show exact spelling Mix of Both | +1 edit |
| 5 | Submit a valid edit with Environment **omitted** | Mix of Both preserved; request p_values lacks the environment key | +1 edit |
| 6 | Choose Not recorded and save | Form sends an empty environment value; server sends JSON null; stored value becomes SQL NULL; detail/Edit show Not recorded | +1 edit |
| 7 | After checks, archive through the existing confirmation flow | Only this new row becomes Archived; Environment remains NULL; no photo or other field change beyond expected status/updated_at | +1 archive |

To exercise omission through the actual Flask route, load only this disposable's current Edit form, temporarily disable only its Environment select for that one submission, and inspect FormData to confirm environment is absent. Leave required fields, CSRF and expected_updated_at intact; reload after submitting. This alters a browser control, not the feature flag. Empty selection is **clearing**, not omission. Do not replace the form with a raw direct RPC that bypasses the Flask boundary.

Each successful step must redirect as expected and be followed by a fresh read, not trusted from a success banner alone. An ordinary Environment edit may advance updated_at; all other fixture fields must remain identical. Even the omission edit is a successful audited invocation, so it adds an audit row and may advance updated_at despite retaining the same Environment value.

## User synchronization checks and publication limit

For the recommended Draft-only test, after every step 1–6:

- Open `/api/places` with an anonymous/public session and verify the disposable UUID/slug is absent. No full-catalog response may leak it.
- Request `/places/<disposable-slug>` anonymously and as an ordinary signed-in non-Admin user, if an existing approved account is available: require 404/unavailable, not the Draft's values. Do not create accounts or change roles for this test.
- Verify public counts and all existing venue values, including Chowking's Environment/photo/status, remain unchanged. Admin/database readers may show Draft updates; that does not imply a public reader should see them.
- Positive rendering coverage for Indoor/Outdoor/Mix of Both/NULL remains supported by Phase 1C's local sequence and live current-state reads. **A never-published Draft cannot prove a new production Admin edit becomes publicly visible.** Do not label that positive production gate PASS from hidden-record checks.

### Optional extension requiring separate explicit publication approval

To certify a positive production Admin-to-User change sequence, approve this extension explicitly in addition to the Draft-only plan. It affects **only the newly created fixture**, never an existing record, and runs after step 6 but before final archival:

1. Publish that new UUID while its Environment is NULL. Check public API returns JSON null and User detail renders Not recorded.
2. Edit it to Indoor, Outdoor, Mix of Both, then clear to NULL, using four fresh versions. After each save, check a fresh anonymous public API response and User detail agree exactly with the authorized database value; confirm photo is still NULL and weather exposure unknown.
3. Return it to Draft immediately and verify public API exclusion and detail 404. Then perform core cleanup step 7 to archive it.

This adds **six successful audited mutations**: publish, four edits, draft. Total audit delta becomes **13**, including the seven core actions. While published, the clearly labeled fixture may appear in real Explore/search/recommendations and to visitors with matching interests despite having no coordinates. A low-traffic window and prompt return to Draft reduce but cannot eliminate that exposure. This extension is **excluded from the default approval scope**. If the record must never be public, retain the local positive-sync evidence and leave the production positive-sync gate explicitly untested.

## CSRF, permissions, concurrency and audit attribution

- **CSRF/origin:** On only the disposable edit URL, one missing/invalid CSRF submission and one wrong-origin submission must be rejected with no row or audit change. Never disable CSRF, modify session cookies, or send credential-bearing requests to an external origin. Inspect actual request Origin and retain the normal same-origin path for successful saves.
- **Admin authorization:** A logged-out or already authorized non-Admin test session must not access the Draft or mutate it. Require login redirect/denial, no write and no new audit record. Do not revoke/provision roles or reuse a service key to simulate an Admin. If an approved non-Admin account is unavailable, leave that live account-specific negative check to local coverage and record the limit.
- **Concurrency:** Retain a second Edit form at the version immediately before step 6. Complete step 6 in the first tab, then submit the old second form proposing Indoor. Require rejection, NULL retained, no new audit entry. Existing Flask handling surfaces a generic reload/unavailable response (currently 503), while the database guard uses SQLSTATE 40001. Capture both available layers; do not weaken concurrency to get a particular UI status.
- **Invalid value:** On the disposable form only, attempt an invalid string such as lowercase indoor using an instrumented local form control. Require validation rejection, no state change and no audit increment. Do not change the approved option list in application code.
- **Audit attribution:** After every successful mutation, require exactly one new row for the pinned disposable destination_id, correct create/edit/archive action, actual signed-in actor_id, expected submitted_fields and resulting_status. Normal saves/clear include environment; omission does not. No image_url field should appear. Audit summary records field names/status, **not old/new Environment values**; use before/after row evidence to prove the values.
- **Multiple Admins:** If two existing explicitly approved Admin sessions are available, A performs creation/Indoor/Outdoor, B performs Mix of Both/omission, and A clears/cleans up. Require their distinct actor UUIDs in corresponding audit rows. Otherwise use one approved actor and mark live multi-Admin attribution untested. Do not create an Admin or accept client-supplied actor identity.
- **Failure atomicity:** Every rejected request must leave both the disposable row and its audit count unchanged. Do not deliberately damage an audit constraint/policy/function to test failure in production; that scenario remains an isolated-test concern.
- **Ambiguous response:** If a request times out or reports an uncertain save, stop and read the pinned destination and audit rows before retrying. Never blindly replay creation, increment a sequence on an unknown outcome, or create a replacement fixture. Missing/duplicate audit rows, unexpected actor, unexpected UUID/status or any existing-row drift is a stop condition.

The expected negative probes do not add audit rows. Preserve real tokens in the browser only and redact CSRF/session/access tokens from screenshots and network exports. Record actor UUIDs and test UUID in controlled evidence; do not paste credentials into chat.

## Expected changes and safe cleanup

Using fresh baseline symbols, the default successful run changes only:

- `places`: N becomes N+1. During steps 1–6, Draft count is D+1; final archival returns Draft to D and increases Archived to A+1. Published remains P throughout. Existing-row full-field fingerprints, including Environment/photo/status/timestamps, remain identical.
- `admin_destination_audit`: H becomes H+7, all seven new rows referencing only the new UUID. Every preexisting audit row remains identical. Optional publication testing changes this delta to H+13; it returns Published to P before cleanup.
- `storage.objects` and destination-images bucket metadata: no change from current baseline O. No upload, replacement, removal or cleanup call is allowed.
- No profiles, Admin memberships, trips/itineraries, grants, policies, functions, migrations, imported catalog data, feature flags or weather metadata change.

Cleanup is **archive and retain**, not delete. After pinning identity and checking a fresh version, use the standard audited Archive action only on the disposable UUID. Retain it Archived with NULL Environment and no image; preserve all audit history. Verify public absence and unchanged full baseline checkpoints excluding only the new UUID and its audit rows. A returned archived record is an intentional verification artifact, not a promise of zero residual rows.

Do not DELETE the fixture, truncate audit history, delete Storage objects, restore an old database backup, rerun migrations/imports, or use CASCADE. The audit destination FK deliberately restricts deletion. If testing stops partway, capture current row/audit evidence and, only within the approved cleanup scope and with correct identity/version, return the new record to Draft if the optional publication extension was active, then archive it. Never automate cleanup by a broad name prefix. If identity or permissions are uncertain, stop and report; do not touch an existing row to restore counts.

## Approval requested — no execution yet

Approve creation and steps 1–7 for **one newly created disposable Draft**, the scoped negative probes, current read-only checkpoints and final archive/retention. Specify whether one or two already authorized Admin actors will be used when arranging execution; no credentials should be supplied in chat. Temporary public publication and the positive User-sync extension require an explicit additional approval; silence does not approve them.

Until that approval, no fixture creation, edit, archive, publication or production write test will occur. **Preparation stopped here.**
