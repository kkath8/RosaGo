# RosaGo — final evaluation and deployment readiness

**2026-11-07, Asia/Manila. Evaluation deadline: November 8, 2026. Public authenticated deployment: NO-GO.**

Local User/security fixes were implemented and focused tests passed. No completed Admin destination tests, inventory audit, real login, hosted mutation, email delivery or deployment was repeated.

## Working features and evidence limits

| Workflow | Current evidence |
| --- | --- |
| Registration / verification | Focused validation, consent, OTP/resend, safe errors and callback tests pass with provider doubles |
| Login / logout | Provider-result validation, opaque session handling, expiry, refresh and local revocation tests pass |
| Recovery / reset | PKCE, invalid/replayed callbacks, limited recovery grants, password reset and isolation tests pass |
| Browse / search | Published filtering, search/parsing, pagination, details and failure handling pass |
| Recommendations / AI | Ranking, quiz/recommendation/preview routes and Gemini structured-output/fallback contracts pass |
| Maps / routing / weather | Map routes, destination-bound routing, forecast parsing/cache/outage handling and frontend checks pass |
| User/Admin separation | Independent logout, cross-realm cookie/CSRF denial and production startup refusal pass |

These are **offline application/provider-contract results**. They do not certify real mailbox delivery, Gemini entitlement/spending limits, live forecast/routing uptime or a production Linux deployment. Prior real Admin editing evidence remains valid within its recorded scope; it was not rerun.

### Focused verification

- **257 User workflow tests passed**, zero errors/failures/skips and zero outer network-guard attempts. Real credentials were scrubbed before module loading. [Results](isolated-results.json); [runner](run_user_checks.py).
- **63 changed-component tests passed, 90 subtests passed**. [Results](changed-component-results.json).
- **Six frontend files passed**: registration, verification, recovery, map routing, map UI and recommendation UI. [Results](frontend-results.json).
- pip check passed; edited Python/configuration files compile. This is not vulnerability scanning or Linux dependency resolution.
- Initial focused failures exposed one test needing a normal browser Origin header and the map referrer-policy interaction. Both were corrected; the final scoped checks pass. Initial workflow evidence is retained in initial-user-results.json.

## Implemented fixes

1. **Public email-form CSRF admission:** register and forgot-password now reject missing/null/foreign Origin and cross-site Fetch metadata before contacting providers. These browser forms use strict same-origin admission, not a new synchronizer-token flow. Test helpers explicitly send normal Origin; raw negative tests bypass no security checks.
2. **Email abuse mitigation:** bounded local registration/recovery counters cap accepted attempts per address/purpose at 20/minute with Retry-After. Invalid field submissions do not trigger email. These counters are process-local and do **not** close the shared public abuse-control blocker.
3. **Trusted redirects:** ROSAGO_PUBLIC_ORIGIN is validated; active registration and recovery routes construct callbacks from configuration rather than request Host or hard-coded localhost. HTTPS is required outside development; HTTP is limited to explicit loopback origins locally. Local default remains port 5000 for compatibility; set port 5055 explicitly if using it.
4. **Registration enumeration:** existing-account provider errors now follow the same pending-verification navigation as accepted signup rather than returning “already exists.” Neither response grants authentication. This does not claim constant-time provider behavior or remove provider-side enumeration risks.
5. **Browser/resource protections:** nosniff, frame denial and a limited frame/base/object CSP are added. Sensitive auth pages use no-referrer/no-store; normal pages use strict-origin-when-cross-origin so map tiles receive origin attribution. Body size is capped at 6 MiB, form memory at 128 KiB and form parts at 100. Existing tighter route-specific limits remain.
6. **ORS migration:** the optional server-side endpoint now uses https://api.heigit.org/openrouteservice/v2/directions/... with the existing server-only key and protocol checks. OSRM remains the default when no ORS key is configured. The provider documents the required host **and service-prefix** change. [Official migration](https://ask.openrouteservice.org/t/deprecating-api-openrouteservice-org-in-favour-of-api-heigit-org/7912).

Main source changes: app.py, public_auth_security.py, recovery_transport.py, routing_service.py; focused tests were updated/added. No session adapter was activated and session_realms.py's production refusal was preserved.

## Render preparation: candidate only

Added at repository root:

- render.yaml: Flask/Python service, automatic deploys off, production auth mode, runtime secret inputs and readiness path.
- requirements-render.txt: existing requirements plus reviewed Gunicorn 26.2.0 pin.
- gunicorn.conf.py: two bounded sync workers, no preload, path-only access logs without query strings/bodies, explicit limits; forwarded-header trust is not blindly enabled.
- production_wsgi.py: refuses development/experimental modes before importing the application.
- Application origin configuration also refuses development/experimental mode when Render's RENDER=true marker is present, covering accidental use of a different WSGI entrypoint. The six focused release-security tests passed again after adding that check.
- /health/ready deliberately returns **503** until qualified production sessions/readiness are implemented. It cannot make the blocked application look ready.

The explicit production startup refusal still applies. **Do not set development/redis-local, change the health result to 200, or weaken the entrypoint to force Render online.**

Python 3.13.18 is the prepared runtime pin. Availability on Render, Linux wheel/dependency compatibility, Gunicorn execution and service resource sizing still need qualification. YAML critical fields were manually reviewed; a machine Blueprint/schema validation tool was not available locally. [Local checks](deployment-checks.json).

