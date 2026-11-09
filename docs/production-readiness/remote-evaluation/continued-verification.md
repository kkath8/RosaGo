# Continued verification — 2026-11-07

The evaluation project is ready for separate **schema-only setup approval**.
Authenticated deployment and respondent access remain **NO-GO**. Nothing in this
report authorizes hosted changes. Only `mcp__supabase_evaluation__...` tools were
used for hosted access; the protected project was not queried.

## Authenticated hosted evidence

`get_project_url` returned `https://jfaufpfzfhysqkhcdsrs.supabase.co`, matching the
requested reference before schema inspection. SQL ran as
`supabase_read_only_user`. The tool namespace contains read-only inspection tools,
including SQL, tables, migrations, URL, advisors and Edge Function listings;
it has no Auth configuration reader or migration application tool.

| Area | Verified result | Limit |
| --- | --- | --- |
| Application schema | No public relations or functions; no custom application schema found | Recheck immediately before any later application |
| Migration history | Empty | Independently checked schema emptiness; history alone was not used |
| Policies | No public/Auth/Storage policies | Application policies have not been installed |
| Default grants | Broad future-table/function grants to anon/authenticated/service_role for postgres and supabase_admin | Scripts must run under reviewed owner authority and explicitly revoke defaults |
| Auth metadata | Zero users, zero instances, no custom auth.users trigger | Does not establish service configuration or provider behavior |
| Managed Auth tables without RLS | Eleven managed tables; no anon/authenticated SELECT or write table privileges | These managed tables are not application RLS defects; schema USAGE alone grants no row access |
| Storage | Zero buckets and objects; buckets/objects tables have RLS; no policies | No photo bucket is configured; service-wide Storage settings are not available through this connection |
| Edge Functions | None | No deployed application integration inferred |
| Security advisor | Empty lint list | No application objects yet; not a deployment security certification |

Auth Site URL, callback allowlist, signup/confirmation policy, password rules,
session limits, providers, SMTP, CAPTCHA and provider rate limits **cannot be
verified through these tools**. No credential-bearing HTTP/CLI fallback or
other project's MCP was used. No raw Auth configuration/secrets were requested.
An authorized operator must provide a redacted settings review or an appropriate
read-only settings capability before Auth readiness can be claimed.

## Prepared SQL review

Reviewed README and all 15 manifest entries, with the independent seed kept
separate. Source and prepared SHA-256 hashes match; exact source comparisons
allow only the preparation header, two photo-host substitutions and their
dependent function checksums. Original migrations and production photo SQL
remain unchanged. The photo contract follows 0013 and precedes 0014.

| Files | Reviewed responsibility |
| --- | --- |
| 0001–0003 | Own-profile access/trigger, published destinations, owned trips/memberships and checked trip RPCs |
| 0004–0007 | Owned itinerary tables; private validators; authenticated ownership/revision/expiry checks; preview/catalog validation |
| 0008–0009 | Own Admin membership visibility, invoker predicate and Admin destination reads |
| 0010–0011 | Checked preview adjustment and additive Tourism metadata |
| 0012–0013 | Membership-checked destination/overview RPCs; inaccessible inner mutator; transactional audit wrapper |
| 0013b, 0014 | Evaluation-only photo URLs; exact baseline/postflight guards; nullable environment contract |

All 15 transactions plus the fictional two-place seed pass in disposable PG17
with minimal Auth stubs and the broad postgres default privileges observed
hosted. Checks confirm nine RLS tables, pinned function search paths, no PUBLIC
function execution, no direct client place/membership mutation privileges,
no client execution of the internal mutator, own-profile/membership visibility,
published-only ordinary reads and Admin destination visibility. This is not
exhaustive RPC/concurrency acceptance or hosted Supabase Auth/Storage acceptance.

The seed had CRLF bytes on Windows while its manifest hashed LF text. The
generator now writes LF explicitly; regenerated seed bytes match the existing
manifest hash. No SQL semantics or ordered schema-file hashes changed.

The target annotations in SQL are comments, not a project-identity interlock.
Later execution must independently recheck the exact target, emptiness and
manifest hashes. Do not rely on a comment to prevent wrong-project application.

## Exact hosted approval boundaries

Read-only inspection and local rehearsal are authorized now. Every mutation below
requires separate explicit approval; none was performed. Current read-only MCP
credentials cannot perform schema setup even if approval is later granted.

