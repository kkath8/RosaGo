# Phase 6C-2A: expanded draft preferences

Status: **local, unapplied**. The user reports 0001–0005 live and Phase 6C-2
browser-tested. Older migration comments describe historical development status;
they are not permission to rerun those migrations. Their files remain unchanged.

## Architecture and scope

Draft preferences already live in bounded JSONB. Migration 0005's private
validator rejects unknown keys and has the old transportation enum, so 0006 is
necessary. It replaces only `public.rosago_validate_draft_preferences(jsonb)`.
No table, column, policy, trigger, public RPC signature/body, or stored row changes.
The existing create RPC still makes an empty editing draft. The existing update
RPC still validates a complete snapshot, locks an owned row using `auth.uid()`,
checks editing state, schema version, expiry and expected revision, and increments
exactly once. Generic rejected mutation behavior and no automatic retry remain.

The replacement keeps SECURITY INVOKER and an empty search_path, explicitly
retains postgres ownership, and revokes all application-role EXECUTE privileges.
CREATE OR REPLACE preserves the helper's identity/dependencies and existing ACLs;
the explicit revoke reasserts the private boundary. The only SECURITY DEFINER
functions remain the unchanged create/update RPCs from 0005. Authenticated table
access remains SELECT-only through existing RLS. Python uses the caller's existing
AuthenticatedContext, never a new client. CSRF/Origin, exact form fields, upload
rejection, private no-store responses and Jinja authority isolation are preserved.

## Canonical document

Every new successful write stores exactly these fourteen keys:

| Key | Contract |
| --- | --- |
| interests | 1–6 unique attraction, dining, shopping, accommodation, nature, heritage values |
| other_interests | Trimmed text up to 200 Unicode code points, or null |
| companion_type | solo, couple, family, friends, group |
| budget_centavos | null or integer 0–10,000,000; PHP per person for the entire itinerary |
| start_date / end_date | Exact valid YYYY-MM-DD, years 1–9999, end >= start, 1–7 inclusive days |
| daily_start_time / daily_end_time | Exact HH:MM:SS, hours 00–23, minutes/seconds 00–59, end > start |
| transportation | walking, bicycle, motorcycle, private_car, public_transport, ride_hailing, mixed_transport |
| trip_pace | Required relaxed, balanced, packed |
| activity_preferences | Required 1–6 unique sightseeing, food_trip, shopping, outdoor_activities, culture_heritage, relaxation |
| environment_preference | Required indoor, outdoor, mixed |
| additional_preferences | Trimmed text up to 500 Unicode code points, or null |
| timezone | Server constant Asia/Manila |

Array order is retained. No arbitrary keys or nested preference objects are
accepted. SQL/Python service callers may omit optional budget/text/timezone keys;
canonicalization adds nulls and the server timezone. A supplied timezone must be
Asia/Manila. Browser forms must contain each scalar control exactly once, even
when its optional value is blank. Only interests and activity_preferences repeat;
absent checkbox lists are validation errors. CSRF and expected_revision are the
only infrastructure fields; neither is stored in preference JSON.

The form accepts strictly HH:MM and appends :00. Stored HH:MM:SS from old snapshots
remains readable and is shown exactly in Review; minute-resolution edit controls
show HH:MM. Money uses Decimal, never floats. SQL retains the 16 KiB JSON envelope
bound and all prior constraints, with an explicit end-year bound matching Python.

## Free-text trust boundary

Free text is **untrusted user preference data**, never instructions or trusted
place/category IDs. Literal HTML-like strings, SQL-like strings and JSON-like
strings are retained as text; no HTML rendering, SQL interpolation, JSON parsing
or instruction execution occurs. Jinja autoescapes both stored and rejected form
values. Leading/trailing whitespace is trimmed; blank becomes null. Character
limits apply after trimming. SQL uses an explicit Unicode whitespace set matching
Python str.strip(), avoiding locale-dependent differences. PostgreSQL JSONB cannot
store NUL/unpaired surrogates; Python rejects these before RPC execution.

Future AI integration must keep these strings separate as contextual data. They
must never override authorization, database rules, deterministic eligibility,
budget/date/time constraints, valid place IDs, or system/developer instructions.
Controlled interests remain mandatory. Activity and transport choices are signals,
not place IDs, routing claims or weather-aware behavior. No AI, prompts, scoring,
weather, routes, itinerary generation or fabricated previews are implemented.

## Backward compatibility and deployment

Schema version remains 1: it is the existing draft envelope version. The reader
recognizes an exact canonical legacy nine-key document only when **none** of the
five extension keys is present. It validates old transport choices and all original
fields. Otherwise it requires the complete expanded contract; partial extensions
are rejected. Canonical snapshots are compared with validated results so malformed
stored data is not silently normalized on read.

Reading never writes or backfills choices. Review displays missing new choices as
"Not selected" and absent optional text as "Not provided". Editing legacy drafts
leaves pace/environment blank and activities unchecked. Their next successful
edit must submit all new required choices and uses the original revision token.
Old open forms must reload; after 0006, old-contract writes fail validation.

Deploy the application and 0006 together in a controlled write pause: the new
application cannot save expanded JSON through the old validator, and an old
application cannot safely read expanded snapshots. Legacy reads in this updated
application work before and after migration. No automatic migration runner exists.

`trip_itinerary` retains its original typed transportation constraint and lacks
the new fields. This phase never writes that table. A future final Save design
must explicitly address persistence of the expanded model; do not pass new draft
values into the old saved-itinerary schema without a separately reviewed change.

## Verification and exact pre-application steps

Offline tests cover parsing, service canonicalization, old/new reads, route
security, literal-text escaping, every enum, character bounds, unchanged migration
hashes, and 0006's structural scope/security. They do **not** execute PostgreSQL or
establish live RLS behavior. Do not apply 0006 based solely on static tests.

1. Review the complete diff and this migration. Verify migration history and
   checksums for 0001–0005 against the intended environment; never edit or rerun
   them. Confirm 0006 has not already been applied. Stop on unexpected drift.
2. With separately authorized database access, inspect the existing helper's
   signature, definition, postgres ownership, ACLs and search_path, plus the
   unchanged create/update RPCs, SELECT grants and RLS policies. Save these
   definitions/ACLs and take a recoverable database backup before rollout.
3. Restore a disposable database from the approved 0005 baseline (do not rerun
   0001–0005). Apply only 0006 there in its transaction. Confirm it compiles and
   commits. Exercise all new enums, wrong JSON types/nulls, arrays, text limits,
   Unicode whitespace, optional normalization and original constraints through
   the existing update RPC. Verify old snapshots still read without backfill.
4. In that disposable environment, use authenticated subjects for two users;
   test anon/missing subject, denied private-helper execution and direct writes,
   foreign/missing drafts, expired/non-editing drafts and concurrent revision-N
   updates. Confirm exactly one N+1 success, generic rejections, no trips rows,
   unchanged expiry, and rollback on rejected input. Check actual resulting ACLs.
5. Validate the updated application against that environment: create, edit,
   review, legacy upgrade, stale-tab 409 and escaped text. Preserve a rollback
   plan: pause writes and keep compatible readers if expanded snapshots exist;
   do not blindly roll back to the old application/validator or delete new data.
6. Obtain separate live-application authorization after those checks. During a
   controlled itinerary-write pause, apply **only 0006 once** using the approved
   migration process and deploy this compatible application. Verify function
   definition/ACLs and an authorized smoke test, then resume writes. Do not rerun
   0001–0005 or use startup hooks to apply any migration.

No database application, external service contact, commit or push is part of
this implementation. Live rollout remains a separate authorized operation.
