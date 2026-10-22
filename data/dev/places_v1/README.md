# RosaGO Development Places Dataset v1

DEVELOPMENT ONLY / NEVER PRODUCTION.

This dataset supports RosaGO's 70% development demonstration. All 12 POIs are
synthetic, not production data, and not real businesses or attractions. They are
not verified or endorsed by the Santa Rosa City Tourism Office. Official POI
data will be handled separately later.

## Environment designation, including Supabase Free

Supabase Free may expose only the main database branch, labeled "PRODUCTION"
by Supabase. For this RosaGO capstone, the entire project is currently used only
for development/testing. A branch label alone neither determines the project's
actual use nor authorizes these scripts.

Execution is allowed only after the operator explicitly designates the entire
project as a non-production RosaGO capstone development/testing environment.
Manually verify the connected project identity and its current use before each
operation. Never use either script in a project serving real production users/data.
If the project later becomes a real production deployment, these scripts must
no longer be executed there, including cleanup.sql.

Synthetic records must be removed before replacing them with verified/final
tourism data where appropriate, while the project is still designated for
development/testing. Resolve test membership references through separately
authorized actions first; do not bypass cleanup guards. If transition already
occurred, removal needs a separately reviewed production data-change procedure.

The required acknowledgement for either script is exactly the following single
line. It records operator intent, not automated environment verification:

```text
I verified the connected Supabase project. I designated this entire project for RosaGO capstone development/testing only; it is not serving real production users/data. I understand these are synthetic test records and the Supabase main/PRODUCTION branch label does not make this safe automatically. I intentionally authorize this development-only operation.
```

The scripts were prepared and tested statically offline; they have NOT been
executed or runtime-validated against PostgreSQL/Supabase by this checkpoint.
They are data scripts, not migrations. Never rerun `0002_places.sql` or
`0003_trips.sql`; both have already been applied to the development database.

## Dataset and permanent identities

UUIDs below all have prefix `9f56c6a0-5c4d-4e82-9b31-`; append the explicit
12-digit suffix shown. Both SQL files contain the full explicit UUIDs, not a
generated range. Slugs all have prefix `rosago-test-v1-`.

| UUID suffix | Slug suffix | Category | Status |
| --- | --- | --- | --- |
| 000000000001 | attraction-01 | attraction | published |
| 000000000002 | attraction-02 | attraction | published |
| 000000000003 | dining-01 | dining | published |
| 000000000004 | dining-02 | dining | published |
| 000000000005 | shopping-01 | shopping | published |
| 000000000006 | accommodation-01 | accommodation | published |
| 000000000007 | nature-01 | nature | published |
| 000000000008 | nature-02 | nature | published |
| 000000000009 | heritage-01 | heritage | published |
| 000000000010 | heritage-02 | heritage | published |
| 000000000011 | draft-attraction-01 | attraction | draft |
| 000000000012 | archived-heritage-01 | heritage | archived |

Expected seed visibility is 10 publicly visible rows covering all six categories,
plus 1 draft and 1 archived hidden row. Other pre-existing records are unaffected.
Every image URL is NULL. Names, descriptions, and addresses disclose test status;
the address disclosure also appears in map popups where descriptions do not.

Coordinates use a deterministic 3-by-4 grid around the approximate anchor
14.28, 121.09: latitude offsets -0.002/0/+0.002 and longitude offsets
-0.003/-0.001/+0.001/+0.003 degrees. They are illustrative map/UI positions only,
not researched locations, real POIs, visitor addresses, or verified city-boundary
points. Distinct markers allow testing map bounds and popups. Browser map tiles
still use the existing external OpenStreetMap service.

## Manual application procedure

1. Obtain authorization for execution separately from preparing these files.
2. Manually verify the Supabase project name, project reference, and
   connection/editor target. Confirm the entire project is explicitly designated
   for RosaGO capstone development/testing and serves no real production users/data.
   A database name, main/PRODUCTION branch label, or acknowledgement cannot prove
   the target project's identity or current use.
3. Use the trusted development `postgres` operator in the SQL Editor. Do not
   supply elevated credentials to Flask or a browser. Do not alter table grants,
   RLS, or application keys to enable this script.
4. Review all 12 records and the whole `seed.sql` transaction. Use READ COMMITTED.
   In an editor copy, replace only the empty `operator_acknowledgement` string
   with the exact acknowledgement line above. Keep repository defaults empty.
5. Execute the complete script as one transaction only after the above checks.
   Do not execute selected fragments. Lock timeout is 5 seconds; statement
   timeout is 30 seconds. Schedule a quiet development window because the
   transaction briefly serializes writes to `places` while allowing reads.
6. Inspect the result. On any error, ensure the transaction is rolled back before
   proceeding. Do not automatically retry an uncertain result; inspect first.
   Verify the expected visible/hidden counts through separately authorized checks.

No existing row is updated. Missing records are inserted with explicit columns;
timestamps come from database defaults. Existing exact records are unchanged,
including timestamps. Any reserved UUID **or slug** with unexpected content
aborts the entire transaction. Only created_at/updated_at are excluded from
content comparison. Partial exact installations are completed safely. A changed
name, status, coordinate, or other content field requires manual review rather
than silent repair. Even unexpected additional table columns cause a conservative
comparison failure. Do not relax these checks to force an execution through.

## Manual cleanup and reset

Repeat the same authorization and development-project verification. Review
`cleanup.sql`, set its acknowledgement in an editor copy, and execute the whole
transaction. Cleanup targets only the explicit UUID manifest, never names, slug
prefixes, or all test-looking data. Missing targets are harmless.

Every existing target must still match all expected content fields, excluding
timestamps. Cleanup refuses changed content and refuses any target referenced by
`trip_places`. It does not delete trips or memberships. The existing restrictive
foreign key remains the final safeguard if a reference is created concurrently;
such a failure rolls back cleanup. Separately review/remove authorized test
memberships before trying cleanup again. Never use cascade deletion to bypass it.

Reset means successful cleanup followed by separately deliberate seed execution.
An intentionally unpublished or otherwise edited fixture will fail the strict
content guard; review that change explicitly, rather than expecting automatic
reset. Neither script modifies schema or installs persistent functions/objects.

Initially hidden records verify public visibility filtering but cannot be added
to trips. To test retained "Place unavailable" membership later, a separately
authorized scenario must add a published test place through the existing RPC,
then unpublish it. This dataset does not create users, trips, memberships, or
destination-mutation routes.

## Offline checks and execution boundary

`tests/test_dev_places_seed.py` reads scripts as text and parses their embedded
JSON manifests. It validates the data using the existing Place parser and checks
SQL safety structure. It never submits SQL. Static checks do not establish SQL
runtime validity, locking behavior, or live RLS enforcement.

There is no automatic startup/test/deployment execution. These scripts must never
be imported by runtime code or wired into Flask startup, tests, or deployment.
No credentials are stored in this directory.
