# Evaluation schema-only setup — verified

The owner applied the 15 approved migrations to `jfaufpfzfhysqkhcdsrs` using
`npx supabase db push --remote` from the isolated schema-operator directory.
Read-only hosted postflight **passes**, with seven expected security-advisor
findings described below. No further schema application or retry is needed.

## Verified through evaluation MCP only

Project URL matches `https://jfaufpfzfhysqkhcdsrs.supabase.co`.
Inspection runs as `supabase_read_only_user` with transaction read-only `on`.
The protected production project was not accessed by the verifier.

All 15 migration versions (`20261107000101` through `20261107000115`) and names
match the operator manifest exactly, including the photo contract before 0014.

Captured hosted metadata was compared against a fresh reconstruction of the
reviewed, hash-verified SQL in an owned disposable loopback-only PostgreSQL
container. No local seed or accounts were inserted. No hosted mutation was used
for verification. All compared sections match exactly:

| Section | Entries | Result |
| --- | --- | --- |
| Tables and table grants | 9 | Match; postgres owner, RLS enabled on every table |
| Columns, defaults, nullability and column grants | 79 | Match |
| Constraints and definitions | 68 | Match; all validated |
| Indexes and definitions | 17 | Match; all valid and ready |
| RLS policies and expressions | 17 | Match |
| Functions, signatures, owners, search paths, ACLs and body hashes | 23 | Match |
| Application/Auth-profile triggers and definitions | 7 | Match |
| Application/Auth/Storage row counts | 12 | All zero |

Authenticated callers retain only the reviewed table/column privileges and
checked RPC grants. No anonymous function execution, service-role function
execution or authenticated execution of the private destination mutator is
present. The final destination inner-mutator and audit-wrapper hashes match the
approved postflight guards. Ownership policies and published/Admin destination
visibility policies match the reviewed definitions.

The nine application tables are empty, as are Auth users and Storage buckets and
objects. No seed, accounts, Admin membership or upload was created. Checking
catalog definitions and empty counts does not establish live multi-account RLS,
hosted Auth or Storage functional acceptance.

## Security advisor findings

The advisor reports seven warnings in one category:
`authenticated_security_definer_function_executable`. They correspond exactly to
the two reviewed Admin entrypoints and five itinerary lifecycle entrypoints.
These functions intentionally run as their trusted owner while enforcing caller
membership or ownership inside the function. Their hosted bodies, grants and
pinned empty search paths match the approved SQL. Private helpers remain
inaccessible to ordinary callers.

These are expected review findings, not an unexpected schema deviation or an
empty advisor result. No grants were automatically revoked and no function was
rewritten. Review the provider's [security-definer advisory guidance](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable).
Real account-based positive/negative acceptance remains pending separately
approved synthetic accounts and test scope.

## Evidence and next action

- `schema-only-approval-status.json`: application and verification status.
- `hosted-schema-postflight-catalog.json`: captured metadata only, no credentials.
- `hosted-schema-migrations-and-advisors.json`: migration and advisor evidence.
- `hosted-schema-catalog-comparison.json`: exact section comparison results.
- `tools/verify_evaluation_postflight.py`: local reconstruction/comparison.

The owned reconstruction container and volumes were removed. The existing
successful Linux build evidence is byte-for-byte unchanged. Production startup
refusal remains intact. No Auth/SMTP/redirect settings, Storage configuration,
session infrastructure or secrets, hosting, deployment, Git commits or Git pushes
were performed by this verification.

The next data setup approval is **synthetic seed insertion only** for the two
fictional destinations in `evaluation/setup/synthetic_seed.sql`. It has not been
approved or run. Synthetic accounts and the intended Admin membership require
separate subsequent approvals.

Deployment remains **NO-GO**: qualified production shared-session wiring,
independent protected recovery authority, real provider revocation and issuer
acceptance, production worker/restart/failure behavior, hosted Auth and Storage
configuration, shared abuse enforcement, managed proxy/cookies and real-device
User/Admin acceptance remain open. A verified empty schema and successful Linux
build do not close those gates.
