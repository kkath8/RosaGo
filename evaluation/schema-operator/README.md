# Approved schema-only setup — operator handoff

The owner has applied and verified the 15 approved schema migrations for
`jfaufpfzfhysqkhcdsrs`. Do not replay them. See the
[postflight report](../../docs/production-readiness/remote-evaluation/schema-only-postflight.md).
The existing `supabase-evaluation` MCP remains read-only. Its SQL role
is `supabase_read_only_user`, with default and current transaction read-only
settings both `on`; it exposes no apply-migration tool. Owner-operated CLI performed
the approved schema writes; the verifier performed only read-only hosted access.

This directory stages exactly 15 byte-identical copies of the reviewed schema
files with CLI-compatible ordered timestamp filenames. `manifest.json` maps
each timestamp and SHA-256 back to its reviewed file. No seed is staged. The
original reviewed manifest remains unchanged as the approval baseline; its older
`hosted_execution_authorized: false` records its preparation-time status.

## Operator steps — explained before any write

Use a separately authenticated Supabase CLI operated by the project owner.
Leave the existing MCP configuration, permissions and role unchanged. These
commands are instructions only: Codex has not run them, logged into the CLI,
linked a project, retrieved credentials, or connected a write-capable mechanism.
The user must choose/provide this operator mechanism before agent execution can
continue. Existing schema approval does not need to be requested again.

