# Focused synthetic identity acceptance

Labels U and A mean the distinct nonmember User and member Admin accounts.
Do not collect passwords, tokens or cookies as evidence. Record actor label,
scenario ID, status/boolean/count and outcome only. Verify project reference and
issuer before each live test window. Stop on any mismatch or unexpected record.

| ID | Check | Expected result | Current execution boundary |
| --- | --- | --- | --- |
| AUTH-1 | U normal password login | Verified confirmed identity; User session only | Offline mocks now; hosted sessions require test approval and qualified runtime |
| AUTH-2 | A Admin password login | Membership checked before installing Admin authority | Same boundary |
| AUTH-3 | U attempts Admin login; forged role field/metadata | Denied; no Admin authority or membership | Offline mocks/local PG now; live attempt later |
| AUTH-4 | Wrong password, unconfirmed identity, wrong issuer/subject/session, recovery AMR | Denied; generic errors, no secrets in output | Synthetic/offline now; no extra hosted account or settings change |
| DATA-1 | Anonymous/U database reads | Exactly published evaluation-garden; draft hidden | Local real PG now; user-JWT hosted reads later; MCP row visibility is not this test |
| DATA-2 | A database reads | Garden and Draft; only own membership/profile | Local PG now; actual hosted JWT read later |
| DATA-3 | U calls Admin overview/check | is_admin false; overview denied | Local PG now; live read-only overview test later |
| DATA-4 | U or A tries self-grant/direct destination writes/private mutator | Privilege denied; no mutation | Disposable PG only; do not issue hosted write probes under account approval |
| SESSION-1 | Both login orders in same browser; cross-realm cookie substitution | Independent User/Admin authority; substituted cookie rejected | Existing offline Flask contracts; live after runtime qualification |
| SESSION-2 | Logout in either realm, replay old selected cookie | Selected local authority revoked; other realm preserved | Offline/shared-store tests now; live own-session logout requires test approval |
| SESSION-3 | Concurrent refresh/logout, stale save and uncertain commit | No resurrection/automatic mutation retry; bounded fail-closed response | Real disposable shared backend and synthetic providers now |
| SESSION-4 | Backend/control-plane unavailable or stale proof | Protected action denied; no memory fallback; transient outage does not claim logout | Offline fault injection now; hosted failure exercise needs separate scope |
| SESSION-5 | Fresh access token after provider session removal | Current-session check denies next protected admission | New offline optional hook only; production source/wiring unavailable |
| SESSION-6 | Separate processes, clean restart, rollback/failover | Shared revocation persists; uncertain recovery stays closed | Prior local clean-restart proof preserved; full rollback/protected service remains open |
| SESSION-7 | Password reset, Admin membership revoke/regrant, key rotation | Respect independent authority, existing scopes and provider-current state | Plan only; these hosted mutations are not approved |

The minimal later live test approval can cover U/A sign-in and safe authenticated
reads, negative Admin login for U, and logout of their own newly created provider
sessions. It does not authorize account reset/deletion, grant revocation, state
restore, uploads, destination edits, malformed write probes or public deployment.

## Local evidence commands

From the RosaGo repository root, the focused offline selection is:

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_provider_session_check.py tests/test_normal_auth_coordinator.py tests/test_independent_sessions.py tests/test_admin_login.py tests/test_admin_authorization.py tests/test_evaluation_isolation.py tests/test_session_release_blockers.py
```

`tools/qualify_account_roles.py` reconstructs the reviewed schema and seed in an
owned temporary loopback PostgreSQL container, uses two local Auth stubs, rehearses
the guarded membership transaction, and checks actual anon/nonmember/member RLS
and privilege denial. These are local database fixtures, not Supabase accounts.

Existing shared-store/application checks are reproducible with
`tools/run_session_pg_checks.py` and `--application-qualification`; independent
process/restart checks are in `tools/qualify_evaluation_readiness.py`. These use
test recovery providers and synthetic authentication; do not label them production
authority, real Supabase authentication or deployment approval.

## Remaining session engineering

The optional coordinator provider_session_check hook receives the server-only
record, configured issuer and selected realm on every protected admission,
including fresh tokens. Exactly True admits, False denies authentication, and
unknown/malformed/exception results deny transiently before database-client
construction or activity renewal. No positive cache, automatic retry or raw
provider error escapes. Existing local factories do not activate this hook.

A real checker must verify the current session for the exact verified
issuer/user/session_id. Supabase documents that JWTs can remain valid after signout
and that auth.sessions can establish whether the session was removed:
[Supabase sessions](https://supabase.com/docs/guides/auth/sessions).
Neither JWT signature/expiry nor get_user alone is a completed revocation policy.
Existence alone also does not enforce time-box/inactivity expiry; provider limits
require an explicit policy and qualification. Do not force-refresh on every request
as a replacement; refresh rotation/races and outages need separate handling.

One candidate is a narrowly checked, caller-bound current-session RPC which
derives identity from verified claims and returns only status, never auth.sessions
rows. It would be new hosted schema and needs separate design/review/approval.
Do not grant clients SELECT on auth.sessions or give application routes a service
key. No RPC is added by this preparation. Provider signout must be per-session,
preserve the other realm and handle unknown outcomes without automatic retries;
existing local logout alone does not prove refresh-token invalidation.

Protected recovery still needs an independent durable authority and authenticated
bounded transport outside the app/database rollback domain, current bindings,
restore/promotion fencing and worker/lease draining. The optional hook does not
supply that service. Production session factory and refusal guards remain closed.
