# Synthetic destination seed — verified

The owner executed the separately approved `evaluation/setup/synthetic_seed.sql`
in evaluation project `jfaufpfzfhysqkhcdsrs`. Read-only MCP postflight passes.
Do not rerun the seed.

The file's SHA-256 remains
`6a9cdc841255ddf3f258b1edffd09122add3fc47ae350aca11be6d3a4bdae71e`.
The MCP project URL matches the evaluation reference; inspection ran as
`supabase_read_only_user` with transaction read-only enabled.

Exactly two places exist. Every seeded field matches the reviewed fixture;
only server-generated created_at/updated_at fields are excluded from the payload
comparison. Both have NULL photo URLs and no real personal data.

| Destination | ID | Status | Environment |
| --- | --- | --- | --- |
| Evaluation Garden (Fictional) | e0000000-0000-4000-8000-000000000001 | published | Outdoor |
| Evaluation Draft (Fictional) | e0000000-0000-4000-8000-000000000002 | draft | Indoor |

All eight other application tables, Auth users, Storage buckets and Storage
objects still have zero rows. No related rows, accounts or Admin memberships
were created. All 15 schema migration versions and names are unchanged.

Tables/RLS/table grants, all 17 policies, all 23 function signatures/owners/
search paths/ACLs/body hashes and all seven trigger definitions match the
verified pre-seed schema snapshot exactly.

## Visibility and acceptance limit

Under the unchanged published-only policy, anonymous and ordinary authenticated
readers can see the Garden and cannot see the Draft. Under the additional Admin
SELECT policy, an authenticated caller with current Admin membership can see
both rows. Admin status still comes from the reviewed membership predicate;
client metadata is not authority.

This conclusion is based on the actual hosted rows and verified RLS/grant/function
definitions. No signed-in User/Admin session was exercised: no Auth accounts or
Admin memberships exist or were authorized. Live account-based visibility and
application acceptance remain a separate gate. The privileged read-only inspector
seeing both rows is not itself proof of ordinary-client visibility.

## Scope and next step

Only the owner performed the approved two-row insertion. The agent used only
evaluation-project read-only MCP calls and made no hosted writes. The production
project was not accessed or targeted; no production verification query was issued.
No Auth/SMTP/Storage settings, session secrets/infrastructure, deployment, Git
commit/push or Google Forms feature was introduced. Linux build evidence remains
byte-for-byte unchanged.

Evidence: `synthetic-seed-postflight-evidence.json` and
`synthetic-seed-approval-status.json`.

The next approval is synthetic account provisioning using operator-controlled
test inboxes and private unique credentials. An intended synthetic Admin's
membership grant needs explicit approval as well. No such action was taken.

Deployment remains NO-GO pending qualified production shared-session wiring,
independent protected recovery authority, provider revocation/issuer acceptance,
production worker/restart/failure acceptance, hosted Auth and Storage configuration,
shared abuse controls, managed proxy/cookie behavior and real-device User/Admin
acceptance. The known seven intended security-definer advisor findings remain
documented in the schema-only postflight report; seed success does not close
these runtime gates.
