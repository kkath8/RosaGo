# Phase 6C-1 local draft lifecycle

`0005_itinerary_draft_lifecycle.sql` is LOCAL and UNAPPLIED. The task reports
0001–0004 as live/applied; their bytes and historical notes are untouched. Do not
interpret the old draft-status comments as permission to rerun them. No remote
database or provider was contacted. No route, UI or application startup wiring
is added. This phase does not implement review, generation, preview or Save.

## Database API

- `public.rosago_itinerary_draft_create()` returns one row containing
  `draft_id uuid, state text, revision bigint`. Owner is exclusively auth.uid().
  State is editing, schema_version=1, revision=1. Existing table defaults supply
  UUID/timestamps/24-hour expiry; preferences, preview and saved fields are NULL.
- `public.rosago_itinerary_draft_update_preferences(p_draft_id uuid,
  p_expected_revision bigint, p_preferences jsonb)` returns the same minimal
  columns with revision N+1. Only preferences and revision are assigned; the
  existing metadata trigger handles updated_at. Expiry and other fields stay put.
- `public.rosago_validate_draft_preferences(jsonb)` is a private invoker helper,
  not a caller-accessible RPC. It validates and returns the complete v1 snapshot.

Create is not idempotent: an ambiguous transport failure must not be blindly
retried. Recovery/listing and create quotas are outside this minimum phase.
Each call creates one bounded row; there is no bulk create or cleanup operation.

## Preference contract v1

Version lives in the draft's schema_version column, not a caller-supplied JSON key.
Each successful update replaces the entire snapshot. Partial quiz progress is
not accepted by this API; a newly created draft can have NULL preferences until
the first complete submission. These are the only keys:

| Key | Contract |
| --- | --- |
| interests | Required JSON array of 1–6 unique strings from attraction, dining, shopping, accommodation, nature, heritage; order preserved |
| companion_type | Required solo/couple/family/friends/group string |
| budget_centavos | Omitted or JSON null means unknown; otherwise integer 0–10,000,000, PHP per person for the whole itinerary |
| start_date / end_date | Required exact YYYY-MM-DD strings, valid Gregorian years 1–9999; end >= start, at most 7 inclusive days |
| daily_start_time / daily_end_time | Required exact HH:MM:SS local strings, hours 00–23 and minutes/seconds 00–59; end > start, no overnight; 24:00:00, fractions/offsets/alternate spellings are rejected |
| transportation | Required walking/private_car/public_transport string |
| timezone | Optional input; if present must be exactly the string Asia/Manila; server always writes Asia/Manila |

Canonical stored JSON has all nine keys: missing budget becomes explicit null,
missing timezone becomes the server constant. No malformed values are repaired,
trimmed, coerced, or silently dropped. Unknown keys, null required fields, wrong
types, duplicate interests, invalid enums/dates/times and oversized documents
are rejected. Input JSONB text is bounded to 16 KiB before semantic processing.
Valid fields themselves have small fixed bounds; canonical defaults cannot
expand a valid snapshot beyond that bound. JSONB determines object key ordering;
this is a canonical shape, not a cryptographic serialization/fingerprint format.

Budget validation rejects fractional/decimal text, negative values and strings.
JSONB has already parsed numeric notation (and collapsed duplicate object keys)
before the function runs; it cannot recover original wire syntax. The Python
API accepts actual int, not bool/float, and dict input, never raw JSON text.
Future HTTP handlers must define parsing/duplicate-key policy at their boundary.

## Security boundary

Authenticated users retain SELECT-only table privileges and existing RLS. No
table write grants or write policies are added. Since invoker functions cannot
write under those ACLs, only the two narrow RPCs are SECURITY DEFINER. They are
explicitly owned by trusted postgres, matching the existing 0001 ownership
convention. This is a privileged boundary: postgres has broader powers than
these functions exercise, so review their exact bodies/ownership before applying.
There is no runtime service_role key, new client, role switch, or dynamic SQL.

