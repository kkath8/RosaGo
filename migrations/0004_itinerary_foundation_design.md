# Phase 6B: local itinerary foundation

Status: **unapplied local draft**. `0004_itinerary_foundation.sql` is the next
migration after 0001–0003. The task records those three as already applied;
the older README/0003 static-test wording still calls 0003 unexecuted. That is
historical documentation, not authority to rerun it. No live state was inspected.
No SQL, migrations, external APIs, or application startup hooks were executed.
Do not apply 0004 without separate authorization and database verification.

## Scope and compatibility

Only three optional child tables, their indexes, two invoker-only helper
functions, three triggers on **new tables**, ACLs, and SELECT policies are added.
No existing schema, function, policy, projection, route, service, or data changes.
Manual trips need no itinerary; memberships need no stop plan. The composite
`trip_places(trip_id, place_id)` primary key continues to prevent duplicate places.
`trip_places.position` remains the only global destination order, including gaps.
Publication/unavailable-place behavior remains governed by 0002/0003 and current
services. There is no provider, weather, routing, cost, prose, or scoring storage.

No Python contracts are added: nothing consumes them yet. No destructive rollback
script is added in this phase; existing rollback scripts must not be used to
remove parent tables after 0004. Review dependent objects before any future rollback.

## Tables and bounds

### itinerary_drafts

UUID identity, Auth owner, constrained lifecycle, schema version 1, positive
revision, nullable preference and preview objects, timestamps, and fixed expiry.
Empty editing drafts can have NULL preferences. Generating/preview-ready/saved
states require preferences; preview-ready requires a preview. Failed/expired
drafts may retain bounded documents for owner review until cleanup.

Preferences are bounded to 16 KiB and preview to 256 KiB of JSONB's serialized
text (uncompressed logical bytes, not compressed storage size). These are initial
engineering caps, **not a completed JSON schema**. Only object/type/size and
basic state consistency are enforced here. Before enabling any writer, define
strict versioned keys, unknown-key handling, nested/array bounds, and validate
preferences against all typed saved-preference rules. Partial editing input must
remain clearly distinguished from a validated generation snapshot. Preview
schema/acceptance rules are deliberately deferred. An object passing SQL CHECKs
is not automatically a validated preference snapshot or accepted preview.

Expiry defaults to creation plus 24 hours and cannot exceed that deadline.
Timestamps must be finite; expiry must follow creation. Time passing does not
update a state column: future operations must compare database wall-clock time
with `expires_at` even if `state` still says preview_ready. No cleanup job exists.
Expired drafts remain owner-readable; future retention/cleanup needs a separate
decision, including saved tombstone retention for idempotency.

The draft UUID itself is the save idempotency key. `accepted_preview_digest` is a
64-character lowercase SHA-256 digest, accompanied by `saved_at`. Saved-trip links
are unique when non-NULL. A trigger verifies that the referenced trip belongs to
the draft owner; the FK alone would not establish that. Trip deletion sets the
link NULL while retaining saved state/time/digest, so future Save must return
"already saved; trip deleted", never recreate a trip. A saved row with no trip
link is reserved for this tombstone case; future Save must insert the link in its
transaction. Direct application writes are denied, so clients cannot manufacture
that state. When present, `saved_at` must be finite and >= `created_at`; it is not
constrained to be earlier than `expires_at`. Draft expiry eligibility belongs to
the future validated Save RPC. Later FK cleanup may update `updated_at` after
expiry. Cleanup must not convert saved drafts to expired.

### trip_itinerary

One row per existing trip, cascaded on trip deletion; ownership is not duplicated.
Typed interests, companion type, optional budget, inclusive dates, daily window,
transportation and timezone. Names/owner IDs are not copied from trips.

- Interests: one-dimensional, ordinary one-based array, 1–6 distinct non-NULL
  members of the six existing place categories. The immutable SQL helper uses
  count-distinct versus cardinality to reject duplicates and NULL elements.
- Companions: solo/couple/family/friends/group.
- Budget: NULL or 0–10,000,000 integer centavos, always PHP per person for the
  entire itinerary. The PHP 100,000 ceiling is an explicit initial design cap
  for review. NULL means unspecified; it is never converted to zero or treated
  as a factual cost estimate. Currency/scope are fixed contract constants, not
  redundant per-row fields.