Official references: [Render Flask](https://render.com/docs/deploy-flask), [Blueprint specification](https://render.com/docs/blueprint-spec), [Gunicorn release](https://pypi.org/project/gunicorn/), [Python security releases](https://blog.python.org/).

## Remaining critical public blockers

1. **Production session/recovery authority remains unfinished.** Active User/Admin credentials, verification/recovery state and throttles are process-local. No reviewed shared production session integration/recovery boundary is active. Cross-worker logout/refresh, restart behavior, backup/rollback revocation and other-session invalidation after password reset are not qualified. The earlier PostgreSQL candidate must not be enabled as a deadline workaround.
2. **Hosted account/email acceptance is unqualified.** Current Supabase Site URL, redirect allowlist, SMTP/templates, confirmation/reset delivery and User-owned profile/trip/draft enforcement were not reconfigured or newly inspected. No approved mailbox test was performed. The app redirect defect is fixed; operator/provider setup remains.
3. **Public abuse and paid-service controls remain incomplete.** Local email counters are mitigation only. Shared/edge limits, trusted client-IP policy and Gemini project quotas/budget/usage acceptance are required. A model key or an offline test does not prove live model access.
4. **Production hosting/operations remain unqualified.** Canonical HTTPS/host/proxy/cookie admission, Linux build, log-sink redaction, readiness, secrets, supported backup/recovery and rollout acceptance are not complete. Runtime pin/dependency patches must be installed and tested; the local interpreter used here is still 3.13.1. Prepared configuration is not deployment clearance.

This task did not repeat the extensive prior audit or start another session-authority experiment. It closes bounded defects while retaining the genuine release blocker.

## Exact operator actions

### Before any later public release

1. Choose the approved production project and final HTTPS hostname. Do not infer that the existing capstone project is disposable. The existing project reference from the verified Admin work is brnkigrrqdrywahvcbvc.
2. After approving hosted security-setting changes, open Supabase **Authentication → URL Configuration**:
   - Site URL: https://APPROVED_HOSTNAME
   - Exact allowed redirects: https://APPROVED_HOSTNAME/auth/callback and https://APPROVED_HOSTNAME/auth/reset-callback.
   - Avoid broad production wildcard redirects.
3. Set application **ROSAGO_PUBLIC_ORIGIN=https://APPROVED_HOSTNAME**, with no path/query/fragment. Keep SUPABASE_URL and the publishable SUPABASE_KEY on the intended project. Never substitute the Storage secret or service-role credential as the public database actor.
4. Under **Authentication → Email / Email Templates / SMTP**, confirm email confirmation policy, approved PKCE-compatible recovery/confirmation links, sender/domain authentication, expiry and custom SMTP credentials. Supabase's default SMTP is restricted and unsuitable for general respondent registration. Do not send a real message until the exact test mailbox and email/reset operations are approved. [Redirect documentation](https://supabase.com/docs/guides/auth/redirect-urls), [SMTP documentation](https://supabase.com/docs/guides/auth/auth-smtp).
5. Complete the shared session/recovery implementation and isolated/staging qualification. This is engineering work, **not a dashboard toggle**. Require independent User/Admin continuity and logout, failed/uncertain refresh/reset handling and supported restore/rollback tests. Keep startup/readiness closed until that evidence exists.
6. Qualify the real reverse-proxy path, trusted host list, Secure/HttpOnly/SameSite host-only cookies and forwarding policy. Current Gunicorn configuration intentionally trusts no forwarded IPs; blindly changing it to “*” is not a safe fix. Verify same-origin form admission over actual HTTPS.
7. Set secrets privately, paid-provider quotas and project spending limits; approve one bounded integration acceptance run. Check User ownership enforcement and provider outages using approved test accounts/data. No completed destination test needs repeating.
8. Validate the candidate Blueprint and build on supported Linux with the pinned dependencies, dependency/advisory checks and path-only log sentinel checks. Approve resource costs and deployment separately. Do not deploy or push automatically from this preparation.

No hosted Auth/RLS/API-key change was made here.

### Tomorrow: fastest safe evaluation path

**Use a supervised, single-device localhost evaluation rather than public authenticated hosting.** Keep one process, no reloader, no LAN/public tunnel, and no experimental backend.

- The previously qualified synthetic demo is available at docs/admin-finalization/phase2q-local-demo-readiness/demo_fixture.py. Run from the repository root using the existing venv, then open http://127.0.0.1:5089/login in a fresh private browser profile. It uses synthetic accounts/data; do not enter a real password. Its report lists the synthetic credentials.
- That fixture demonstrates the account/catalog/Admin subset. It does **not** implement full interactive email delivery, Planner persistence or live AI/weather. Label simulated steps and show the focused passing tests for unsupported flows. Do not present the fixture as a real Supabase transaction.
- For a normal-app walkthrough with existing approved test accounts, restart the normal loopback app **after** reviewing these changes and setting ROSAGO_PUBLIC_ORIGIN to its exact localhost origin (for example http://127.0.0.1:5055). The existing no-reloader process does not hot-load the new Python fixes. Do not close/restart an operator's real session without coordination.
- Registration, reset-email sending/password changes and paid AI calls still need their own approved test-account/mailbox/budget scope. Without that approval, skip those live actions and use offline evidence.
- Collect respondent usability feedback separately from the application's production data. Do not create a real destination or change photos for evaluation.

If the evaluation requires all flows to run against live email/AI and a public URL, that requirement is **not safely satisfied by November 8 on current evidence**. Arrange a constrained evaluation or explicitly disclose the incomplete live integration; do not remove safeguards to satisfy the deadline.
