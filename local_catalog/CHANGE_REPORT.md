# Historical archive and offline catalog — change report

Completed 8 November 2026. No hosted project was contacted. Remote deployment
remains **NO-GO**.

## Files moved with byte-for-byte integrity checks

| Original path under `data/santa_rosa_places/` | New path under that directory |
| --- | --- |
| `places.json` | `archive/places.json` |
| `publish.sql` | `archive/publish.sql` |
| `tourism_transition_plan.json` | `archive/tourism_transition_plan.json` |
| `tourism_transition_review.sql` | `archive/tourism_transition_review.sql` |
| `README.md` | `archive/README.original.md` |

All five SHA-256 hashes match their pre-move values. See
`data/santa_rosa_places/archive/manifest.json`. No historical contents or SQL were
deleted or altered. A new parent README distinguishes runtime metadata from the
archive, and an archive README clearly supersedes the old operational instructions.

`weather_metadata.json` was not moved or edited. Its SHA-256 remains
`cdab900f6c1c652f3800ae83347fd0cdf9848c8d5a39277cb67acfd1fd6be724`.
`destination_weather_metadata.py`, runtime clients, routes, database/RPC behavior,
Dockerfile and Docker allowlist are unchanged. Admin and User continue using the
same configured Supabase `public.places` table.

## New files

- `data/santa_rosa_places/README.md` — current runtime/archive guide replacing the
  old location; the old README is preserved as shown above.
- `data/santa_rosa_places/archive/README.md`
- `data/santa_rosa_places/archive/manifest.json`
- `local_catalog/README.md`
- `local_catalog/manifest.json`
- `local_catalog/.gitignore`
- `local_catalog/CHANGE_REPORT.md`
- `tools/local_destination_catalog.py`
- `tests/test_local_destination_catalog.py`

No `local_catalog/snapshot.json`, `catalog.json` or destination plan was created.
The catalog is deliberately awaiting separately authorized current data, rather
than using the original 28-place list or a historical backup.

## Updated references and tests

- `tests/test_santa_rosa_catalog.py`
- `tests/test_tourism_transition.py`
- `tests/test_tourism_weather_identity.py`
- `tests/test_weather_proposal.py`
- `docs/CHECKPOINT_4B_WEATHER_PROPOSALS.md`
- `docs/EXPLORE_TOURISM_TRANSITION_REVIEW.md`
- `docs/admin-finalization/AUDIT.md`
- `docs/admin-finalization/database-preflight/REPORT.md`
- `docs/admin-finalization/phase1b-environment-0014/PRODUCTION-CSV-REVIEW.md`
- `docs/admin-finalization/final-review/REPORT.md`

Historical reports retain their original findings, with artifact paths updated
or a relocation note added. The archived transition plan's protected hashes and
runtime weather path were preserved. The original catalog test now parses SQL
literal values as text instead of executing INSERTs in SQLite, so the focused
suite executes no SQL scripts.

## Offline catalog safeguards

The helper accepts only a current, evaluation-bound, destination-only snapshot
declared and independently verified to cover all publication statuses. It checks
counts, canonical row hashes, supported fields, freshness and record validity.
The metadata is an integrity contract, not cryptographic proof of authorization;
trusted owner/export evidence and a later live-state recheck remain necessary.

`init` creates a local editable copy from that full snapshot only; it refuses
overwrite. `plan` produces review-only JSON and has no apply/network/SQL/login
path. Matching existing UUIDs become updates with their original row version;
unknown UUIDs and UUID/slug/version drift stop planning. Duplicate IDs, slugs and
normalized names stop for manual review across baseline, omitted and staged rows.
New records are explicitly staged separately as Drafts with server-assigned
identities still required. Omitted rows are preserved and never automatically
deleted or archived. Existing publication and audit safeguards must be retained
in any separately approved future application.

## Verification

- **57 focused tests passed** across new planner/identity tests, archived catalog,
  Tourism transition, weather identity and weather proposal suites.
- **36 existing Admin/User catalog tests passed** across
  `test_admin_destinations.py`, `test_places_client.py`, `test_places_service.py`.
- **93 total focused offline tests passed.** Archive hashes and active weather
  loading passed; no published-only catalog was silently accepted as complete.
- CLI help verified. The missing-snapshot test confirms initialization stops
  without creating a catalog. Tests also verify overwrite refusal, malformed
  JSON rejection, stale/wrong-project snapshots, new-row collisions, matching-ID
  updates, and preservation of omitted records.
- Initial temporary-file tests hit a Windows sandbox ACL restriction. The same
  offline suite passed outside that restriction with network guards enabled.
  Only the two empty workspace test directories created by those failed runs
  were cleaned up; no historical/catalog data was deleted.
- Reference search and `git diff --check` passed for changed tracked files.
- Existing Linux build-result SHA-256 remains
  `b3645b00f1ebe1a724e96ccf8d0f9831ef98cb1e627d27d5249b7d73f10a470d`.

No hosted reads/writes, SQL execution, live sign-ins, deployment, commits or pushes
occurred. No runtime configuration changes or application restart are required.

The next authorization needed is a **destination-only, read-only, all-status
export from evaluation project `jfaufpfzfhysqkhcdsrs`**, with target/completeness
evidence. Any hosted application of a later reviewed plan requires separate approval.
