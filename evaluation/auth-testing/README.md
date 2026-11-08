# Controlled live authentication — prepared, not authorized to run

Latest local progress and remaining gates are recorded in
[runtime hardening](../../docs/production-readiness/remote-evaluation/runtime-blockers.md).
The owner has verified the offline evaluation public-key binding. Direct local
HTTPS configuration and explicit local shared-runtime composition are now tested;
no live launch or hosted sign-in is authorized or qualified.

Project: `jfaufpfzfhysqkhcdsrs` only. No live sign-ins were performed. Production
is excluded from both inspection and testing. The MCP remains read-only.

**Decision:** backend configuration can be bound exclusively to evaluation, but
the local User/Admin web runtime is not ready for live authentication. Both
systems share app.py and one backend configuration; they do not need different
Supabase projects or credentials. Current evaluation_wsgi refuses startup through
the production session guard. The default managed-proxy profile requires a real
HTTPS origin with a verified single sanitized proxy hop. The explicit
direct-local-https profile instead permits HTTPS loopback with zero proxy hops;
it still cannot bypass session/recovery qualification. Do not use
development/redis-local, flask run or python app.py to work around these gates.

## Verified target and identities

Read-only evaluation inspection confirmed two accounts/profiles, zero provider
sessions and exactly this membership:

| Actor | UUID | Membership |
| --- | --- | --- |
| U: ordinary User | 3c572202-c1da-4e5a-aa20-d89be25b2d9f | None |
| A: synthetic Admin | 4bc67593-c979-4441-b42a-99b6d3da2885 | Admin |

Only evaluation-garden (published) and evaluation-draft (draft) exist, with NULL
photo URLs. Storage buckets/objects are empty. Account credentials remain private
with the owner; these UUIDs are identifiers, not passwords/tokens.

## Isolation changes completed locally

- Evaluation configuration is now pinned to this exact reference and HTTPS URL.
  A different project, including any other non-production project, is rejected.
- Only the enabled modern public key independently inspected through evaluation
  MCP is accepted by fingerprint. Source embeds only SHA-256, not the key:
  `c7640668eb470357306772fa6a19ac67b0ab207a64aee24875c3d59e28c561d3`.
  Unexpected opaque keys, including keys from another project, fail offline.
  Rotation requires new evaluation-only key inspection and a reviewed pin update.
- Legacy anon JWT keys and nonempty alternate SUPABASE_* variables are rejected
  in this profile. This includes Storage bucket/secret/URL, service-role, access
  token and JWT secret variables. Routing must explicitly be disabled; paid keys,
  DATABASE_URL and custom OSRM configuration are rejected.
- app.py skips workspace dotenv loading in evaluation mode and validates before
  SDK client creation. User/Admin/public clients derive their Supabase endpoints
  from the same validated URL/key; photo configuration cannot receive a secret
  or bucket here. No production hostname was found in templates/static assets.

These checks establish configuration binding, not a server-wide network firewall
or a proof about an arbitrarily launched process. Use only the reviewed entrypoint
and a fresh allowlisted environment once runtime gates close. Do not reuse a
production shell environment or copy an existing .env. No .env was read or edited
for this preparation; no public key value was saved in the repository/reports.

## Exact next operator actions — safe now, no hosted changes

The owner has already completed the offline binding check successfully. The
steps below are retained for reproduction; the next unresolved operator decisions
are the HTTPS path and independent session/recovery services described in the
runtime hardening report. Do not repeat the key check as a substitute for them.

1. Do not start either web application or sign in yet. Open a new VS Code terminal
   at the RosaGo repository root. Do not activate or source a production .env.
2. Open the evaluation dashboard; confirm its URL contains jfaufpfzfhysqkhcdsrs.
   Under project API Keys, locate its existing enabled **publishable** default key.
   Copy only that public key, not a secret/service-role key or account token.