| Operation requiring approval | Concrete scope / prerequisites |
| --- | --- |
| Schema application | Only target jfaufpfzfhysqkhcdsrs; the exact 15 manifest files in order; trusted postgres operator; each transaction and postflight checked; stop on failure/existing objects. Includes tables, functions, trigger, RLS, grants and the profile backfill statement, currently affecting zero existing users. No seed, accounts or Storage resources included. Use a separately approved write-capable operator/connection. |
| Synthetic seed | Separate synthetic_seed.sql approval after schema verification; two fictional places, no photos; refuse nonempty places. |
| Accounts | Provision only specifically approved synthetic identities using operator-owned inboxes and private unique credentials; do not copy Auth records. Profile creation is a trigger side effect. |
| Admin membership | Explicit owner-authorized grant to the intended synthetic Admin UUID; approve separately from ordinary account creation or include it explicitly in that account approval. |
| Auth settings / email | Exact final HTTPS Site URL and required callbacks; signup/providers, confirmation, password/session rules, abuse controls and SMTP changes; approve live signup/verification/recovery tests and mail recipients before sending anything. |
| Storage | Create/configure destination-images only after bucket/privacy decision; approved JPEG/PNG/WebP, 5 MiB cap, ordinary write denial, server-secret boundary and application decode/path checks; separately approve synthetic uploads/deletes. Public bytes also expose Draft photos, so use only public-safe bytes or implement reviewed private delivery. |
| Session infrastructure / credentials | Provision/configure a reviewed shared store and independent recovery authority; separate key generation/rotation, access rules, recovery/restore procedures and any hosted failure/revocation exercises. App routes must not gain service-role database access. |
| Hosting configuration / deployment | New isolated Render service, final hostname, evaluation-only environment and fresh secrets; no production groups; approve configuration and deployment explicitly after engineering gates pass. |
| Live acceptance / opening access | Explicit bounded synthetic mutations, provider sessions/logout/recovery, mail/photo tests and failure/restart exercises; only then separately authorize respondent admission. |
| Cleanup / revocation | Approved account/session revocation, data/object deletion, key rotation or service shutdown; never restore an old session snapshot as cleanup. |

No commit or push was made or authorized. No Google Forms, survey/evaluation
features, new application routes or frontend changes were added.

## Local session qualification

- **39 focused tests and 69 subtests pass:** isolation, revocation conflicts,
  shared abuse-state behavior, protected-authority protocol denial, readiness and
  production-entrypoint refusal. An initial sandbox run could not open temporary
  LMDB fixtures; the same tests passed with permitted local fixture access.
- **6 real local PostgreSQL store checks pass:** encryption/expiry, terminal
  revocation, concurrent refresh/revoke, runtime privilege restrictions, uncertain
  commit behavior and independent family/shared-rate expiry.
- **6 local Flask/PostgreSQL checks pass:** two application instances with
  synthetic providers, realm independence/CSRF/actor checks, shared recovery and
  verification state, authority outage and invalid recovery proof denial.
- **New independent-process checks pass:** child Python processes can resolve
  both realm records; child revocation is visible to the original process; a fresh
  process still denies the revoked User and preserves Admin. A clean restart of
  the owned database container preserves those outcomes. All generated lab
  containers/volumes were removed. No application listener was exposed.

Reproduce the new checks with `.venv/Scripts/python.exe tools/qualify_evaluation_readiness.py`.
It uses cached postgres:17, only a random loopback port, generated throwaway
credentials and stdin for child inputs. Sanitized outcomes are in
`continued-local-qualification.json`. Existing store/application outcomes are in
`real-local-pg-results.json` and `real-local-pg-application-results.json`.

**Evidence boundary:** separate processes exercise PgModel/PgRealm directly;
Flask integration still uses two in-process instances with injected adapters.
Each process uses a test recovery controller with supplied synthetic bindings.
The test does not establish a shared protected control plane, actual production
Flask worker handoff/restart, rollback/failover safety, provider revocation or
clean recovery from uncertain infrastructure state.

## Security blockers remaining

1. `init_session_realms(mode='production')` still refuses unconditionally.
   Production/evaluation WSGI has no qualified shared-session factory. The PG
   adapter is loopback-only and injected into local Flask tests; the Redis factory
   requires a ProtectedRevisionAuthority that application startup does not supply.
   Keep these refusal guards intact.
2. ProtectedRevisionAuthority and RecoveryFence are contracts, not deployed
   services. Authenticated bounded transports, independently durable authority,
   restore/promotion fencing, non-reused epochs, worker draining and independently
   supplied current bindings need implementation and qualification. Nonce checks
   and clean restarts do not prove resistance to full-state rollback.
3. Provider-current-session validation and sign-out remain unqualified. Fresh
   local records can pass the coordinator without a fresh provider-session lookup;
   local revocation evidence must not be presented as invalidation of provider
   access/refresh tokens. Qualify revoked/expired provider sessions and bounded
   failures against the evaluation project's actual issuer after approved accounts.
4. Shared application limiter component checks pass, but direct provider abuse,
   signup settings, global/account quotas and multiworker integration limits still
   need review and acceptance. No hosted Auth configuration was verified.
5. Actual hosted RLS/grants/RPC/profile-trigger/Storage acceptance follows approved
   setup. Independent project URL identity is confirmed; real signing-key/issuer
   isolation and live client behavior are not yet qualified.
6. Final hostname, actual managed proxy/header behavior, Secure cookie issuance
   and deletion, full application worker/restart/outage operation and real-device
   User/Admin acceptance remain open. The current diagnostic email/photo-disabled
   configuration is not the complete User/Admin website.

## Preserved Linux evidence

`linux-build-results.json` remains unchanged: Python 3.13.18 candidate build,
pip check, compilation, offline imports, non-root execution, sensitive-context
exclusions and expected production startup refusal passed. No ports were
published and nothing was deployed. This supersedes the older failed-build
entries in historical reports. No application-image rebuild was needed for the
verification tools/docs and seed line-ending correction, which are excluded
from its build context. Successful build evidence does not qualify the missing
production runtime adapter or approve deployment.
