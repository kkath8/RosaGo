# Admin Add Destination — isolated verification

**Result: PASS in the isolated environment.** No production application changes were necessary. No hosted destination, Storage object, authentication setting, schema, deployment or Git state was changed.

## Verified behavior

| Area | Result |
| --- | --- |
| Add Destination | Actual template submits a native multipart POST and redirects after mocked persistence |
| Draft creation | Exactly one Draft created; stable ID/slug and entered values survive reload |
| Admin management | Newly created Draft appears in the list and its detail/edit pages |
| Draft privacy | Excluded from public Explore; public detail returns 404 |
| Validation | Required fields, incomplete coordinate pairs, malformed duplicate controls and corrupt photos are rejected without unintended mutation |
| Duplicate handling | Rapid second click creates no duplicate; duplicate named controls return 403 |
| Same-name policy | Intentional repeated name/address creates a separate Draft with a distinct ID/slug; existing record is never overwritten |
| Photo upload/display | Actual selected PNG is decoded/re-encoded, uploaded through mocked Storage and decoded/displayed by Chrome |
| Photo replacement | New mock object/URL; JPEG pixels display correctly |
| Photo removal | Reference cleared; existing objects are not deleted or overwritten |
| Invalid/oversized files | Browser rejects SVG/oversized selection; backend checks reject corrupt, oversized and unsupported images |
| Publishing | Confirmation POST makes the new Draft visible in public Explore/detail |
| Published updates | A detail edit to the newly created synthetic destination appears in public detail |
| Archiving | Admin retains archived record; public Explore excludes it and public detail returns 404 |
| Isolation | Two pre-existing records/photos and the unrelated same-name Draft remain unchanged |

“Duplicate handling” does **not** claim database idempotency or semantic venue deduplication. The existing product permits same-name/address records under distinct identities. A later real operator must check whether a venue already exists; a stricter business rule would need an explicit policy and appropriate atomic enforcement.

## Focused tests

**17 browser checks passed, no JavaScript exceptions.** [Browser results](browser-results.json) preserve sanitized request methods/paths/statuses.

The run used fresh headless Chrome, the actual Add/Edit/Publication templates, native form submission, the real Flask route/service code, mocked SDK transports and synthetic destination data. It verified image pixels from the mocked stored upload, not merely a photo URL or preview. External browser requests were blocked; only the ephemeral fixture origin and locally fulfilled synthetic image responses were allowed. It did not attach to the operator browser or port 5055.

**6 selected backend tests passed; 14 subtests passed.** [Backend results](backend-results.json) record their exact names. They cover Admin/CSRF/Origin denial, invalid creation, image size/format limits, malformed controls, Storage error handling and uncertain database-save cleanup. Existing fixtures block real network transports. The previously completed real-edit/login/inventory tests were not repeated.

Reproduce the browser run:

    node docs/admin-finalization/add-destination-isolated/browser_flow.mjs

The runner launches its own Python stdio fixture and fresh temporary browser profile. It may require host-context child-process permission in the managed Windows sandbox. No real credentials or hosted access are used.

## Defects and files

**Confirmed application defects: none reproduced.** Add, Draft visibility, photo management and lifecycle synchronization worked with existing application code; no speculative production patch was made.

The first browser attempt exposed a test-fixture issue: the SDK sends a multipart upload envelope, while the mock initially served that envelope as image bytes. [offline_bridge.py](offline_bridge.py) now extracts the uploaded file part before serving the mock object; Chrome then decoded both PNG and JPEG successfully. This was a fixture correction, not a production Storage bug.

Only this task's local test harness, generated synthetic test images, test-result artifacts and this report were added:

- [browser_flow.mjs](browser_flow.mjs)
- [offline_bridge.py](offline_bridge.py)
- browser-results.json and backend-results.json

## Before one real destination

**GO for the isolated feature flow. No real creation is authorized.**

Remaining live qualification is one explicitly approved new Draft through the existing Admin interface: approve exact content, confirm the target project/current session, check for an existing venue, capture a fresh baseline, then verify one created identity/audit event, Admin reload, Draft-only visibility and unchanged unrelated records. Define a supported archive/cleanup plan before creation; do not assume hard deletion.

Start that future live test without a photo to isolate destination creation. Actual photo uploads, replacements or removals require their own explicit approval and object-byte/retention review. Mocked Storage success does not prove current hosted upload permission or recovery coverage.

No new hosted venue was created, no real photo operation or publication change occurred, and no RLS/Auth/key change, migration, deployment, staging, commit or push was performed.
