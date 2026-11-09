# Add Destination and photo management — isolated next steps

Real editing/persistence/public-detail synchronization/restoration were observed on 2026-11-07. The first description Save deviated from the approved append text; a separately approved restoration returned the exact original. No hosted creation or photo-management permission follows from that run.

## Existing isolated checks

**9 tests passed; 6 subtests passed.** Existing test fixtures block real network transports and use synthetic Auth, PostgREST and Storage doubles.

Selected tests:

- ManagementRouteTests: test_create_edit_and_full_publication_lifecycle; test_direct_mutations_require_auth_membership_csrf_and_exact_origin; test_invalid_creation_retains_values_and_never_calls_mutation.
- PhotoValidationTests: test_actual_formats_and_metadata_are_validated_not_just_filename; test_empty_oversized_svg_truncated_oversized_dimensions_and_animation_rejected.
- PhotoRouteTests: test_upload_replace_unrelated_edit_remove_and_admin_rendering; test_storage_error_and_timeout_do_not_save_or_expose_credentials; test_database_failure_keeps_old_image_and_does_not_delete_uncertain_upload; test_duplicate_files_and_forged_image_urls_are_rejected.

These establish mocked route/service behavior, not successful real Storage uploads or hosted destination creation. No production code changes were needed.

## Next focused isolated browser exercise

1. Open the actual Add Destination template in a fresh loopback-only fixture browser. Create one clearly synthetic destination with no photo. Require exactly one native POST, redirect, generated stable ID/slug, Draft status and one audit event in the mock contract.
2. Reopen its Admin details/form and compare every field. Confirm User Explore/details/maps exclude the Draft and existing synthetic records are unchanged.
3. Try a required-field failure and an invalid image. Require retained entered values, a useful validation message and zero database/Storage mutations.
4. Add one valid generated test image through mocked Storage only. Verify unique object path, safe decoded/re-encoded content, correct reference and no overwrite of an existing object.
5. Simulate Storage error and uncertain database response. Confirm no retry, no duplicate destination, no exposed secret and no blind deletion of an uncertain uploaded object.
6. Verify ordinary User/Admin membership/CSRF/Origin denial and immediate duplicate-click protection. Do not activate experimental session adapters.

Only synthetic fixture state may change. Keep the fixture independent of the real port 5055 instance and operator browser.

## Hosted approval boundary

Do not create a real destination, change publication, upload/replace/remove a real photo, or delete any Storage object.

Before any later hosted test, prepare a concrete proposal with exact name/text, new-record identity expectations, initial Draft visibility, audit effects, photo/byte-backup scope if applicable, and an approved cleanup procedure through supported Admin actions. Obtain separate explicit approval. Avoid using an existing real destination as a photo-test fixture.