1. Open the [evaluation project dashboard](https://supabase.com/dashboard/project/jfaufpfzfhysqkhcdsrs).
   Confirm the address contains exactly `jfaufpfzfhysqkhcdsrs`. Recheck through
   the read-only evaluation MCP that URL identity matches, public relations and
   functions and migration history are empty, Auth users are zero, and Storage
   buckets/objects are zero. Stop on any difference; do not merge/replay/reset.
2. From the RosaGo workspace, verify every staged file's raw-byte hash against
   this directory's manifest and `evaluation/setup/manifest.json`. The list must
   contain exactly the following 15 files, with no additional migration or seed.
3. Open a terminal **inside `evaluation/schema-operator`**, not the application's
   existing migration directory or any previously linked CLI workspace. With the
   official CLI already installed, initialize local CLI metadata and authenticate:

   ```powershell
   Set-Location -LiteralPath 'evaluation/schema-operator'
   supabase init
   supabase login
   supabase link --project-ref jfaufpfzfhysqkhcdsrs
   ```

   The Set-Location command assumes the terminal starts at the RosaGo root.
   Enter owner-controlled credentials privately at the CLI's prompts. Do not
   paste access tokens/database passwords into chat or a script. If init would
   overwrite existing config, or linking reports another project, stop. Do not
   reuse production linking/configuration. Local generated config is not approval
   to push Auth/Storage configuration.
4. Inspect the plan without applying schema:

   ```powershell
   supabase migration list
   supabase db push --dry-run
   ```

   Confirm no remote migrations and exactly versions `20261107000101` through
   `20261107000115` in the order below. Stop if any other files, seed, destructive
   DDL, unexpected remote history or reconciliation/repair is proposed. Do not
   use `--include-seed`, reset, repair, db pull, configuration push, or bulk imports.
   Recheck staged hashes after initialization and immediately before application.
5. After the target, hashes and plan match, the operator can use the existing
   schema-only approval to execute:

   ```powershell
   supabase db push
   ```

   This is a database migration command, not a Git push. It applies the staged
   schema files and records migration tracking metadata. Stop on the first error
   or warning about unexpected/destructive changes. Record the last confirmed
   committed version and sanitized SQLSTATE; do not rerun the batch, remove a
   guard, edit approved SQL, repair history or reset anything to force success.
   Earlier committed files may remain if a later file fails. A lost/uncertain
   result requires read-only reconciliation before further execution.
6. Recheck via the unchanged evaluation MCP, including `list_migrations`,
   `list_tables(public, verbose=true)`, security advisors and the queries in
   `evaluation/verification/schema_postflight_readonly.sql`. Execute its SELECTs
   separately when needed so an MCP returning only the final statement does not
   hide earlier results. Return only sanitized metadata, not credentials.

## Exact application order

| Version suffix | Reviewed file |
| --- | --- |
| 01 | 0001_profiles.sql |
| 02 | 0002_places.sql |
| 03 | 0003_trips.sql |
| 04 | 0004_itinerary_foundation.sql |
| 05 | 0005_itinerary_draft_lifecycle.sql |
| 06 | 0006_itinerary_preference_extension.sql |
| 07 | 0007_itinerary_preview_lifecycle.sql |
| 08 | 0008_admin_authorization.sql |
| 09 | 0009_admin_places_read.sql |
| 10 | 0010_itinerary_preview_adjustment.sql |
| 11 | 0011_places_tourism_metadata.sql |
| 12 | 0012_admin_management.sql |
| 13 | 0013_admin_destination_audit.sql |
| 14 | 0013b_destination_photo_contract.sql |
| 15 | 0014_destination_environment.sql |

All version suffixes use prefix `202611070001`. Migration names preserve the
reviewed filename stem after the timestamp; file contents are unchanged. The
scripts contain their reviewed transaction boundaries, REVOKEs, function
replacements/rename and data-mutation RPC definitions. These are intended schema
operations. The 0001 profile backfill statement must affect zero rows because
Auth is empty. No top-level DROP/TRUNCATE statement was found in the approved
files. Defining a mutation RPC does not execute it.

## Postflight acceptance — not yet performed

- Nine public application tables: profiles, places, trips, trip_places,
  itinerary_drafts, trip_itinerary, trip_stop_plans, admin_memberships,
  admin_destination_audit. All have RLS enabled and trusted owner.
- Compare column definitions, validated constraints, valid/ready indexes, table
  and column grants, policy expressions and function signatures against the
  reviewed files. Ordinary clients cannot write places or memberships, execute
  private helpers/inner mutators, or receive service-role database authority.
  Function search paths stay pinned; ordinary ownership/publication policies and
  the audited Admin wrapper stay intact.
- Inner mutator body MD5 `a45875ef215c9713bc4c7d32ef6601e1`; audit wrapper body MD5
  `4cab3fdc6baf75133fd19b8f1dde6345`, normalizing CR exactly as the approved guards.
- The Auth profile trigger exists with its reviewed definition. All nine public
  tables, Auth users and Storage buckets/objects remain empty. No live mutation
  RPC, account creation, seed or upload is part of postflight.
- Migration history must contain exactly the 15 staged versions in order, with
  matching names/statements where exposed. Missing history is not successful CLI
  tracking; reconcile read-only and stop rather than fabricate applied entries.
- Inspect security advisors and report any findings before further setup.

Direct SQL Editor application is not the proposed path because it bypasses
migration tracking. Supabase documents CLI migration tracking and this SQL Editor
limitation in its [database migrations guide](https://supabase.com/docs/guides/deployment/database-migrations).
No history-repair operation has been authorized or performed.

## Current state / next approvals

Owner-operated CLI application and evaluation-only read-only postflight have
completed successfully. All 15 versions/names and the full catalog match the
reviewed SQL; seven intended authenticated SECURITY DEFINER RPC advisor findings
remain documented. No database execution error or auto-review rejection occurred.

After schema postflight passes, the next data setup approval is the separate
two-fictional-place seed (`evaluation/setup/synthetic_seed.sql`). Account creation
and Admin membership grants are separate subsequent approvals. All user-excluded
Auth/mail/redirect, Storage, infrastructure/secrets, hosting/deployment and Git
operations remain excluded.

Deployment remains NO-GO: production shared-session wiring, protected recovery
authority, actual provider revocation, production worker/restart acceptance,
hosted Auth/Storage settings, shared abuse enforcement, managed proxy/cookie
behavior and real-device acceptance remain unresolved. The successful Linux
build evidence and production refusal guards are preserved.
