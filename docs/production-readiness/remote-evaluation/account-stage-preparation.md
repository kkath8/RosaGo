# Synthetic account stage — prepared, not authorized

The evaluation-only read-only preflight confirms project jfaufpfzfhysqkhcdsrs,
zero Auth users, profiles and memberships, the installed profile trigger, and
the two approved Published/Draft fictional destinations. No hosted accounts,
membership grants, provider sign-ins or configuration changes were performed.

The concrete procedure is `evaluation/account-setup/README.md`. It proposes two
owner-controlled inbox aliases and privately generated unique passwords, manual
password account creation with individual confirmation, automatic profile creation
and a separately approved one-row Admin membership transaction. It uses no
service-role key in application code and stores no real credentials in the repo.
Exact grant SQL is prepared in `grant_admin_membership.review.sql`, outside all
schema migration runners. Only the intended synthetic Admin UUID receives a row;
ordinary test User membership stays absent. UUID-to-inbox matching is done privately
by the owner before granting.

`evaluation/account-setup/ACCEPTANCE.md` specifies login, visibility, authorization,
session isolation/expiry/logout, concurrency, outage and recovery tests with clear
local/hosted boundaries. `postflight_readonly.sql` returns only UUIDs, booleans and
counts, not passwords, emails, JWTs or Auth secrets. Live provider sign-in/logout
tests need separate approval and a qualified runtime; provisioning alone does
not authorize them or a startup-guard bypass.

## Local validation completed

- 79 focused offline login/coordinator/Admin boundary/realm/isolation/revocation
  tests and 54 subtests pass, including six new provider-check cases.
- 17 protected-authority, configuration and recovery-contract tests with 36
  subtests pass. These use local test providers, not independent infrastructure.
- 11 real disposable-PostgreSQL role checks pass, including anonymous/nonmember
  published visibility, Admin Draft visibility, own profile/membership, denied
  self-grants/direct writes/private helper execution, Admin overview access and
  denied nonmember overview. The exact guarded grant transaction was rehearsed
  only against local Auth stubs. The owned container and volumes were removed.
- All six new provider-check tests pass on Linux using read-only source/test
  overlays in the existing non-root image, network disabled and no published ports.
  This validates the changed hook against the prior image's dependencies.

## Session progress and open blockers

NormalAuthCoordinator now accepts an optional server-injected provider_session_check
boundary. Fresh records must pass it before a database client/context or activity
touch is issued. Near-expiry records are checked before refresh reservation or
rotation, and the resulting record is checked again at admission. True admits,
False denies, and unknown/malformed/exception outcomes fail transiently closed
without automatic retry/cache or raw exception leakage. The checker gets the
server-only record, configured issuer and realm; it must bind actual provider
proof to that exact user and session. Missing hooks retain existing local behavior.

No production/local application factory activates a real checker. This is tested
plumbing, not a completed provider revocation implementation. A caller-bound
current-session status RPC or equivalent trusted source needs separate design,
review and hosted schema approval. JWT validity/get_user alone cannot establish
immediate signout revocation; session existence alone does not establish all
provider time-box/inactivity policies. See [Supabase sessions](https://supabase.com/docs/guides/auth/sessions).
Per-provider-session logout/unknown-outcome handling remains unimplemented;
local realm logout is not a provider refresh-token revocation guarantee.

Independent protected recovery transport/service, rollback-resistant current
bindings and restore/promotion fencing remain unavailable. Production session
factory and unconditional startup refusal remain intact. Cross-process/clean
restart component evidence from earlier work is preserved, but actual production
worker, provider-current-state and protected infrastructure acceptance remain open.
Hosted settings, shared abuse controls, managed proxy/cookie behavior and real-device
acceptance are also unqualified. Deployment remains NO-GO.

The original `linux-build-results.json` is byte-for-byte unchanged. A separate
new-image rebuild attempted with build networking disabled could not install
uncached dependencies; no new full-image build success is claimed. The Linux
source-overlay tests above passed and do not replace that rebuild requirement.
The previously successful image tag was not overwritten. No deployment, production
access, hosted Auth/SMTP/Storage setting change, commit or push occurred.

## Approval requests

A. Create exactly two synthetic password Auth accounts in the evaluation project,
   using owner-controlled inboxes and private distinct passwords, individually
   confirmed at creation, with their two automatic profile rows. No mail/invite,
   global settings change or provider sign-in.

B. After account verification, insert exactly one public.admin_memberships row for
   the intended synthetic Admin UUID using the guarded transaction. No User grant
   or schema/client privilege changes. This approval can be deferred until A is
   complete; neither A nor B is currently approved.
