# Runtime hardening after offline evaluation configuration verification

Historical baseline report. The newer local authority/externally fenced PG/logout
implementation and current release gates are documented in
[evaluation/infrastructure/README.md](../../../evaluation/infrastructure/README.md).
The historical unresolved-component descriptions below predate that implementation;
remote deployment and live authentication remain NO-GO.

**Decision: NO-GO for live User/Admin authentication or deployment.** The user's
offline public-key binding check passed. This turn made no Supabase calls, hosted
changes, live provider sign-ins, public app listeners, commits or pushes. No
production credentials or .env were read. Local database/container credentials
and provider responses were throwaway fixtures only.

## Resolved locally and verified

| Area | Concrete change and evidence | Qualification boundary |
| --- | --- | --- |
| Shared dependency wiring | Explicit LocalSessionRuntime installs the selected backend/model/challenge factory for browser, User/Admin auth, pending recovery, recovery grants and email state. Both coordinators receive the explicit provider checker. Backend-specific import monkeypatching is no longer needed in the PG application fixture. | Only an explicit local Python dependency injection path; production still refuses unconditionally. |
| Worker process safety | Backend readiness is checked before runtime publication; runtime cannot cross a fork with inherited clients. Each qualification process builds its own pool and full Flask app. | External pool/TLS/failover and production factory remain unavailable. |
| Cross-worker/restart behavior | Eight actual Flask-route scenarios pass across separate Python processes and owned PostgreSQL restarts, including both realm orders, logout/replay and terminal provider-denial persistence. | Synthetic authentication and per-process test recovery controllers; clean restart is not rollback/failover qualification. |
| Confirmed provider denial | The checker now terminally revokes the selected local auth handle before reporting authentication failure. This fixes a reproduced shared-browser cleanup conflict that left the auth record active. | Requires a trustworthy real checker; no hosted RPC or real provider operation was performed. |
| Provider unknown outcomes | Outage/malformed proof remains 503 without local revocation, activity renewal, memory fallback or automatic retry. Uncertain local revoke does not claim authentication cleanup succeeded. | Actual provider logout and encrypted uncertainty/cleanup handling remain open. |
| Authority lock waits | Both protected metadata and recovery clients now bound lock acquisition and include queue time in response-budget checks. Contention denies before contacting the authority. | An actual transport must enforce its own network deadlines; the client cannot interrupt arbitrary blocking provider code. No protected service is supplied. |
| Proxy policy | Local HTTPS qualification now ignores forwarded Host/client-IP/port, trusts only configured scheme hops, requires the exact host and rejects noncanonical/plaintext requests. | Actual trusted edge sanitation is not established by unit tests or an environment flag. |
| Direct local HTTPS profile | Explicit ROSAGO_EVALUATION_TRANSPORT=direct-local-https accepts only HTTPS loopback origins, zero proxy hops and no proxy-attestation flag. It ignores all forwarded headers; plaintext/other ports fail. | No certificate, OS trust setup, TLS listener or live browser request was created. Production session guard still prevents launch. |

Local runtime injection cannot enable production, and has no environment bypass.
The normal process-local development behavior is not relabeled production ready.
The new profile permits safe configuration preparation for direct local TLS; it
does not authorize launching it before the other gates pass.

## Focused validation

- **124 offline tests and 127 subtests pass** across composition, User/Admin
  authentication, provider checks/transports, normal coordination, realm isolation,
  HTTPS/proxy policy, evaluation isolation, public-entry refusal and shared logout.
- **13 additional protected-authority/recovery tests and 15 subtests pass.**
- **Four real local PostgreSQL/Flask integration tests pass** for explicit runtime
  wiring, provider unknown/confirmed denial, shared login/logout and shared recovery
  state. No real provider authentication or recovery operation occurred.
- **Eight process/restart scenarios pass** in runtime-worker-qualification.json.
  Concurrent activity CAS conflicts can produce temporary 503 responses; tests
  verify no credential/cookie loss and a subsequent stable read succeeds. This
  is a remaining concurrency/availability limit, not production load acceptance.
- A separate current-source Linux image rosago-evaluation:runtime-check builds.
  **34 focused tests pass inside it**, plus dependency, non-root, sensitive-file
  exclusion and expected direct-local-HTTPS startup-refusal checks. Runtime network
  is disabled and no application ports are published. Existing successful images
  and original linux-build-results.json remain unchanged.