- Dates: years 1–9999, inclusive length 1–7 days. No "must be in future" rule.
- Local times: end strictly after start; no overnight window.
  The same window applies each day. PostgreSQL time precision is retained.
- Transportation: walking/private_car/public_transport. Timezone: Asia/Manila.

`trips.visit_date` is existing optional manual-trip metadata; itinerary dates
represent a multi-day range. Future Save should initialize visit_date=start_date
for existing Trip Detail compatibility. Existing editing of visit_date remains
possible; detect divergence as needing review, do not silently rewrite dates.

### trip_stop_plans

Composite primary key/FK to an existing membership; membership deletion cascades
to its plan. No extra order/position or duplicate place entry. Date can be NULL;
times must both be absent or both present, with end > start. Timed plans require
a date. Date-only plans are allowed. Source is manual/recommended; keep_place
defaults true, preserving manual selections by default. Missing stop plans must
also be interpreted as manual/preserved by future recommendation code.

No mandatory FK to trip_itinerary: a manual membership may have planning metadata
without a generated itinerary. Date/window containment and cross-stop conflicts
are future transactional validation, not cross-table CHECKs. Existing membership
edits may invalidate schedules; retain the old schedule as needing review rather
than blocking current manual-trip operations. Removal still cascades its plan.

## Ownership and write boundary

RLS is enabled on all new tables. Authenticated users get SELECT only: drafts by
`auth.uid()`, extensions by an owned `trips` row. There are no anonymous policies
and no INSERT/UPDATE/DELETE policies or grants. Default grants are explicitly
revoked from PUBLIC, anon, authenticated and service_role. Helpers have no direct
application EXECUTE grant, use SECURITY INVOKER and an empty search_path. Trigger
checks additionally reject updates of owner, primary keys, and creation time.
Timestamp triggers update only the new tables and are not revision counters.

This intentionally provides **no usable draft-write/Save API yet**. The current
SECURITY INVOKER trip RPC pattern cannot write these tables under these ACLs.
A later reviewed migration must choose the write boundary explicitly: e.g. narrow
RPCs owned by a restricted non-login role with only necessary privileges, explicit
auth.uid() checks, fixed search_path, and a complete document validator. Do not
simply grant table writes to authenticated, elevate Flask, or use service_role.
Any SECURITY DEFINER choice is future security work, not implemented/approved
here. Existing trip RPCs remain invoker-only and unchanged.

## Revision and schedule freshness

Draft revision is a positive optimistic concurrency token. Future mutations must
lock the row, match expected revision, and increment exactly once. Generation
must not publish results against a revision that changed while work was running.
An async job must carry draft identity/revision rather than cookie-stored state.

Saved schedules have positive `schedule_revision`, fingerprint version 1, and a
nullable SHA-256 baseline. NULL means unvalidated/needs review. A non-NULL value
is meaningful only after recomputing and comparing a canonical snapshot. Do not
infer freshness from it, schedule_revision, or trips.updated_at alone.

Proposed fingerprint v1 input is a versioned canonical UTF-8 JSON object with:

- trip ID and current visit_date;
- every typed preference, including explicit NULL budget, fixed PHP/scope,
  dates/times/timezone; interests sorted as a set;
- **all** memberships in position order: place_id, position, and created_at
  (so removal/re-addition is also detectable);
- each membership's optional stop plan: date, times, source, keep_place, or
  explicit NULL for no plan. Do not include updated_at or the fingerprint itself.

Use lowercase UUIDs, fixed ISO date/time formats, UTC timestamp normalization,
integer money, explicit nulls and deterministic key ordering. Specify exact
serialization/test vectors before implementing version 1; digest storage alone
does not freeze a language-specific JSON encoding. Include the entire membership
set, including unpublished/unavailable places, never only a visible/paginated
detail page. Do not assume the current 50/100 row page size is a trip size limit.

Future validation/save code must lock the parent trip **before** reading this
snapshot in READ COMMITTED, matching the existing membership RPC lock order;
all future preference/plan writers must acquire that same parent lock. Concurrent
changes then cannot produce a false fresh baseline. Increment schedule_revision
and store the new fingerprint only after full schedule validation and acceptance.
If the snapshot differs, preserve manual places and require review. This detects
state differences without modifying existing triggers. A change later reverted
to exactly the same canonical state need not remain stale. This is not a claim
about provider facts/publication freshness; those require independent rechecks.

