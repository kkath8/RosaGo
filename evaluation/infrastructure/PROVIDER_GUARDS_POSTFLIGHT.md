# Provider security SQL — hosted read-only postflight PASS

Evaluation project `jfaufpfzfhysqkhcdsrs`. The owner reported one successful
execution of the approved second script. The verifier used only SELECT queries
through `supabase-evaluation`, as `supabase_read_only_user` with read-only mode on.
Project URL matched. No hosted writes, sign-ins, deployments or production access.

Approved file SHA-256 remains
`4136cd079ad39201e3fb185c0de8410374a556cb38631f25ac51e81c19983307`.
The first file also retains its approved hash. Neither file was edited or rerun.

## Exact catalog verification

- New caller-bound helper has no arguments and returns boolean; PL/pgSQL,
  SECURITY DEFINER, postgres owner, empty search_path, not leakproof. Its complete
  body matches the approved SQL hash, including evaluation issuer, subject/session
  binding, role/audience, JWT expiry, session ownership and not_after checks.
- All seven complete replacement RPC definitions match the approved SQL, with
  Windows CRLF line endings normalized for comparison:
  five itinerary lifecycle entrypoints and two Admin entrypoints. All seven
  contain the reviewed session entry check. Existing signatures, owners, empty
  search paths and ACLs match the original catalog. Private helpers remain private.
- All nine new public policies match exactly: RESTRICTIVE ALL TO authenticated,
  with both USING and WITH CHECK invoking the caller-bound helper. All original
  17 public policies remain byte-for-byte equivalent in the captured definitions.
  Total public policies: 26.
- All 24 public function definitions/metadata match the original 23 plus the
  single helper and exactly seven approved body changes. Original function ACLs
  remain unchanged. New helper permits postgres/authenticated EXECUTE, with no
  anon/service_role/PUBLIC execution grant.
- Existing public table/column grants, ownership, columns, constraints, indexes
  and triggers match the original reviewed schema catalog. No extra public
  tables, columns, indexes or triggers were added.
- Private schema/table grants and forced RLS remain unchanged. Its sole policy
  is still for rosago_session_app only. API roles have no private access or
  ability to assume that role; it remains NOLOGIN and without elevated privileges.
- Session payload table is empty. No ciphertext or session credentials were read.

## Preserved data and migration baseline

- Two Auth identities, two profiles and exactly one Admin membership remain.
  Ordinary User 3c572202-c1da-4e5a-aa20-d89be25b2d9f retains a profile and no
  membership; Admin 4bc67593-c979-4441-b42a-99b6d3da2885 retains its profile and
  the sole membership. Auth credentials/private account attributes were not read.
- Exactly two destinations remain. Every approved seed payload field still
  matches the hash-verified fixture, including Published Garden and Draft place.
- Other application tables and Storage remain empty. No provider sessions exist.
- All 15 original migration versions/names, 20261107000101..20261107000115,
  match the operator manifest. SQL Editor did not add migration history entries.

## Evidence

Captured metadata only, no credentials:

- docs/production-readiness/remote-evaluation/hosted-provider-guards-postflight-catalog.json
- docs/production-readiness/remote-evaluation/hosted-provider-guards-additional-postflight.json
- docs/production-readiness/remote-evaluation/hosted-provider-guards-rpc-definitions.json
- docs/production-readiness/remote-evaluation/hosted-provider-guards-destination-postflight.json
- docs/production-readiness/remote-evaluation/provider-guards-postflight-comparison.json

Offline comparator: `tools/verify_provider_guards_postflight.py`.
All 23 catalog/data comparison checks pass. This confirms installation and scope;
it is not live provider/API functional acceptance. Do not rerun either SQL file.

## Remaining blockers — remote deployment NO-GO

1. **Auth restore/JWT replay remains unresolved.** Restored auth.sessions rows
   can make previously removed sessions appear current to these SQL checks while
   old JWTs remain unexpired. Restoring old public schema can remove the guards.
   These guards do not consult the external authority or detect restoration.
   Closing Render alone does not fence direct Supabase API access. Independent
   API quarantine, credential invalidation and verified reopening remain required.
2. Hosted provider logout/removal/not_after semantics, direct REST/RPC/GraphQL
   replay and other enabled API paths have not been exercised. The helper does
   not establish every ban/account/inactivity/password-AMR/recovery restriction.
3. Independent authority provisioning/control isolation and recovery operations,
   private SQL login/TLS/secret lifecycle and production runtime composition are
   not qualified. The session role is intentionally still NOLOGIN.
4. Actual Render proxy/TLS/cookies, two-worker resource/load/failure acceptance
   and subsequent controlled live tests remain separately gated. Production
   startup remains closed; no deployment or live-test authorization is inferred.
