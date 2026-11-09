> Latest completed state: owner-applied evaluation schema and read-only hosted postflight are verified. See [schema-only postflight](schema-only-postflight.md). All 15 migration records and the full catalog match; seven intended security-definer advisory findings are documented. Seed/accounts remain unapproved and deployment remains NO-GO. Earlier status entries below are historical.

> Latest status (2026-11-07): see [continued verification](continued-verification.md). Evaluation-only MCP identity and empty schema are now verified; schema-only setup is ready for separate approval. Linux build success is preserved. Auth settings and production session/recovery deployment remain unqualified. Earlier status entries below are historical.

# Restricted remote evaluation — readiness decision

**Decision: NO-GO for exposing the authenticated Flask User/Admin systems now.** Separate synthetic data and an invitation gate reduce impact; they do not qualify session persistence, revocation, HTTPS admission, abuse enforcement or deployment recovery.

**Latest local progress:** the shared logout conflict and shared email-limit wiring defects are fixed; 29 focused tests and 38 subtests pass. Docker’s Linux engine now starts, but the build is blocked by Docker Hub DNS. The separate evaluation project and qualified production session integration remain unconfirmed/unavailable. See the immediate follow-up at the end; earlier Linux-engine observations below are historical.

No deployment, hosted setting/account/schema change, existing-project read/write, public tunnel, email or paid API call was performed. The current real Admin/Explore flows and previous broad User tests were not repeated.

## Prepared locally

- **evaluation_config.py:** explicit allowlisted evaluation project reference and matching Supabase URL; the known live project **brnkigrrqdrywahvcbvc** is hard-denied. Rejects privileged keys, unexpected Supabase credential variables, inherited Storage secrets, paid AI/ORS keys and database URLs. Legacy anon-key metadata must identify the evaluation project; modern publishable-key ownership still requires provider acceptance. This is classification, not JWT signature verification.
- **app.py evaluation branch:** skips the real workspace .env entirely; validates configuration before constructing clients; disables email account workflows and photo mutation in this initial evaluation profile.
- **evaluation_wsgi.py:** isolated entrypoint, still subject to the existing production-session startup refusal. It does not load a test credential adapter or activate redis-local/PostgreSQL experiments.
- **HTTP preparation:** canonical HTTPS origin, exact trusted host, host-only Secure/HttpOnly/Lax cookie settings, scheme-only single-hop proxy handling and rejection of plaintext/wrong-origin requests. Forwarded Host/client-IP headers are ignored. Actual managed-edge sanitation and real User/Admin cookie interfaces remain unqualified.
- **Browser privacy/isolation:** synthetic-evaluation notices on shared User/Admin layouts and both login pages; camera, microphone and geolocation disabled. An additional CSP intersects with existing policies and limits browser connections/images to self, the evaluation backend and approved map tile images. This is not a server network-egress firewall.
- **Synthetic material:** evaluation/synthetic_places.json contains two fictional destinations, one Published and one Draft, no photos or personal data. evaluation/accounts.example.json specifies synthetic User/Admin identities without passwords, tokens or respondent email addresses. Nothing has been imported/provisioned.
- **Dockerfile.evaluation, its deny-by-default Docker ignore file, and render.evaluation.yaml:** candidate Linux build/configuration, no auto-deploy, generated independent Flask secret, no production environment-group reuse, no dotenv/backups/reports/tests in the image context. Paid routing starts disabled. Readiness remains closed.

The configured backend/issuer checks prevent normal app clients from targeting the known real project, and production-issued claims fail the evaluation issuer policy. This does **not** prove complete isolation of an unprovisioned environment: independent project keys/signing authority, data/Storage URLs, RLS and actual network destinations must still be verified. Never clone production Auth, users, data or credentials.

## Focused local checks

**20 tests passed, 36 subtests passed.**

New tests cover protected-project rejection, URL/key mismatches, privileged/inherited credential refusal, legacy-key project binding, wrong issuer denial, HTTPS/Host/proxy preparation, cookie flags and no-dotenv startup. They verify that invalid evaluation configuration is rejected before SDK construction, and that a valid configuration still hits the production session refusal without any network connection.

The small regression selection also verifies normal public-entrypoint refusal, User/Admin cookie denial and independent logout. These are local single-process tests, not new remote persistence/revocation proof. No full suite or completed destination audit was repeated.