3. Run the offline binding check:

   ```powershell
   .\.venv\Scripts\python.exe -I .\tools\check_evaluation_backend.py
   ```

   At its hidden prompt, paste the evaluation publishable key. Do not supply an
   account password. The script uses a new four-field mapping and ignores inherited
   credentials, never imports app.py, loads dotenv, constructs an SDK, signs in,
   starts a listener or saves configuration. It validates URL/ref/key fingerprint
   only. Expected sanitized result includes public_key_binding_verified=true,
   offline_only=true, configuration_saved=false and web_runtime_qualified=false.
   Stop on any error; do not change the pin to make a different key pass.
4. Return only that sanitized PASS/JSON output. Do not paste keys or credentials.
5. Close the remaining engineering gates below before configuring a runtime or
   requesting the bounded live-test execution window. No application launch
   command is authorized or provided for the currently blocked runtime.

## Exact eventual environment — specification, not runnable setup

Create a fresh allowlisted child/service environment; never bulk-import the
current process or workspace .env. There is no approved live launcher yet.

| Variable | Required value / condition |
| --- | --- |
| ROSAGO_EVALUATION | true |
| ROSAGO_EVALUATION_PROJECT_REF | jfaufpfzfhysqkhcdsrs |
| SUPABASE_URL | https://jfaufpfzfhysqkhcdsrs.supabase.co |
| SUPABASE_KEY | Existing enabled evaluation publishable key matching the inspected pin; enter privately |
| ROSAGO_AUTH_MODE | production; do not substitute development/redis-local |
| ROSAGO_EVALUATION_EMAIL_MODE | disabled |
| ROUTING_PROVIDER | disabled |
| FLASK_SECRET_KEY | Separate private evaluation-only secret, at least 32 characters; actual generation/configuration is not performed in this preparation |
| ROSAGO_EVALUATION_TRANSPORT | managed-proxy (default), or explicit direct-local-https for loopback-only TLS; neither enables production sessions |
| ROSAGO_PUBLIC_ORIGIN | Actual canonical HTTPS test origin; direct mode may use https://127.0.0.1:5443 with trusted certificate/loopback binding; no pretend .invalid or production origin |
| ROSAGO_EVALUATION_PROXY_HOPS | 1 for a verified managed proxy; 0 for direct-local-https |
| ROSAGO_PROXY_HEADERS_SANITIZED | true only for a verified managed proxy; false for direct-local-https, which ignores all forwarded headers |

Leave SUPABASE_STORAGE_BUCKET, SUPABASE_STORAGE_SECRET_KEY, service-role/JWT/access
tokens, SUPABASE_STORAGE_URL, DATABASE_URL, GEMINI_API_KEY, ORS_API_KEY and
OSRM_BASE_URL absent. No Storage resources are used by the proposed auth tests.
Do not set ROSAGO_LOCAL_HTTPS_QUALIFICATION or raw LMDB authority paths to turn
local test fixtures into a purported production authority.

The existing session_readiness preflight additionally names
ROSAGO_SESSION_BACKEND=redis, ROSAGO_SESSION_KEYRING (current key ID plus base64
32-byte key map), ROSAGO_PROXY_HOPS, ROSAGO_SESSION_REDIS_USER_URL,
ROSAGO_SESSION_REDIS_ADMIN_URL (rediss with credentials), ROSAGO_SESSION_NAMESPACE,
ROSAGO_USER_SESSION_EPOCH and ROSAGO_ADMIN_SESSION_EPOCH. These are not a working
production factory. Do not populate them now: new secrets/infrastructure need
their own approved plan. There is no environment setting for a qualified external
authority transport/current binding, and the PostgreSQL adapter remains a numeric-
loopback laboratory adapter. Environment variables cannot close this missing code.

## Focused later live acceptance — separate approval required

Start with a read-only evaluation preflight: same two confirmed profiles, one
intended membership, two destinations, zero baseline sessions and unchanged schema.
Record only actor label, route, status/count and pass/fail; do not save credentials,
cookies, HAR bodies or tokens. Keep any replay references in a private in-memory
test harness only. Stop on wrong issuer/host, extra records, unexpected writes,
secret-bearing logs, missing authority or unqualified runtime.

