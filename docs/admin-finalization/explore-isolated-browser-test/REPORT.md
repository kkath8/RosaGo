# Admin Explore — Isolated Browser Connection and Editing Test

Date: 2026-11-06 (Asia/Manila). **Browser/server identity verified in both runs. Manual testing stopped at a repeated synthetic login failure; no destination Save occurred. Both owned servers are closed. NO-GO for editing real destinations.**

## 1. Previous mismatch and scope of correction

Reviewed the [previous manual report](../explore-manual-edit-test/REPORT.md). The operator reported a successful save, but the owned server recorded no Admin login/edit POST and retained both original records. The operator could not display the fixture's run ID. Browser-control connections failed with ECONNREFUSED. **The underlying network/browser-context cause was not established**; no claim of a fixed Flask, proxy, reloader or authentication bug is made.

A confirmed workflow weakness was that instance identity had not been established before the reported edit. The correction is limited to the local test wrapper: dedicated port **5096**, one server without the Flask reloader, a visible HTML identity page/banner, browser confirmation and additional fail-closed POST admission. No Windows listener/PID verifier or production authentication change was introduced.

## 2. One isolated server

Fixture origin used: **http://127.0.0.1:5096**. Last instance ID: **299a0509f5c11384298580c6**. **The server is now closed; this URL is not an active test invitation.** The wrapper serves directly through Werkzeug `make_server`, one process, no `app.run`, debugger or reloader. A bind collision fails startup rather than selecting a different port or stopping another server. There was only one isolated listener at a time; the first was closed before the one controlled restart.

The server was started in the host execution context to avoid relying on the earlier sandbox-to-browser path. This is an explicit execution choice, **not proof** that sandboxing caused the previous mismatch. Independent read-only HTTP inspection verifies the origin, returned instance header, run identity and local state.

Inherited provider configuration is cleared, dotenv disabled, SDK startup creation mocked, and all Auth/business/Storage transports replaced with the existing in-memory demo doubles before serving requests. Outbound socket connections/connect_ex and UDP sends are denied; non-loopback DNS is rejected. The guard qualifies itself by denying a socket probe before any remote connection occurs. Experimental session adapters remain unselected; the normal development session architecture and production startup refusal remain intact.

Exactly two published synthetic destinations are seeded: **Manual Test Garden** (editable target) and **Unrelated Test Museum** (sentinel). Only target `edit` is permitted by the mock mutation provider. Creation, publication changes and edits to other destinations are rejected. Photos are in-memory PNG bytes served on localhost; replacement uses mocked Storage. No real destination, Auth account, database relationship or Storage object is loaded.

## 3. Browser identity gate

Open `/__isolated` in the intended private browser. It shows the exact origin, public instance ID, fixture scope and a **Confirm this instance and continue** button. Confirmation requires the matching ID, exact origin and one expected field. It records only the public ID/event/time, then sets an HttpOnly/SameSite=Strict **public instance marker**. This is additional test admission, not a login/session credential or a grant of Admin authority. The original Admin login, membership and CSRF checks still execute.

All test login/edit POSTs require confirmation and that browser's current instance marker. Unknown POST families and other edit targets are rejected before their application route. A banner repeats the instance ID on HTML pages; every response is no-store. No credentials, CSRF values, Authorization headers, cookies or raw login/form bodies are recorded.

The agent's read-only state inspection does not confirm the browser or set the marker. **The operator must report the visible matching ID and the server must record confirmation before the agent requests login or Save.** If either observation is absent or contradictory, stop before editing.

**First-run checkpoint passed:** the operator reported “The ID matches and the confirmation opened Admin login.” Independent state inspection then found one identity page GET and one matching `browser_instance_confirmed` event at **2026-11-06 11:03:21 UTC**, for first-run ID `1fb326e96b45e4456c891495`. At that checkpoint there were zero Saves/edits, two original fixture records, preserved target ID and unchanged Museum. That evidence is preserved in [attempt1](attempt1/README.md). It establishes that first run's browser/server path, not the previous phase's network root cause or the restarted run's identity. Current pre-edit state is [before-edit-state.json](before-edit-state.json).