Command:

    .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_evaluation_isolation.py tests/test_public_release_fixes.py tests/test_independent_sessions.py::IndependentSessionTests::test_user_cookie_never_grants_admin_even_for_admin_account tests/test_independent_sessions.py::IndependentSessionTests::test_admin_cookie_never_grants_user tests/test_independent_sessions.py::IndependentSessionTests::test_user_logout_preserves_admin_and_admin_csrf tests/test_independent_sessions.py::IndependentSessionTests::test_admin_logout_preserves_user_and_recovery

### Linux build status

**NOT VERIFIED.** Docker CLI is installed, but the Docker Desktop Linux-engine pipe was absent. WSL enumeration was denied in this execution context. No image build, Linux dependency resolution, Gunicorn startup or Render build was claimed.

After a working Linux Docker engine is available, the prepared build command is:

    docker build -f Dockerfile.evaluation -t rosago-evaluation:check .

Do not run it publicly. Inspect the image/context for secrets and validate dependencies/Gunicorn on Linux. A successful image build would still leave the session/release gate closed.

## Critical blockers applying even to restricted remote evaluation

| Blocker | Why restrictions do not solve it | Required closure |
| --- | --- | --- |
| Shared authentication/recovery state | Separate DB does not share current in-memory User/Admin credentials, email/recovery state or throttles across workers/restarts | Qualified shared backend, concurrency/logout/refresh behavior, documented invalidation/recovery and no memory fallback |
| Revocation/recovery | Old sessions/keys or restored backend state can defeat intended logout/revocation; invitation alone has no freshness authority | Supported restore/rollback prohibition/enforcement and fail-closed current authority; tests with real shared infrastructure |
| HTTPS/proxy/host/cookies | A private URL still receives untrusted requests | Confirm exact Render proxy path and sanitized scheme header; test actual User/Admin cookie issuance/deletion, wrong Host and forwarding spoof denial |
| Shared abuse controls | Local counters reset and multiply by worker; hidden URL is not a limit | Edge/global and account limits; prevent bypass through direct Render origin and direct provider signup; qualify shared application limits |
| Separate project/schema/accounts | No approved evaluation project reference or hostname has been supplied/qualified; local fixture files are not hosted setup | Independently created project/keys, reviewed schema/RLS, synthetic accounts/memberships and data-only seed after approval |
| Linux build/operations | Windows tests do not establish Linux/native-package support or safe rollback | Successful build, dependency/security review, restart/worker/readiness/logging/withdrawal acceptance |
| Paid/external services | Restricted respondents can still incur cost or send personal coordinates | Explicit enablement, shared quotas, consent and bounded live checks; disabled/unavailable otherwise |

**Important new schema portability finding:** migrations/0014_destination_environment.sql contains the real-project hostname in its photo URL allowlist and function-body checksum guards. Do not blindly apply or string-replace the historical migration chain in another project. Prepare a reviewed evaluation-project schema/contract and recomputed checksums separately; do not disable validation. Photos remain disabled in the initial candidate profile.

Current source health and production mode remain deliberately closed. No environment label, invitation secret, reduced worker count or readiness flag may substitute for these closures.

## What can be completed today

**Done:** narrow isolation guards, synthetic-only fixtures/account manifest, disabled risky integration paths, HTTPS/host preparation, bounded build context, Docker/Render candidate, focused tests and the device checklist below.

**External input/engineering still required:** separate project/hostname and setup approval; production-grade shared session/revocation implementation; shared abuse enforcement; working Linux build infrastructure; provider and real-device acceptance. No completion-by-tomorrow promise is supported yet.

No new shared-session backend or authority experiment was introduced. The previous unqualified candidates have not been activated.

## Integrations: honest initial evaluation profile

