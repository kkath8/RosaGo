> Completed: the owner executed the approved seed and evaluation-only read-only postflight passed. Exactly the two fictional destinations exist; other application/Auth/Storage counts remain zero. Do not execute the seed again. See [seed postflight](../../docs/production-readiness/remote-evaluation/synthetic-seed-postflight.md). The procedure below records the completed operation.

# Approved two-destination seed — owner-operated procedure

Approval covers only `evaluation/setup/synthetic_seed.sql`, only in evaluation
project `jfaufpfzfhysqkhcdsrs`. The evaluation MCP remains read-only. No seed has
yet been executed. Do not add a migration or rerun the schema batch for this DML.

Verified SHA-256:

`6a9cdc841255ddf3f258b1edffd09122add3fc47ae350aca11be6d3a4bdae71e`

The exact reviewed file inserts only two public.places rows:

| ID suffix | Slug | Status | Environment |
| --- | --- | --- | --- |
| 000001 | evaluation-garden | published | Outdoor |
| 000002 | evaluation-draft | draft | Indoor |

Both have explicit fictional names/descriptions and NULL image URLs. No related
records are necessary or inserted. The transaction locks places, refuses a
nonempty table, inserts the fixed two-row JSON payload, and commits. No INSERT
trigger exists on places; its only custom trigger updates timestamps on UPDATE.

## Preflight confirmed through evaluation-only read-only MCP

- Exact project URL matches the approved reference; inspection role is
  supabase_read_only_user and transaction read-only is on.
- All nine application tables, Auth users, Storage buckets/objects are empty.
- places RLS is enabled; anon/authenticated SELECT and the reviewed published-only
  and Admin SELECT policies remain intact. The Admin predicate body hash matches.
- Local seed bytes match both the approved hash and an exact reconstruction of
  the reviewed statement structure and two-place JSON fixture. No extra records
  or statements were found.

## Execute once using the owner's SQL Editor

From the existing isolated `evaluation/schema-operator` PowerShell directory:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $target = (Get-Content -LiteralPath '.\supabase\.temp\project-ref' -Raw).Trim()
    if ($target -ne 'jfaufpfzfhysqkhcdsrs') {
        throw 'STOP: Linked evaluation project mismatch.'
    }
    $seedPath = '..\setup\synthetic_seed.sql'
    $hash = (Get-FileHash -LiteralPath $seedPath -Algorithm SHA256).Hash
    if ($hash -ne '6a9cdc841255ddf3f258b1edffd09122add3fc47ae350aca11be6d3a4bdae71e') {
        throw 'STOP: Seed hash differs from the reviewed approval.'
    }
    Get-Content -LiteralPath $seedPath -Raw | Set-Clipboard
    Write-Output "PASS: Target $target; approved seed copied to clipboard."
}
```

This local block copies only the verified seed to the clipboard; it does not
connect to or change a hosted database.

Open https://supabase.com/dashboard/project/jfaufpfzfhysqkhcdsrs and select SQL
Editor, a new blank query, and the trusted postgres execution role. Check the
browser URL still contains exactly this project reference. Paste the clipboard
without editing the SQL. Confirm the single INSERT target is public.places and
the payload has exactly the two rows above. Execute the full transaction once.
Do not run it in any other open project tab. If the role is read-only, do not
change the MCP or its role: stop and report the operator-side issue.

Stop on any error, target/hash/content difference, unexpected affected records
or destructive warning. Do not retry on an uncertain result or remove the empty
table guard. Return the success message or sanitized error to the chat. No
additional SQL, account, grant, configuration or schema change is authorized.

## Postflight pending owner execution

The agent will use evaluation MCP SELECTs to compare all seeded fields to the
fixed fixture (excluding server-generated created_at/updated_at), confirm exactly
two places and no changes to other application/Auth/Storage counts, and recheck
policies/grants, triggers and the 15-entry schema migration history.

Policy-derived visibility is one published Garden for ordinary/anonymous access,
and both rows for a caller with current Admin membership. No accounts or Admin
memberships are authorized or present, so real signed-in User/Admin acceptance
cannot be claimed. Read-only metadata checks and local fixture behavior are
distinct from live sign-in tests.

Production is excluded from all operations; the agent will not query it merely
to prove that it was untouched. Successful Linux build evidence and production
session refusal remain preserved. Deployment remains NO-GO pending production
shared sessions, protected recovery authority, provider revocation, hosted
configuration, shared abuse controls, proxy/cookie and real-device acceptance.
