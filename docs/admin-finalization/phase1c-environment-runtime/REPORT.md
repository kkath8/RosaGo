# Phase 1C — Environment runtime verification

**PASS within the authorized local/read-only scope. Testing is complete for that scope.** No runtime application defect was identified. A complete production mutation/audit round-trip is **not certified**: no disposable production Draft was explicitly identified and approved, so no production write test was performed.

The local `.env` already sets `ROSAGO_DESTINATION_ENVIRONMENT_ENABLED=true`. This review did not change it or enable a hosted flag. A fresh execution of the actual `app.py` loaded the actual `.env`, enabled the Admin Environment switch, and included Environment in the public PlacesService projection. The preexisting/hosted Flask process configuration was not inspected. All network access during the initial bootstrap was blocked; subsequent live requests were restricted to GET against the expected RosaGo Supabase hostname.

## Runtime gates

| Requirement | Result | Evidence and limit |
| --- | --- | --- |
| Flask loads enabled flag | **PASS — local actual startup** | `load_dotenv()` loaded true from existing configuration; Admin helper returns true and startup-created public service selects environment. No mocked dotenv or replacement public service was used for this check. |
| Admin Add/Edit choices | **PASS — local authenticated routes** | Both forms enable exactly Indoor, Outdoor, Mix of Both, plus the empty Not recorded choice. Invalid strings/types are rejected. |
| Save and API round-trip | **PASS — local write fixtures and live reads** | Every approved value, omitted creation and explicit null validated through real Flask/PostgREST client code with isolated in-memory database transport. Live database-to-Flask API agreement checked independently for Environment and photos; live Indoor value agrees with User detail. No live INSERT/UPDATE/RPC performed. |
| NULL display | **PASS — local and live read** | Actual database NULL propagates through `/api/places`; actual User detail renders `Not recorded`. Local Admin Add/Edit and detail also render/select the empty placeholder correctly. |
| Omission and explicit clear | **PASS — local only** | Omitted edit excludes Environment from RPC payload and preserves stored Indoor/Mix of Both. Empty form choice sends JSON null and clears only Environment plus the expected updated_at change. Supplemental Draft test retains photo, Draft status and unrelated fields. |
| User details reflect Admin changes | **PASS — local sequence; live current-state agreement** | Local authenticated Admin saves are followed by User API and detail reads of Outdoor, Mix of Both and NULL. Live Indoor/current detail matches the database. No live Admin save was performed to establish a new production change sequence. |
| Photos, status, unrelated fields, exposure | **PASS — local preservation and live read evidence** | Tests preserve every fixture field other than Environment/expected updated_at, omit image_url, prohibit an upload, retain status, respect publication visibility and leave ranking unchanged. Weather suites pass; live Indoor is independently exposed as unknown weather exposure. No weather data was edited. |
| Authorization, CSRF, concurrency, audit identity | **PASS — local; live insertion deferred** | Unauthenticated/forged/non-Admin/revoked membership paths, CSRF/origin/duplicate-field checks, stale versions and caller-bound RPC tokens pass. Two distinct Admin contexts and Environment audit UI actor attribution pass. No real production audit insertion was generated or inspected in this phase. |

## Live read-only observations

Production target: `brnkigrrqdrywahvcbvc.supabase.co`. The requests used the existing public application client, without an Admin login, service-key database request or mutation RPC. Real Supabase GET reads fed the freshly initialized local Flask `/api/places` and `/places/<slug>` routes; a running hosted HTTP frontend was not exercised.

- Public API returned HTTP 200 with **35 published destinations**: 34 NULL Environment and one Indoor.
- The 34 visible destinations whose UUIDs are in the saved 49-row checkpoint still have NULL Environment.
- One additional published UUID, `9c745f18-aebc-43f3-96da-fdd1a9dd787d`, is outside that saved checkpoint. Its slug is `destination-259a1938b66048a6995604bbfd989a76`; it has Indoor Environment and a non-NULL image URL. These are public observations, not evidence of who created/edited it or authorization to use it for write tests.
- Direct database reads through the application PlacesService and `/api/places` agree on Environment and image_url for all current public rows.
- Both a real NULL detail and the Indoor detail return HTTP 200 and show the correct Environment text.
- The Indoor row has weather exposure **unknown**, demonstrating that the human-entered setting is not being promoted to verified weather exposure. Other exposure values continue to come from the curated sidecar.

The original 34-row count assertion was stale: the live count is now 35. Investigation resolved the difference to the extra published UUID. This is an observed catalog change since the earlier snapshot, not a migration/runtime defect or a change attributed to this agent. No record was modified, archived or deleted to reconcile it.

These anonymous reads cannot inspect Draft/Archived rows or private audit history. This phase does not make a fresh all-status fingerprint or production audit-count preservation claim; Phase 1B's separate post-deployment CSV verification remains the evidence for its original checkpoint. The newly observed published record must not be assumed to be the disposable Draft required by the write-test restriction.

## Local verification performed

**188 tests and 216 subtests passed, zero failures/errors/skips** across the final recorded runs:

| Suite | Tests | Subtests |
| --- | ---: | ---: |
| Environment, Admin management/authorization/audit/photos, photo SQL contract, Places routes/services, recommendations | 126 | 200 |
| Tourism/weather identity, weather service/proposal and itinerary weather | 60 | 16 |
| Supplemental exact Add/Edit choices and Draft omission/clear preservation | 2 | 0 |

The fixture suites run with socket-level live-network guards and synthetic credentials. Database writes are simulated by in-memory transports; they do not execute the deployed PL/pgSQL. This verifies application behavior and payloads, not a new production transaction.

Detailed JUnit evidence is saved in `test-results.xml`, `weather-test-results.xml`, and `form-test-results.xml`. [local_form_checks.py](local_form_checks.py) contains the two additional reproducible network-blocked checks. [test-summary.json](test-summary.json) records totals and scope, and [startup-and-readonly-evidence.json](startup-and-readonly-evidence.json) records safe flag/read observations without credentials or full photo URLs.

## Completion and remaining limit

The user-authorized fallback—read-only production observations plus local tests—has been completed successfully. No error requires a code/database correction. No application code or migration was changed; only verification artifacts and supplemental tests were added under this directory.

If Phase 1C is intended to certify live writes as well, that portion remains **NOT PERFORMED** until a specific disposable Draft is explicitly approved. Its real save/omit/clear and audit-insertion behavior must not be inferred solely from fixtures or from reading the current Indoor row. A Draft must remain unpublished during write testing; User publication visibility is already exercised with local fixtures.

No production destination, publication state, photo, audit record or weather metadata was modified. No migration rerun, CSV import, flag edit, stage, commit or push occurred. **Stopped after testing.**
