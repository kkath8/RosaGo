# Local destination image integration — 2026-11-08

Local implementation is complete. No uploads, hosted writes, SQL execution,
publication or live sign-ins occurred. Remote deployment remains **NO-GO**.
Completed image scanning, matching, sanitization and upload validation were
not repeated. Original downloads and prior staging/evidence are preserved.

## Destinations without matching photos

| CSV record | Destination |
| --- | --- |
| 65 | Mabuhay Homes Basketball Court |
| 66 | Golden City Clubhouse Basketball Court |
| 67 | Balibago Court |
| 70 | Terrazas de Teodora Pavilion and Resort |
| 71 | Garden Villas 1 Clubhouse (Pool) |
| 72 | Summer's Place Resort |
| 73 | Popong Resort |
| 74 | Paseo Premiere Hotel |
| 75 | Hotel Sogo Santa rosa |
| 76 | El Cielito Hotel - Sta. Rosa |
| 77 | My Hotel Sta. Rosa |
| 78 | Sans Hotel |
| 80 | Candy Inn Motel |
| 81 | E.M. Drive Inn |

## Completed local behavior

The shared `static/img/destination-placeholder.svg` is generic artwork labelled
"Photo unavailable", not a fabricated destination photo. It is used by User
destination cards, details, recommendations, itinerary previews and dynamically
rendered saved/visited cards, plus Admin photo previews/details. A scoped error
handler also substitutes it when a recorded cover fails to load, without a
retry loop. It leaves unrelated avatars/images alone. Placeholder paths are
presentation only: they are never written to `image_url`.

Admin Create/Edit retains its existing multipart upload, CSRF, permission,
validation and audited mutation flows. Local selection previews a blob URL;
cancellation restores the existing image or placeholder. Replacement, explicit
removal and unrelated edits retain their existing semantics. Blob URLs are
released on replacement/page exit. Existing saved URLs are not replaced by
placeholder URLs. No upload size, MIME, Storage URL or security rule was relaxed.

## Final image disposition

[destination-images.final-mapping.review.json](destination-images.final-mapping.review.json)
binds the completed review and upload-payload evidence by SHA-256, without
opening/scanning images again. It contains all 98 destination rows:

| Disposition | Count |
| --- | ---: |
| Preserve existing hosted cover exactly | 3 |
| Proposed local attachment, separate approval required | 79 |
| Render placeholder: no matching photo | 14 |
| Render placeholder: held court photo | 2 |

Enchanted Kingdom, Chowking Balibago and Santa Rosa City Auditorium retain
their existing hosted covers. Nuvali Sand Courts (#56) has no selected image:
the incorrect indoor badminton photo remains unassigned. Winner Badminton
Court (#58) also remains unassigned pending venue identity confirmation. Its
candidate shares the same source bytes. The WalterMart branch and all other
proposed assignments still require owner approval. The mapping intentionally
does not invent Storage URLs, approve uploads or change publication status.

The file-based catalog remains review material; it is not an active runtime
data source or an automatic importer. Existing Admin/User applications continue
using their existing Supabase destination table. New local photos are not yet
available in hosted records merely because this review package exists.

## Focused offline verification

- **100 Python tests passed** in 12.218 seconds, with socket connection attempts
  prohibited. Coverage: new image view/mapping tests, Admin photo routes,
  destination routes, itinerary recommendations/preview UI, public layout,
  functional completion and provider-session admission checks (7 of the 100).
- **8 JavaScript tests passed** using the actual scripts in a simulated DOM:
  fallback behavior, dynamically inserted/cached failures, unrelated images,
  same-origin/prefixed fallback configuration, Admin create/edit previews,
  cancellation/removal, invalid files, blob cleanup and submit controls.
- JavaScript syntax checks passed for destination-images.js, admin.js and
  user-ui.js. Existing image-validator and route safeguards remain intact.

These are offline route/DOM tests with synthetic images and mocked SDK calls,
not live authentication, actual Storage uploads or a visual browser acceptance
test. Device/browser visual acceptance remains pending an authorized local
session/testing procedure. No existing image payloads were revalidated here.

## Remaining gates

The previous mapped-only publication review remains unchanged: **0 approved
geographic verifications / 98 held Draft in the proposed plan**; the existing
35 hosted Published rows were not changed. This does not reclassify valid
numeric coordinate pairs as verified geographic evidence. Identity/coordinate,
alias/archive, description, tourism/category and migration decisions remain
as documented in [SCHEMA_AND_IMAGE_INTEGRATION_REVIEW.md](SCHEMA_AND_IMAGE_INTEGRATION_REVIEW.md).

The provider restore/replay blocker remains unresolved; see
[PROVIDER_SESSION_IMAGE_STAGE_NOTES.md](PROVIDER_SESSION_IMAGE_STAGE_NOTES.md).
No security or session code was changed for the image work. Hosted image upload
and audited assignment need separate exact-change approval after identity
review; publication and deployment need their own outstanding qualifications.

Changed implementation/test files and their final hashes are listed in
[image-integration-local-files.json](image-integration-local-files.json).