Both RPCs require non-NULL auth.uid(); create accepts no arguments and update
accepts no owner/state/preview/save fields. The update checks ownership twice,
including in the mutation predicate. This is mandatory despite RLS because the
function owner can bypass RLS. Functions have fixed empty search_path and
qualified relation/helper references. Default EXECUTE is revoked from PUBLIC,
anon, authenticated and service_role; only the two public operations are granted
to authenticated. The validator remains private. Existing ownership guards and
all trip/place functions/policies are unchanged.

Trust remains in verified Supabase JWT claims consumed by auth.uid(), not Python
user_id, browser parameters, or function owner's identity. The Python context
check enforces its calling contract; database ownership is independently enforced.

## Atomic revision and expiry

Update does not restrict transaction isolation, validates input, locks only the owned draft FOR
UPDATE, then performs the conditional UPDATE and RETURNING in the same RPC
transaction. The predicate checks editing, schema_version=1, revision=N and
expires_at > clock_timestamp(). Wall-clock time is evaluated after the lock wait,
which also rejects expiry that occurs while waiting (stronger than transaction-
start now()). Expired rows are not deleted or automatically relabeled.

Only one concurrent update with revision N can succeed; a competing update is
rejected by the revision check or PostgreSQL's serialization handling, depending
on transaction isolation. No automatic retry is added. Expected revision must be 1–9223372036854775806
to prevent increment overflow. Missing, foreign, stale, expired and non-editing
rows share a fixed P0002 rejection; no row state or foreign existence is exposed.
Any failure aborts the whole transaction. There is no Python read-then-write or
automatic retry. Concurrent updates may consume a revision even with identical
preferences: every successful update advances exactly once.

## Python service and errors

`itinerary_draft_service.py` exposes:

- `create_itinerary_draft(context) -> DraftResult`
- `update_itinerary_draft_preferences(context, draft_id, expected_revision,
  preferences) -> DraftResult`

The existing AuthenticatedContext/client is caller-owned; the service neither
creates nor closes it. The immutable redacted result contains only draft ID,
editing state and exact expected revision. Each write uses `.retry(False)`.
Local validation mirrors the wire contract; SQL remains authoritative for direct
RPC callers. Response shape, UUID, state and revision are checked strictly.

| Failure | Domain error |
| --- | --- |
| Invalid local input / SQLSTATE 22023 | DraftValidationError |
| P0002 rejection / 42501 authentication or authorization denial | DraftRejectedError |
| Other provider errors / HTTP transport failures | DraftUnavailableError |
| Malformed or inconsistent response | DraftConsistencyError |

All domain messages are fixed; provider diagnostics are not retained in exception
chains. Programming/control-flow errors propagate. An unavailable or inconsistent
write response does not prove that the operation failed to commit.

No route exists yet. Future browser-facing routes must follow existing login,
server-owned context, strict form, CSRF, Origin, no-store, and Jinja isolation
patterns from app.py. This service adds no browser cookie state or auth changes.

## Validation limits and pre-application review

Static migration tests inspect text, signatures, ACLs, ownership checks, revision
predicates, bounds, and hashes of 0001–0004. Python tests use mocked clients with
network/client-creation guards. Neither proves SQL runtime validity or live RLS.

Before separately authorized application, validate in a disposable database:

- Parsing/execution of functions, installed PostgreSQL/PostgREST behavior and
  one-row RETURNING responses; actual function owners/ACLs and helper execution.
- Real authenticated JWT subjects for two users, anon and missing subject;
  confirm direct table writes and private helper calls remain denied and that
  SECURITY DEFINER still reads the caller's auth.uid(). Review default privileges.
- Full invalid-input matrix, multibyte/oversized JSON, integer notation after
  JSONB parsing, leap dates, valid 23:59:59, rejected 24:00:00 and revision overflow boundaries.
- Two simultaneous N updates, state changes and expiry during lock waits;
  exactly one increment, revision rejection/serialization failures across isolation
  levels, complete rollback, no expiry extension.
- Existing metadata/owner triggers under the definer and transaction timestamp
  behavior; unchanged existing trip/place/auth behavior.
- Function-name collisions and migration order. Do not use CREATE OR REPLACE
  or rerun applied migrations to bypass unexpected objects.

No SQL was applied, and no claim of verified live authorization is made here.