Initial local harness runs revealed missing Windows system variables and an overly
strict expectation that both simultaneous activity-CAS updates always return 200.
The harness now keeps only required OS variables, excludes inherited app credentials,
and distinguishes safe transient 503 from authentication loss. Raw errors, DSNs,
keys and cookie values are never saved in the evidence. Owned lab containers and
volumes are removed after each run.

## Blockers still open

1. **Production shared-session activation:** LocalSessionRuntime is a tested
   composition candidate, not a production environment factory. A selected real
   store, restricted runtime role, TLS verification, keyring/epoch lifecycle,
   maintenance, resource limits and readiness/failure behavior need qualification.
   The PG pool still deliberately accepts only numeric-loopback laboratory DSNs.
2. **Independent protected recovery authority:** No independent durable service,
   authenticated bounded transport or trustworthy current binding is available.
   Client nonce/revision checks and test controllers cannot prove restore safety.
   Recovery state must be outside the session-store/app backup and admin failure
   domain and fence restores/promotions before old sessions can be served.
3. **Real provider-session validation:** The new transports and local checker
   wiring are tested, but the proposed caller-bound status RPC is not installed
   or authorized. Its existence/not_after proof does not implement every provider
   lifetime/inactivity rule. Actual issuer/signing and provider acceptance remain
   untested under the current prohibition on live sign-ins.
4. **End-to-end provider revocation:** Normal/shared logout still revokes local
   authority only; explicit scope=local transport is not wired into a durable
   logout/unknown-outcome protocol. A provider failure must not be called completed
   logout, nor erase the only cleanup evidence or be retried automatically.
   Existing direct data API RLS does not check provider session liveness, so JWT
   replay can outlast signout. App-only checking does not close that gap.
5. **Actual HTTPS acceptance:** The direct TLS option is configured/tested at WSGI
   level only. Real certificate trust, numeric-loopback binding, secure browser
   cookie issue/delete and absence of unprotected HTTP access need acceptance.
   Managed-proxy use additionally needs verified edge behavior.
6. **External acceptance:** Shared abuse enforcement, real infrastructure recovery/
   failover, production worker lifecycle, real devices and the diagnostic profile's
   email/photo-disabled feature boundaries remain unqualified. No guard is removed.

## Exact next operator actions

Do not launch either app, run live sign-ins or change either hosted project yet.

1. **Choose the intended HTTPS path.** For a single-machine controlled test, the
   prepared option is direct local HTTPS at `https://127.0.0.1:5443`, bound only to
   numeric loopback, with a certificate trusted by the test browser and a matching
   IP SAN. The eventual profile uses ROSAGO_EVALUATION_TRANSPORT=direct-local-https,
   ROSAGO_PUBLIC_ORIGIN=https://127.0.0.1:5443,
   ROSAGO_EVALUATION_PROXY_HOPS=0 and ROSAGO_PROXY_HEADERS_SANITIZED=false.
   No certificate/secret is generated or installed by this report. A managed proxy
   remains an alternative only with its exact HTTPS origin and independently
   verified single scheme-header hop. Do not guess the attestation.
2. **Identify an existing independent session/recovery service, or request a
   separate infrastructure design/provisioning approval.** Supply only non-secret
   service/provider names and the operator's restore/failover policy, not passwords,
   API keys, client certificates or database URLs. The locally rehearsed candidate
   is a dedicated session PostgreSQL store plus a separately controlled recovery
   authority, not new session tables in either Supabase project. If no authority
   exists, there is no environment-only step that makes production startup safe.
3. **Review the concrete provider-check schema proposal separately:**
   evaluation/auth-testing/provider_session_rpc.review.sql. Applying it would be
   a new hosted schema operation and requires separate approval. No account or
   live-test approval covers it. Resolve the direct-API revocation guarantee and
   provider-logout cleanup design before calling revocation complete.
4. Once infrastructure and enforcement designs are approved and implemented,
   privately configure only the pinned evaluation public credentials and fresh
   evaluation-only session secrets. Requalify that actual transport/store/TLS path.
   Keep both Supabase projects unchanged until their specific operations are
   separately authorized.
5. Only after those gates close, request/receive the bounded live-test approval
   in evaluation/auth-testing/README.md. Existing account/membership approvals do
   not authorize sign-in sessions, new schema, infrastructure or deployment.

## Reproduction

From the repository root, tools/run_session_pg_checks.py --runtime-wiring runs
the four selected real local integration tests. tools/qualify_runtime_workers.py
runs the separate-process/restart checks using one owned throwaway PostgreSQL
container and synthetic providers; it starts no application listener.
No command in this report starts a live application or modifies a hosted project.