| Step | Controlled action | Expected result |
| --- | --- | --- |
| 1 | U signs in at /login | Confirmed U identity, issuer bound to evaluation; User realm only; /user admitted |
| 2 | U reads /places and /places/evaluation-draft | Garden visible; Draft hidden/unavailable |
| 3 | U attempts /admin/login and protected /admin/places | No Admin session/authority; Admin entry denied |
| 4 | A signs in at /admin/login | Fresh membership verified; independent Admin session |
| 5 | A reads /admin/places and Draft detail | Both destinations visible, including Draft; no destination edits |
| 6 | U and A use same browser, both login orders | User/Admin cookie realms remain independent; a User cookie alone cannot grant Admin |
| 7 | Logout User via normal CSRF-protected flow | Old User reference denied; Admin remains valid; newly created provider User session signed out only when its approved integration is wired |
| 8 | Repeat in reverse for Admin logout | Admin authority denied; User preserved; no global/others signout |
| 9 | Reuse only the test's old references in memory | Local revoked reference fails; fresh JWT after provider removal is denied per agreed revocation policy; no token refresh resurrection |
| 10 | Read-only final MCP check | Exactly two users/profiles, one original membership, two unchanged destinations and unchanged schema; no outstanding test sessions, or explicitly report unresolved cleanup |

The public User destination UI uses an anonymous PublicPlacesClient, so it stays
published-only. A's authenticated database JWT has Admin RLS membership regardless
of browser realm; direct authenticated API visibility differs from the public
UI. Never treat logging A into /login as an ordinary nonmember test.

Password reset, account deletion/ban, Admin revoke/regrant, destination mutations,
Storage operations, hosted failure injection, restore/rollback, key rotation,
global Auth changes and public deployment are not part of this proposed window.
Blocked tests are not passes. No live test has been run or approved.

## Engineering progress and remaining security gates

Prepared bounded transports for caller-bound current-session status and explicit
scope=local provider signout. MockTransport tests cover exact endpoint/headers,
strict booleans, issuer/realm errors, redirect/outage/malformed denial and no
automatic retry after uncertain logout. Neither transport is wired into an app
factory or route yet. Local logout currently revokes app authority only.

`provider_session_rpc.review.sql` is a **new, unapplied schema proposal**. It derives
caller identity/session from verified Auth claims and returns only a boolean for
that caller's session, including not_after. It grants no access to auth.sessions.
It passed local Auth-stub checks, not hosted/provider acceptance. Do not apply it
under account, membership or live-test approval; it needs separate schema review
and approval. Supabase explains session_id/removal checks in its
[sessions guide](https://supabase.com/docs/guides/auth/sessions).

Remaining gates:

1. Production shared-session factory, encryption/key management, provider-check
   wiring, selected-realm logout ordering and unknown-commit handling.
2. Independently durable protected recovery authority/transport, current binding,
   restore/promotion fencing, worker/lease draining and rollback/failover evidence.
   Test controllers cannot establish these properties.
3. Agreed provider revocation semantics: existing JWTs may remain valid after
   signout. App admission checks alone do not fence replay against direct data
   APIs, whose current RLS does not check session liveness. Additional reviewed
   enforcement or an explicitly accepted bounded expiry policy is needed. Mere
   session-row existence also does not establish every configured inactivity/
   time-box policy. See [Supabase signout](https://supabase.com/docs/guides/auth/signout).
4. Actual local HTTPS/proxy/cookie configuration, shared abuse controls and clean
   process/worker/restart acceptance; the current remote profile does not admit
   a raw loopback development server.
5. Hosted Auth settings remain unverified by the available read-only tools.
   Provider signing/issuer and actual synthetic-account acceptance remain untested.
6. Full runtime/device acceptance is still open. The current-source Linux image
   rosago-evaluation:controlled-auth-check now builds and passes offline non-root,
   dependency/file-exclusion and expected startup-refusal checks with no network
   or published ports. Historical successful image evidence is preserved. This
   build closes only the current-source packaging check, not runtime admission.

**Approval request:** a later bounded U/A sign-in, safe-read, negative-Admin-login,
selected-realm logout/replay test window exactly as listed above, only once its
runtime/revocation gates are closed. Approval does not authorize schema/RLS changes,
new infrastructure/secrets or bypassing startup refusal. For now only the offline
public-key check is ready for the operator to run. Deployment remains NO-GO.
