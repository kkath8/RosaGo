# Phase 6D-7B: database preview lifecycle

Status: **APPLIED ONCE to the Supabase development project**, with successful
positive authenticated runtime verification reported by the operator. Do not
reapply migration 0007. Migrations 0001-0007 are now immutable; historical
pre-application comments in the SQL are preserved, not current deployment status.
The migration adds six functions, ownership/ACLs and transactional compatibility
assertions, without changing any table or trigger.

## Environment and canonical bytes

The operator verified target PostgreSQL 17.11 and the exact core hashing primitive
`pg_catalog.sha256(bytea)` with UTF8 conversion and hexadecimal encoding. The
implementation uses this core function instead of extension `digest`. This
computes the same SHA-256 algorithm without any
extension installation or search-path lookup. `convert_to(..., 'UTF8')` fixes
the bytes and `encode(..., 'hex')` fixes lowercase hexadecimal output. The
migration requires UTF8 server encoding and asserts a standard SHA-256 vector.

`rosago_preview_canonical_json(jsonb, integer DEFAULT 0)` recursively serializes
the validated JSON subset: object keys sorted with C collation, ordered arrays,
compact separators, signed 64-bit integer decimal values, JSON booleans/null,
and unnormalized Unicode strings. It explicitly escapes quote, backslash, and
control characters exactly as Python `json.dumps(ensure_ascii=False)` does.
UTF8 byte ordering agrees with Unicode scalar ordering; NUL/unpaired surrogates
cannot enter PostgreSQL UTF8 JSONB. Numeric decimal spellings are rejected, even
where JSONB equality would consider them equal to integers. It never uses JSONB
text as the canonical representation. Text casts are used only for size limits.

The helper is private and used only on schema-validated previews and bounded
catalogs/manifests, whose node counts are below Python's 10,000-node bound. It
also bounds recursion at 16 and bytes at 262144. It is not intended as a general
replacement for every Python `canonical_json` input-validation rule. JSONB has
already discarded duplicate input keys and some numeric lexical distinctions
(for example exponent spelling); the RPC validates JSONB values, not raw HTTP
JSON tokens. It does not infer raw-token properties from those values.

Five frozen domain/vector/hash combinations from `test_itinerary_preview.py`
are embedded as transactional application-time assertions, along with nested
key sorting and escaping checks. Offline tests compare the literal fixtures,
the explicit SQL algorithm's Python model, and the existing Python canonical
serializer. **These are static/model tests, not executed PostgreSQL results.**
Separately, all embedded compatibility assertions passed during the successful
live application. No local cluster, Docker service, or new dependency was introduced.

## Functions and contracts

Private invoker helpers, all with empty search_path and no application EXECUTE:

- `rosago_preview_json_keys(jsonb, text[])`: exact object key set.
- `rosago_preview_canonical_json(jsonb, integer)`: explicit canonical serializer.
- `rosago_preview_hash(text, jsonb)`: domain-prefixed UTF8 SHA-256.
- `rosago_validate_itinerary_preview(jsonb, jsonb, uuid, bigint)`: schema,
  preferences, source version and deterministic plan invariants; returns the
  selected UUID array in its original order.

Authenticated entry points, owned by postgres, SECURITY DEFINER, empty
search_path, with all relation/function references qualified:

| RPC | Parameters | Success result |
| --- | --- | --- |
| `rosago_itinerary_draft_store_preview` | `p_draft_id uuid`, `p_expected_revision bigint`, `p_candidate_preview jsonb` | one `(draft_id, state='preview_ready', revision=expected+1)` row |
| `rosago_itinerary_draft_return_to_editing` | `p_draft_id uuid`, `p_expected_revision bigint` | one `(draft_id, state='editing', revision=expected+1)` row |

PUBLIC, anon, authenticated and service_role execution is revoked from all six
functions before granting only the two entry points to authenticated. There are
no table grants, RLS changes, public helper APIs, dynamic SQL, or Save writes.

## Transaction and validation

Both RPCs require a nonnull `auth.uid()`, valid UUID argument and positive
expected revision below bigint maximum. They reject non-READ-COMMITTED
transactions and acquire an owned draft `FOR UPDATE` lock. Missing and foreign
drafts yield the same fixed rejection. Ownership is explicitly repeated at the
mutation; RLS is not relied upon inside SECURITY DEFINER. Revision and schema
must match. Exceptions use fixed messages; the Python boundary sanitizes native
database/transport failures as well. No automatic retries are performed.

Store permits editing -> preview_ready and preview_ready -> preview_ready only.
Regeneration requires exact ordered equality with the stored selected IDs.
Return-to-edit accepts only preview_ready, clears preview and returns to editing.
Each successful operation increments revision exactly once. Other states reject.
Expiry is checked with `clock_timestamp` after the draft lock; store checks it
again in the final UPDATE after any Place lock waits. Expiry is never extended.
The existing metadata trigger updates updated_at using its established
transaction-time semantics; this phase does not replace it. Preferences and all
saved fields remain untouched. Existing non-saved CHECK constraints keep saved
fields NULL, including accepted_preview_digest.

Store validates current expanded preferences using migration 0006 and requires
the stored snapshot to already be canonical. Legacy preferences lacking the
extension must be updated while editing before a preview can be stored. The
eight builder-relevant constraints must equal those stored preferences exactly.