**Restarted-run checkpoint also passed:** its independent event file records the identity page, successful confirmation at **2026-11-06 12:32:55 UTC**, redirect to Admin login, helper-script GET 200 and subsequent Admin login POST 401. The confirmation's matching public ID and marker were prerequisites for that login POST. Thus this browser was reaching the exact owned isolated application; the earlier connection/identity blocker is resolved for the observed path. This does not prove the mechanism that caused the previous phase's mismatch.

## 4. Tooling qualification

Eight in-process identity-gate tests passed: visible ID/no-cache, unconfirmed Save denial, marker-only bypass rejection, mismatched/cross-origin confirmation denial, successful confirmation and safe evidence serialization, second-browser denial, forbidden creation/other-target denial, and wrong-origin rejection.

Initial sandbox runs could not write/read/clean their temporary test directories (PermissionError). The same eight tests passed in the host context in 0.260 seconds. After adding the fill-only control, the expanded suite passed **9 tests, zero failures/errors, 0.117 seconds**. A separate Node VM check passed for dummy filling, no automatic submission/network and exact origin/path guards. These tests contacted no providers and altered no real data. The filesystem context limitation does not establish the previous browser network cause.

Files: [wrapper](isolated_server.py), [gate tests](test_identity_gate.py), [read-only inspection](inspect_fixture.mjs), [ready metadata](ready.json), [state](latest-state.json), [identity events](identity-events.json), [final state](final-state.json), [fill-only script](fixture-login.js) and [offline script test](test_fixture_login.mjs). The previous [test launcher](../explore-manual-edit-test/manual_fixture.py) gained optional port/app-hook parameters; its defaults and previous result files are preserved. New evidence goes only to this directory. Application source, production settings, session safeguards and SQL are unchanged.

## 5. Manual results — closed, incomplete

| Check | Current evidence |
| --- | --- |
| Same browser/server instance before Save | PASS in both sequential runs, independently recorded before any Save |
| Actual Admin login/Edit selection | First run: five 401s; restarted run: one 401; no actual-browser edit GET |
| Actual Save request | None: zero Save responses and mock mutations |
| Before/after target values | Baseline only: Manual Test Garden, original description/address, nature, 14.3/121.1, Indoor, original mock photo |
| Stable ID/no duplicate/unrelated row | Final read-back: both complete records equal baseline; two rows, original target ID, unchanged sentinel |
| Published changes in User Explore | Not verified; no successful manual edit exists to synchronize |
| Validation and photo-removal retention | Not executed manually because login failed; offline regressions remain separate evidence |

The planned walkthrough was to edit the Garden once, verify its successful HTTP result and same-store read-back, compare identity/row count/sentinel, and refresh User Explore before photo/validation tests. It did not reach Save. No success is inferred from a confirmation click, helper-script download or an offline result.

### Before-and-after read-back

| Target field | Before | Final read-back |
| --- | --- | --- |
| ID | `33333333-3333-4333-8333-000000000002` | Same |
| Slug | `manual-test-garden` | Same |
| Name | Manual Test Garden | Same |
| Description | Isolated saved description. | Same |
| Category | nature | Same |
| Address | Isolated Santa Rosa test address | Same |
| Latitude / longitude | 14.3 / 121.1 | Same |
| Environment | Indoor | Same |
| Publication | published | Same |
| Photo | Original seeded blue mock PNG | Same reference; two original mock objects, no upload/removal performed |

The entire Museum sentinel record is unchanged. Destination count remains two. Mutation history and Save-response events are empty. These are unchanged-state checks, not proof of successful editing or real PostgreSQL foreign-key enforcement. See [before-edit-state.json](before-edit-state.json) and [final-state.json](final-state.json).

### Operator report and login obstacle

After being instructed to use the synthetic login and perform one edit, the operator selected **“The record or prefilled information was incorrect.”** The independent [first-run snapshot](attempt1/login-obstacle-state.json) shows **five `/admin/login` POST responses with HTTP 401**, no Admin destination-management/edit GET, no Save response and zero mock mutations. Both seeded rows and photos remained unchanged. The available server evidence identified an obstacle before the edit form, **not a confirmed destination prepopulation bug**. The operator subsequently confirmed the visible message was **“Invalid email or password.”**

