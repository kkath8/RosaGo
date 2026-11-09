# Isolated application backend setup — schema applied and verified

The owner applied the approved 15-file schema to `jfaufpfzfhysqkhcdsrs` through
the isolated CLI procedure. Hosted read-only postflight passes; see
[schema-only postflight](../../docs/production-readiness/remote-evaluation/schema-only-postflight.md).
The MCP remains read-only. Do not replay the schema files. The separately approved two-destination seed is also applied and verified; see
[seed postflight](../../docs/production-readiness/remote-evaluation/synthetic-seed-postflight.md).
Accounts and other hosted changes remain unapproved. Historical preparation-time authorization
fields in the frozen setup manifest remain unchanged.

Target: `jfaufpfzfhysqkhcdsrs`. Protected existing project: `brnkigrrqdrywahvcbvc`.
This directory contains application schema and fictional destination data only.
It has no questionnaires, production records, accounts, passwords, tokens, photos,
or session keys. The 15 schema files and the separately approved synthetic_seed.sql have been
applied only to the evaluation project. No accounts or memberships were created.

## Verified locally

Authenticated read-only verification on 2026-11-07 confirmed that
`supabase-evaluation` targets `https://jfaufpfzfhysqkhcdsrs.supabase.co`.
The inspected public schema has no relations or functions; application migration
history, Auth users, Storage buckets/objects and public/Auth/Storage policies are
empty. Security advisories are empty. This is readiness for **schema-only setup
approval**, not authorization to execute or readiness to deploy.

The connection runs as `supabase_read_only_user` and exposes no Auth management
settings endpoint or migration application tool. Site URL, redirects, signup,
confirmation, password/session limits, providers, SMTP and abuse controls remain
unverified. Empty `auth.instances` is not proof of any service setting. Bucket
metadata is verified empty; global Storage service limits are not exposed.
See [continued verification](../../docs/production-readiness/remote-evaluation/continued-verification.md)
for the approval matrix, evidence and remaining blockers.

`tools/prepare_evaluation_setup.py` prepares ordered copies of migrations
0001–0014, inserting the reviewed photo contract after 0013 and before 0014.
Only the two project-specific photo URL checks and their dependent function
hashes change. Original migrations and production photo SQL remain unchanged.
The exact preflight/postflight checks remain enabled; do not remove them.
`manifest.json` records the order and source/prepared hashes. Inspect the generated
diff before any hosted approval. Never run these files through application startup.

`tools/check_evaluation_schema.py` successfully rehearsed this order and the seed
in disposable PostgreSQL with minimal local Auth stubs. It checked nine RLS-enabled
application tables, published-only ordinary access, Admin visibility, and profile
creation. This does not qualify hosted Supabase Auth, Storage, or all RPC behavior.

## Required approvals and operator actions

1. Make the authenticated read-only `supabase-evaluation` tools available to the
   current agent session. Independently verify `get_project_url` equals the target
   before reading its tables, policies, functions, grants, migration history, Auth
   configuration and bucket metadata. Stop on mismatch or pre-existing objects;
   these migrations are one-time scripts. An empty migration history alone is
   not proof of an empty schema.
2. Review the prepared SQL, then separately approve schema application **only to
   the evaluation project**. Apply in `manifest.json` order, verify each
   transaction, stop on any failure. Do not copy the existing database dump.
   Apply `synthetic_seed.sql` last only after separate seed approval. It refuses
   to merge with nonempty `places`. Do not use the real-place import/publish scripts.
3. Separately approve synthetic account provisioning. Use unique, privately
   generated credentials and operator-controlled test inboxes. Never copy users,
   Auth rows, profile/trip/audit records, JWT secrets, or identity/password exports.
   Profiles are created by the reviewed Auth trigger. Grant only the intended
   synthetic Admin UUID membership through trusted owner authority; no self-grant,
   client metadata role, or direct destination write grants.
4. Choose the final Render HTTPS hostname. Set its exact Site URL and allow only
   required callback URLs `/auth/callback` and `/auth/reset-callback` when the
   respective flows are enabled. No broad wildcard or production callback.
   These settings require separate approval. Live signup/verification/recovery
   additionally requires approved mail delivery using owner-controlled inboxes,
   email confirmation, shared pending/replay/rate state, and focused acceptance;
   the current diagnostic profile disables email and is not the complete website.
5. Review new-project Auth signup policy, password rules, provider/session limits,
   abuse protections and SMTP. Synthetic pre-created accounts must not imply
   unrestricted signup is safe. Do not send real respondent mail under this plan.
6. Review destination-photo setup separately: a new `destination-images` bucket,
   JPEG/PNG/WebP only, 5 MiB maximum, application decode/pixel checks, generated
   `destinations/<32 lowercase hex>.(jpg|png|webp)` object paths, and approved
   non-sensitive test images. Existing code uses a server-only new-project
   `sb_secret_...` Storage key; it bypasses RLS, so never expose it to clients,
   logs or chat. No ordinary direct upload/update/delete grants. Public bucket
   reads expose all bytes in that bucket, including photos of Draft records:
   use only synthetic/public-safe bytes or separately implement private delivery.
   The current diagnostic guard forbids Storage secrets and photo mutations;
   completing that integration and reviewing its boundary is still required.
7. Preserve row ownership for profiles/trips/itineraries, Admin-only membership
   visibility, published-only ordinary destination reads, Admin destination/audit
   reads, and checked mutation RPCs. Keep internal mutators unavailable to clients;
   no service-role database access from application routes. Inspect hosted grants,
   function owners/search paths, RLS and security advisories after approved setup.
8. Supply only evaluation-project URL/public key privately in a **new** Render
   service with no production environment groups. Use separate Flask/session
   encryption secrets and a reviewed shared session/revocation/recovery backend.
   Do not set development/redis-local mode to bypass the production refusal.
   Deployment and hosted configuration remain separately approval-gated.

Supabase configuration references: [redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls),
[Storage access control](https://supabase.com/docs/guides/storage/security/access-control).

## Release gates still open

The Linux candidate builds and passes an offline non-root/import/startup-refusal
check. This is not a deployed service. Shared persistence/recovery checks use a
local test controller and synthetic provider responses. Real protected recovery
authority, production adapter wiring, actual cross-process/restart/revocation
acceptance, hosted project/issuer isolation, shared integration abuse limits,
proxy/header behavior and real-device User/Admin acceptance remain unqualified.
The diagnostic feature restrictions must be replaced with reviewed working
integrations before calling this the complete respondent website.

Latest local qualification also applies all 15 files and the seed under the
observed broad Supabase-style default grants, verifies explicit privilege
revocation, and checks shared session reads/revocation across separate Python
processes and a clean disposable-database restart. These component checks pass
using test recovery controllers; actual production Flask worker/restart and
independent protected-authority acceptance remain open. The generator writes
the seed with LF line endings so its byte hash matches the manifest on Windows.
