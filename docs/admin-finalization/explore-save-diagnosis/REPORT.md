# Admin Explore Save — focused diagnosis

Verified 2026-11-07, Asia/Manila. **No real Save or restoration was submitted by this investigation.**

## Finding

**Synchronous submit-button disabling is not the reproduced cause.** A fresh headless Chrome instance, running the existing admin.js against the actual rendered Edit Destination template and Flask POST route with network-blocked Auth/DB/Storage doubles, successfully sent one native multipart POST, received 303, persisted the synthetic description, and showed the update in User Explore.

No application defect was reproduced, so **admin.js, the edit template and Flask route were left unchanged**. Changing their timing without evidence would not establish a fix for the original missing request.

The real-tab cause remains unresolved. The operator supplied the current URL ending in **/admin/places/enchanted-kingdom/edit**. That is the editor, not the post-success detail route. A marker inside its Description textarea can be unsaved; the isolated browser confirms that changing text alone sends no POST. The operator has not independently established that the earlier marker was on a newly loaded read-only detail page.

The previous hosted comparison and intended-server log did not show the description Save. Possible remaining explanations are unsent form state, a click that did not initiate native submission, a browser-specific handler/extension/error, or an uncorrelated tab/instance. **None is proven as the real-tab cause.** User-reported current validation success rules out a currently visible native validity failure but does not establish the historical attempt's state.

## Inspection and instance limits

- Form: native POST, multipart/form-data, no explicit action. Its action therefore resolves to the current edit URL. Save is a submit button inside the destination form.
- Admin template loads admin.js; it does not include the User form interceptors from user-ui.js or login.js.
- Destination submit handler does not call preventDefault or replace submission with fetch. It disables only the submit button; named destination controls remain enabled. The button has no required payload name.
- Browser constraints can stop a submission before the submit event; the isolated invalid-field case demonstrates that behavior. Backend rejection or redirect would require a request to reach the server and therefore cannot by itself explain a missing request.
- Existing backend POST route validates same-origin fields/CSRF/version, uses caller-owned audited RPC, and preserves the photo when no replacement/removal is selected.
- Known normal Flask PID **19740** remained alive. Seven recorded application/auth source hashes match the prepared instance. Native process/listener enumeration remains inconclusive here; multiple serving processes cannot be excluded independently. No personal browser profile or tab was inspected.
- The latest sanitized local-log review still showed only the historical Enchanted Kingdom photo edit POST; no additional target-description POST was observed. Other User-route requests were present but were not treated as this Save or investigated.

Current source inspection supports the intended route, but does not replace real-tab Network evidence.

## Files changed

Application files: **none**. Existing unrelated workspace modifications were preserved.

- [tests/test_admin_explore_edit.py](../../../tests/test_admin_explore_edit.py): added a description-only Save/restore regression, checking photo, identity, other fields, public reader and unrelated-record preservation.
- [browser_submit.mjs](browser_submit.mjs): focused fresh-Chrome test using native form activation, isolated origin and blocked external requests.
- [offline_bridge.py](offline_bridge.py): stdio bridge to existing network-blocked Flask/Auth/DB/Storage test doubles. It runs separately from the real app and uses synthetic browser cookies only.
- [browser-results.json](browser-results.json): sanitized requests/assertions; no real credentials, cookies, Auth responses or destination records.
- This report.

## Focused results

**Chrome: 6 checks passed, no JavaScript exceptions.**

1. Actual rendered form resolves to the correct POST target and is valid/enabled.
2. Typing a description alone causes no request.
3. Existing synchronous disable still allows native POST; immediate second button activation causes no duplicate.
4. The real Flask route returns 303 and the mocked SDK persists the description, preserving the photo and unrelated destination; zero Storage calls.
5. User public detail shows the saved published description.
6. Native validation failure stops POST.

The browser test posted only to an ephemeral loopback fixture, never port 5055 or Supabase. It used a fresh temporary headless profile; external browser traffic was blocked. The Python fixture blocks real network transports. Its initial test-bridge import-path error was corrected before the successful run; no production code was changed.

**Backend: 5 focused tests passed, with 9 subtests passed.**

Selected tests cover saved-row loading, existing-row/public Explore updates, description-only Save/restore, invalid fields/identity injection and non-Admin denial. They use existing isolated fixtures. No inventory/login audit or broad suite was repeated.

Commands:

    node docs/admin-finalization/explore-save-diagnosis/browser_submit.mjs

    .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_admin_explore_edit.py::ExistingExploreEditTests::test_catalog_and_details_edit_links_load_exact_saved_row tests/test_admin_explore_edit.py::ExistingExploreEditTests::test_edit_updates_existing_identity_and_public_explore_only tests/test_admin_explore_edit.py::ExistingExploreEditTests::test_description_only_save_and_restore_preserve_photo_and_other_fields tests/test_admin_explore_edit.py::ExistingExploreEditTests::test_invalid_fields_and_identity_injection_never_mutate tests/test_admin_explore_edit.py::ExistingExploreEditTests::test_non_admin_and_user_only_sessions_cannot_read_or_save

The isolated browser needed host-context process spawning because the sandbox rejected Node child-process creation. The approved run was limited to the same fixture/browser command; it did not attach to the operator's browser.

## Exact checks before any renewed real test

**Read-only checks first; do not click Save during diagnosis.**

1. Use the intended existing Admin tab at http://127.0.0.1:5055/admin/places/enchanted-kingdom/edit. Record whether the marker is in the textarea or on a read-only page. Do not interpret an editable value as persisted data.
2. Open browser Network before reloading. Reload the editor and correlate its fresh **GET /admin/places/enchanted-kingdom/edit, port 5055, HTTP 200** with the owned server's current log. Do not rely on a cached page or a historical PID file. If this cannot be correlated, stop.
3. Check Console for errors and form validity without submitting. Confirm the button is enabled, the form resolves to POST at the exact URL, all other fields/current photo match the fresh hosted baseline, photo input is empty and Remove photo is unchecked. Do not copy cookies, CSRF values, request bodies or HAR files.
4. Obtain **new explicit approval** for the exact one-Save test and gated restoration. Approval of this investigation authorizes no real write.
5. Only in that later approved test, require Network to show one POST to the exact edit URL, a response status and subsequent detail GET. Require a successful redirect to **/admin/places/enchanted-kingdom**, fresh hosted description/version/audit evidence and User detail synchronization before any restoration. On missing request, errors, ambiguity or unexpected changes, stop without retrying.

## Recommendation

**The existing Save flow works in isolated browser/backend testing; no production fix was justified.** The historical real-tab discrepancy is still unverified.

**Conditional GO for a separately approved observed retest after the fresh browser GET/server correlation and current-baseline checks pass. NO-GO for a real write under this diagnostic request.** This is not a claim that a confirmed production bug was fixed.

No hosted record/Storage/RLS/Auth/key change, real login, restoration, deployment, staging, commit or push was performed. Existing real application/session state was left untouched.