The operator was told not to retry login or Save and asked to describe only the visible page/error, never entered credentials or sensitive browser data. The cause of the rejected submissions is not yet established; no request body, password, email input or token was inspected or logged.

An independent in-process clone of the existing synthetic fixture accepted its known dummy login and returned **303 → `/admin`**: [qualification code](qualify_synthetic_login.py), [sanitized result](synthetic-login-qualification.json). This did not contact the running manual server, create a real authentication session, or consume another browser login attempt. It confirms the fixture's intended login contract; it does not establish what the operator submitted or resolve the actual-browser failure. No production authentication or application-source fix was made.

### Fill-only helper and controlled restart

To remove manual transcription from the next fixture login, the test wrapper now adds **Fill synthetic Admin credentials** on `/admin/login`. Its [local script](fixture-login.js) writes only the existing public fixture constants into the two controls; it neither reads/logs their old values nor submits the form. The operator must still click the original **Log In** button once, through unchanged origin/CSRF/password-adapter/membership/session checks. This is not an authentication bypass or a production feature.

The first owned server was shut down and exited with status 0. Its ready/state/identity/final records were archived under `attempt1/` before restarting a single server on the same dedicated port, without the reloader. Fresh state again contained exactly two original rows/photos, zero edits and no unexpected outbound transport attempts. Restart intentionally discarded only synthetic process-local sessions. No normal application server, real Auth session or real account was changed. The browser reconfirmed ID `299a0509f5c11384298580c6`; the prior marker could not authorize POSTs in that run.

The operator then reported **“Login still showed an error.”** Independent evidence shows exactly one restarted-run Admin login POST returning **401**, with no catalog/edit request or Save. The helper script was served with 200; delivery alone does not establish that its fill action executed or what was submitted. No operator-entered credential was inspected to resolve that uncertainty.

The repeat-login stop condition was applied. No more manual login, Save, validation or photo actions were requested. A final check showed zero mutations and unchanged records/photos, then the identity-checked fixture stop endpoint shut down the second owned server; it exited with status 0. The user's private browser and any normal RosaGo server were not stopped.

### Complete-wrapper offline qualification

To distinguish incomplete mocking from the manual failure, [qualify_full_wrapper.py](qualify_full_wrapper.py) exercised the **complete current wrapper**, two-record backend, identity marker, exact `127.0.0.1:5096` origin, existing Admin route and membership/session wiring through a Flask test client. A fake server object prevented any listener from starting.

Result: **confirmation 303; synthetic Admin login 303 → `/admin`; target edit GET 200 with Manual Test Garden prepopulated**. No Save was performed, no request reached the manual server and no live provider was contacted. The result is [full-wrapper-qualification.json](full-wrapper-qualification.json); separately labeled artifacts are under [qualification](qualification/README.md).

This confirms the intended complete fixture contract accepts the fixed dummy input, but does **not** explain the actual-browser 401 or prove manual success. The manual rejection's cause remains unknown. There is no confirmed application editing bug or basis for changing production authentication from this evidence.

## 6. Decision

**NO-GO for editing real destinations. Connection/instance identity: PASS for the observed browser path. Complete manual editing: BLOCKED by the synthetic login failure.** No actual Save, published-change synchronization or manual validation/photo PASS is claimed. Even a passing mock walkthrough would not establish real hosted RPC/RLS/Storage permissions or override existing production readiness blockers.

No operator-entered passwords, emails, session cookies, access/refresh tokens, CSRF values, request bodies or API secrets were collected. Known public dummy constants exist only in the explicit test fixture/control; they are not real account secrets. Durable manual evidence contains only identifiers, path/status events and synthetic destination state.

The isolated run is closed. Do not use its old URL or substitute the normal application/production data. The remaining prerequisite for a future manual run is successful synthetic login in that same confirmed browser while preserving all existing checks. No new Windows PID verifier, production Auth change or further retry is authorized by this report. Stop here; any real destination or Storage write still requires separate explicit approval.