## Atomic Save: deferred, proposed contract only

No Save RPC is in 0004: preview shape, acceptance semantics, and secure write
privileges are not settled. Proposed interface:

`rosago_itinerary_save(p_draft_id uuid, p_expected_revision bigint,
p_accepted_preview_digest text) -> (trip_id uuid, saved_revision bigint)`

No owner ID, client-provided memberships, or replacement preference JSON argument.
The eventual preview must bind the reviewed trip name, preferences, selected
published IDs, order, dates/plans and preservation flags into one accepted digest.
The current schema has room for this, but does not invent that document now.

One call, one transaction, no provider/network work inside the transaction:

1. Require non-NULL auth.uid(); reject unsupported isolation; lock the owned draft
   FOR UPDATE. Never reveal whether a foreign draft exists.
2. Handle saved-state retries first: same accepted digest and original accepted
   revision return the same saved trip; differing requests conflict. A NULL trip
   link returns an already-saved/deleted result. Store revision as accepted+1 on
   Save and keep saved revision/digest terminal so retry matching is deterministic.
   This replay remains valid after the original draft expiry; it performs no write.
3. For a new save, check expected revision, preview_ready, supported schema and
   database wall-clock expiry. Validate the stored preview and its canonical
   digest against explicit user acceptance. Do not trust JSON owner/publication.
4. Validate the complete preference snapshot, bounded unique place selection,
   schedule/date/window/conflict rules and manual-place preservation. Resolve
   every place against current published database rows. Define publication lock
   behavior (locks that conflict with status updates, in stable place-ID order)
   and selection/name/count bounds before implementation. Unknown costs stay NULL.
5. Create trips using verified ownership, then the optional itinerary extension,
   memberships in accepted global order, and matching stop plans. Lock existing
   parents first in any future update-existing-trip variant; that variant is not
   part of this proposed create-only Save contract.
6. Compute the validated full fingerprint, associate saved_trip_id, set saved
   state/time/digest and increment draft revision. Check expiry again at the final
   write. Any validation/constraint/permission failure rolls back **all** writes.
7. Concurrent saves serialize on the draft lock. After an ambiguous network
   outcome, reconcile through the same idempotent request; never issue independent
   create calls. A conflicting digest/revision must not create another trip.

The server retains full private draft/preview state. Browser cookies hold only
the existing opaque session reference, never full itinerary documents.

## Verification and manual review before application

Offline text tests cover declared constraints, exact ACL/policy scope, membership
FK, identity guards, no competing order, additive-only scope and checksums of
0001–0003. They **do not parse/execute PostgreSQL or prove live Supabase RLS**.
Existing trip/place tests use offline mocks and do not establish live behavior.

Before a separately authorized application, review and test in a disposable DB:

- SQL syntax/types/function privileges, Supabase default ACLs and actual roles;
  test two owners, anon and missing subject, plus rejected direct writes.
- Interest NULL/empty/duplicate/multidimensional/non-one-based arrays, date
  infinities and boundaries, leap dates, all NULL/time pairs and 24:00, money caps,
  multibyte oversized JSON and unsupported states/versions.
- Shared metadata trigger branch behavior; saved-link ownership and row locks;
  immutable IDs/owners; user deletion, trip deletion and membership deletion
  cascades, especially SET NULL retaining a saved draft tombstone.
- Existing authenticated trip deletes/remove/reorder with populated extensions
  and saved drafts. RI cascades must continue to work despite denied direct child
  writes. Check race/deadlock behavior and transaction rollback.
- Confirm 16/256 KiB caps, 24-hour deadline and PHP 100,000 budget ceiling.
  Define retention/cleanup separately; no scheduled jobs are introduced here.
- Verify no existing object-name collisions and migration order. Do not bypass
  unexpected objects with IF NOT EXISTS or CREATE OR REPLACE.
- Before enabling writes: finalize schemas, lifecycle transitions, acceptance,
  serialization vectors, Save replay/deletion behavior, dedicated RPC privileges,
  bounds, parent-first concurrency, and cross-row schedule validation.

No claim is made that 0004 is ready to apply without those reviews.