| Integration | Initial state / live eligibility |
| --- | --- |
| User/Admin password login | Intended real Supabase Auth against synthetic accounts in the separate project only; NOT yet qualified remotely |
| Registration, email verification, recovery | Disabled in this candidate. If demonstrated with static sample screens, label clearly “simulation — no email sent.” Live mail requires owner-controlled test inboxes, SMTP/redirect approval and protected shared pending state |
| Planner/recommendations | Existing deterministic algorithm may use fictional data once evaluation schema/RPC ownership is verified; do not claim live persisted Planner without that acceptance |
| Paid Gemini AI | Key rejected/feature unavailable initially. No fake output presented as live generation. Enable only with separate key/budget/quotas and approval |
| Weather | City-level Open-Meteo is technically eligible after bounded availability/policy checks; current candidate has no live acceptance evidence. Keep unavailable state truthful |
| Maps | Vendored Leaflet and OSM tile images are eligible subject to attribution/provider policy and device loading checks. Browser geolocation is disabled; use synthetic test coordinates |
| Routing | Disabled initially. OSRM is a possible bounded, non-sensitive-coordinate option only after provider-policy/shared-rate checks. Existing per-process limiter is insufficient for a public multiworker guarantee |
| Photo management | Disabled in the diagnostic configuration. No existing-project Storage secret is accepted. A complete respondent build needs separately reviewed test-project Storage permissions and explicit setup approval |

These limitations must appear in the respondent instructions. A disabled function is not an authenticated simulation of a completed service.

## Exact operator actions and fastest conditional deployment procedure

**Do not execute hosted changes or deploy under this request.** Only follow this sequence after explicit setup/deployment approval and closure of the gates:

1. Supply only the new Supabase project reference and desired Render hostname; no credentials in chat. Create a genuinely independent evaluation project after approval. Never restore the existing project's Auth/database/Storage backup into it.
2. Prepare/review the new-project schema and RLS, including destination mutation/audit and itinerary/profile ownership. Resolve the hard-coded photo-contract issue without weakening checks. Apply only after separate hosted-settings/schema approval.
3. Provision unique synthetic User and Admin accounts with operator-owned test aliases and private generated temporary credentials. No respondent's real account/password/email. Assign Admin membership only to intended test actors. Close public/provider signup under separately approved Auth settings; disable real email routes initially.
4. Load only the local fictional destination fixture using a reviewed, separately approved seed. Inspect that no old-project image links, real profile/trip data or production IDs/credentials entered the evaluation backend.
5. Complete shared session/revocation and shared abuse controls before enabling the application. Qualify two actual workers, independent realms, expiry/logout/refresh races, restart behavior and fail-closed backend failure. Do not change the mode to development/redis-local to start it.
6. Start a working local Linux Docker engine and build the image. Review dependencies, copied files, no secret layers, startup failure modes and logging. Do not expose its ports. The current image will not serve authenticated pages while the production gate remains.
7. With explicit approval, use a NEW Render service from render.evaluation.yaml, no linked production groups and no bulk .env import. Populate the new project URL/public key/ref, canonical HTTPS origin and verified proxy-hop attestation privately. Generate an independent Flask secret. Do not add Storage/service-role/Gemini/ORS secrets to this initial profile. Official Render documentation warns that service variables persist when omitted, which is why reusing the existing service is unsafe. [Render environment variables](https://render.com/docs/environment-variables), [Blueprint reference](https://render.com/docs/blueprint-spec).
8. Configure the new-project exact HTTPS Site URL and permitted callbacks only after separate approval. The initial disabled-email mode does not require pretending mail delivery works. Publishable keys still rely on proper RLS and caller JWTs; they are not permission barriers by themselves. [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys).
9. Approve one quarantined staging deployment after the implementation/build gates pass. Keep respondent admission closed during the smoke tests. Verify the request actually reaches the new service/project and all readiness/auth/abuse checks pass; only then approve opening a time-limited respondent window.
10. At the end, close admission and disable/revoke the synthetic test accounts/sessions under approved scope. Do not restore a predecessor session/database snapshot as cleanup.

No deploy-now procedure exists for the current unqualified build. Adding a password or allowlist ahead of it is not sufficient.

## Focused remote-device smoke checklist — after qualification only

Use one Android Chrome, one iPhone Safari, and one laptop browser, with synthetic participant codes:

- Exact HTTPS URL and valid certificate; HTTP, wrong Host and spoofed proxy fields fail. The research team supplies test-account instructions separately.
- User login and Admin login in the same device/profile remain separate in both orders; User cannot open Admin routes. Admin membership is checked server-side.
- Reload, idle expiry, worker handoff and a controlled restart follow the approved persistence policy; logout revokes the old reference; reusing/swapping User/Admin cookies never gains authority.
- A revoked test session, storage outage and stale version fail closed without a silent memory fallback or automatic write retry.
- One pre-approved synthetic destination action appears only in the test project with the correct actor audit; Draft stays hidden, publish/archive affect only fictional records. No production-key/hostname requests appear. Do not run any such mutation without smoke-test approval.
- Email, AI, routing and photos are visibly disabled or clearly simulated. Allowed weather/tiles use non-sensitive coordinates and truthful failure states.
- Shared limit is observed across workers/devices; bypassing the custom hostname cannot reach an unprotected origin. Direct Supabase signup/privileged access is denied per the approved policy.
- No passwords/tokens/query strings in app/edge/error logs; no recording of cookies/HAR bodies. Record only status, route, test actor code and outcome.
- Portrait/landscape, keyboard, forms/errors and slow-network behavior are usable. No personal geolocation, real email or real respondent credential is collected.

## If remote deployment cannot be qualified

The requirement is actual interaction with the working User System from respondents' own devices. A static walkthrough, simulated prototype, or screen-shared demonstration does not satisfy it. If the remote build cannot be qualified in time, reschedule respondent access. Do not expose the development server or call the unqualified fixture a secure remote service.

The research team independently distributes its Google Forms questionnaire after application use. Questionnaire distribution and response storage are outside RosaGo's scope.

**Final: restricted remote authenticated evaluation remains NO-GO. Local preparation is complete within the current constraints; nothing has been exposed.**

## Immediate follow-up: revocation and shared-limit code fixes

Two defects were reproduced and fixed locally in the urgent follow-up. No completed destination/UI audit or full User suite was repeated.

- **Revocation CAS conflict:** record_session_store.RedisModel.revoke and redis_session_flask.shared_logout now make at most three attempts, taking fresh authoritative snapshots after a known RevisionConflict. The whole selected-realm logout transition is rebuilt; other realm state is not touched. Transport/uncertain-commit failures propagate without retry, and browser authority is cleared only after confirmed revocation.
- **Shared email limiter wiring:** public_auth_security.email_attempt_allowed now uses the existing atomic shared rate records when shared sessions are actually configured. It never silently falls back to per-worker memory on a shared-backend outage. Local-only mode retains its bounded development limiter.

**29 focused tests passed, 38 subtests passed** across the new blocker regressions, existing evaluation/public-entry guards and four realm-separation/logout cases. New deterministic tests reproduce stale-revision races, bounded exhaustion, uncertainty, already-missing handles and shared/outage/concurrent rate behavior. They prove component behavior with synthetic backends, **not** deployment of a qualified shared backend.

The existing shared-session adapter was not activated. Production startup/readiness refusal remains. Provider-session sign-out/current-session validation, recovery authority, production persistence and live cross-worker acceptance remain blockers.

**Infrastructure progress:** Docker Desktop was started locally without exposing an application or publishing ports. Its Linux engine reported version 29.9.2. The prepared Docker image build was attempted but failed at base-image metadata retrieval because registry-1.docker.io could not be resolved. No dependency install or Linux application acceptance was reached. Do not bypass TLS or use an older image to work around this; configure working DNS/approved proxy access for Docker and repeat the same build.

**Project discovery limit:** the configured MCP endpoint still identifies the known live project in its project_ref parameter. Its metadata request failed at transport; its available tools do not enumerate all organization projects. Therefore existence of a separate evaluation project is **unconfirmed**, not disproved. No hosted data or settings were accessed/changed.

**Exact next operator actions:** confirm an independently created empty evaluation project in the Supabase dashboard and supply only its reference; if none exists, explicitly approve provisioning before creating/configuring it. Restore Docker Hub/package-index connectivity using approved Docker Desktop DNS/proxy settings. These actions unblock infrastructure testing; they do not by themselves authorize deployment or close the remaining session/recovery integration.

**Current decision remains NO-GO for public respondent access.** A real interactive User System still needs the qualified shared backend and real-device acceptance listed above. A static demo is not a substitute for that requirement. No respondent URL has been created or claimed.

## Scope clarification and real local PostgreSQL component checks

RosaGo contains only the existing User and Admin systems. No questionnaire module, Google Forms integration/link, survey page, or response table has been added. The previously added test-environment notices and template context were removed; server-side project isolation remains. The separate Supabase project means an isolated application backend only. The disabled-feature diagnostic configuration above is not the complete respondent website and cannot meet acceptance by itself.

After this cleanup, **19 focused isolation/session tests and 24 subtests passed**. Using the cached `postgres:17` image, **six selected session tests passed against a real temporary loopback PostgreSQL database**: encrypted storage/TTL, terminal revocation, concurrent refresh/revocation, runtime-role restrictions, uncertain-commit handling, and independent family expiry/shared rate windows. Sanitized results are in `real-local-pg-results.json`; `tools/run_session_pg_checks.py` reproduces only these checks with generated temporary credentials. The owned container and volumes were removed; a subsequent Docker metadata check found no matching lab containers.

These checks used the existing local test recovery controller. They do not qualify a production recovery authority, real Supabase authentication, the active application adapter, or multiworker remote operation. No hosted request, application exposure, questionnaire storage, or hosted setting change occurred. Production refusal remains enabled. Completing and qualifying shared application sessions/recovery remains an engineering blocker, alongside an unconfirmed separate test project and the failed Linux application-image build.

## Separate project preparation and recovered Linux build — latest update

This update supersedes the earlier unconfirmed-project and failed-build status.

The operator reports creation of evaluation project `jfaufpfzfhysqkhcdsrs` and authenticated read-only MCP connection `supabase-evaluation`. Its reference is distinct from the protected existing project `brnkigrrqdrywahvcbvc`. An unauthenticated HTTPS GET to the new host's Auth settings endpoint returned 401, with no credentials sent; DNS and HTTPS reachability are verified. This is not authenticated ownership/schema verification. The current tool catalog still exposes only `mcp__supabase__...`, which independently identified the existing project. No existing-project tools were called after the instruction to use only `supabase-evaluation`. A refreshed tool session exposing the new connection is required to inspect its schema, RLS, grants and settings. Neither hosted project was modified.

Before that connection-only instruction, metadata-only inspection of the existing project identified nine public application tables, all with RLS enabled: profiles, places, trips, trip_places, itinerary_drafts, trip_itinerary, trip_stop_plans, admin_memberships and admin_destination_audit. The MCP migration-history result was empty despite those objects, consistent with manually applied migrations; do not infer an empty schema or blindly replay against either project. No account/destination rows or credentials were copied.

**Prepared:** `evaluation/setup/README.md`, 15 ordered SQL copies, a hash manifest, and a separate two-place synthetic seed. The generator preserves original migrations and rewrites only the two photo host restrictions plus dependent preflight/postflight hashes for the new reference. A first local rehearsal caught the dependent postflight hash; the generator now derives both exact hashes, preserving all integrity checks. The corrected rehearsal applied every file and the seed successfully in disposable PostgreSQL, verifying nine RLS-enabled tables, published-only ordinary visibility, Admin membership visibility and the local Auth profile trigger. Results: `evaluation-schema-results.json`. Minimal Auth stubs are not hosted Supabase Auth acceptance. No seed or migration has been applied remotely.

**Session progress:** six additional focused checks passed with two Flask instances, real local PostgreSQL and synthetic provider responses: independent realm login/logout, CSRF/nonmember/actor checks, cross-instance recovery/verification state, fail-closed authority outage, recovery gate denial, and stale/replayed/uncertain proof denial. The test fixture needed the now-required synthetic HTTPS public origin; production validation was not relaxed. Results: `real-local-pg-application-results.json`. This is in-process application integration with a test recovery controller, not actual independent-worker/restart or protected production-authority qualification. Owned containers/volumes were removed; cleanup metadata check found none.

**Linux blocker cleared:** Docker connectivity recovered. The candidate image built successfully with Python 3.13.18, `pip check`, compilation, and non-root user creation. A read-only, network-disabled container with no published ports passed dependency imports, sensitive-file exclusions, and the expected production startup refusal. See `linux-build-results.json`. The Render candidate now pins the supplied evaluation reference and URL; no key or credential was added. Ten focused isolation tests and 22 subtests passed. No app was deployed or exposed.

**Remaining NO-GO gates / next actions:** refresh the current MCP tool session to expose `supabase-evaluation`; independently verify target identity/schema/policies; review then separately approve new-project schema/seed/accounts/Auth/Storage setup as detailed in `evaluation/setup/README.md`; choose the final HTTPS hostname. Engineering must still complete and qualify production shared-session/revocation/recovery wiring, cross-process/restart behavior, shared provider abuse controls, actual proxy behavior and real-device acceptance. The current email/photo/integration-disabled diagnostic profile is not the complete User/Admin website. Read the plan's exact Auth callback, synthetic account, Storage and RLS requirements before setup approval. A separate project and successful build do not close these runtime security gates. Deployment remains unauthorized and **NO-GO**.