Preview/schema/source versions must be 1, personalized planning and
`preserve-order-equal-count-v1`; recommendation policy is `category-interest-v1`.
Source draft identity/revision bind the pre-write draft. Selected IDs are 1-100
unique lowercase canonical UUID strings. SourceVersion must equal an independently
computed `v1:` SHA-256 of `rosago:source:v1:` plus canonical source manifest bytes.
The source hash is content binding, never authorization.

Exact nested key checks or equality to constructed exact objects reject unknown
fields. Days are the requested 1-7 consecutive dates; flattened stops contain
every selected ID exactly once, in selection order, with global order 1..N,
source recommended and keep_place true. Only equal-count invariants are checked:
first N%D days have N//D+1 stops; the others N//D, including empty days. No plan
is generated or corrected. Unresolved codes follow the existing builder's exact
sequence; budget_feasibility appears only for a supplied budget (including zero).
The existing 262144-byte JSONB-text preview size limit is retained.

## Catalog locking and fingerprint

Selected Place rows are locked in canonical UUID order using `FOR SHARE`, the
least row-lock mode that conflicts with ordinary non-key UPDATE as well as key
UPDATE/DELETE. KEY SHARE would allow relevant name/address/status/category edits.
The locked row versions themselves supply validation and fingerprint facts;
locks remain held through transaction completion. Missing, unpublished, or
nonmatching-category Places reject the whole request. Every category must belong
to stored interests; there is no SQL scoring, ranking, replacement or filtering.
Name/address must also meet Python's Unicode trimming contract.

The ordered catalog records contain exactly id, category, status='published',
name, address and is_test_record. The boolean is the exact case-sensitive
`slug.startswith('rosago-test-v1-')` rule. Slug itself, description, images,
coordinates and timestamps are excluded. The fingerprint hashes
`rosago:catalog:v1:` plus the canonical UUID-sorted record array. All selected
rows must be present and the supplied fingerprint must match.

Deterministic locking avoids opposite selection-order deadlocks between these
RPCs. Arbitrary administrative multirow writers can still deadlock; PostgreSQL
must abort such a transaction and the wrapper does not retry it. Locks establish
consistency through persistence, not permanent catalog freshness after commit.

## Python boundary and verification limits

The normal reader keeps its projection and model. A separate preview reader
adds owner, schema version and a validated immutable preview model, checking
preview-ready revision linkage and stored constraints. Reads do not attest to
current catalog freshness. Both readers explicitly filter owner and use the
scoped authenticated client. Store and return-to-edit wrappers pass only their
minimal RPC arguments and expect the exact next revision and target state.
`_call` defaults to editing, preserving create/preference-update contracts.
The service invokes the existing pure preview parser for self-consistency; it
does not select Places or call a plan-generation entry point. The parser's
existing reference replay remains internal to the 6D-7A contract.

Offline tests cover immutable migration hashes, additive scope, privileges,
ownership/revision/state/expiry clauses, exact schemas/invariants, catalog locks,
frozen canonical/hash vectors, and mocked service success/error/no-retry paths.
They do not establish SQL runtime validity, actual ACLs/RLS, lock waits or
transaction isolation behavior; the separately reported runtime coverage is
recorded below. Remaining runtime coverage includes foreign-user rejection,
anon/missing-subject invocation, malformed direct RPC inputs, stale/overflow
revisions, unsupported transitions, expired drafts and expiry during lock waits,
concurrent regeneration/editing, and Place archival/edit/deletion races. The
positive lifecycle and privilege checks do not prove every RLS scenario, all
negative security cases, or concurrency behavior.

## Verified development runtime status

The operator reported successful application once, including embedded canonical
byte/hash assertions. Both RPCs were verified with the signatures above and
SECURITY DEFINER status. Intended privileges were checked: authenticated can
execute the lifecycle RPCs, anon/PUBLIC cannot, and internal preview helpers are
not executable by authenticated/anon/PUBLIC.

A dedicated development test user completed the real service/adapter flow:
editing revision 1 -> preferences update revision 2 -> preview_ready revision 3
-> editing revision 4. `PASS: STORE_AND_RELOAD` confirmed preview persistence and
exact reload equality; `PASS: RETURN_TO_EDIT_AND_RELOAD` confirmed preview clearing.
Preferences and original expiry were preserved through both lifecycle operations.

The disposable draft was subsequently deleted using its exact ID and owner,
editing state, revision 4, NULL preview and NULL saved fields; exactly one row
was deleted. The temporary `runtime_preview_check.py` harness was removed.

## Offline review results

- `python -m unittest discover -s tests -p 'test_itinerary*.py'`: 141 passed.
- `python -m unittest discover -s tests -p 'test_recommendation_engine.py'`: 13 passed.
- `python -m unittest discover -s tests -p '*migration.py'`: 64 passed (overlaps
  the itinerary suite; these counts must not be summed as unique tests).
- The focused preview suite passed 40 tests, including nine new static/vector
  tests and nine new mocked service tests.
- `git diff --check` passed. Existing Git warnings concern `.pytest_cache`
  permissions and automatic LF-to-CRLF conversion.

Final checkpoint preparation reconciles this documentation and reruns offline
tests only. It does not reapply the migration, access Supabase, rerun the removed
runtime harness, or commit/push. Live results above are operator-reported evidence.
