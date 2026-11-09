# Phase 2O — Final Deployment Architecture and Security Decision

Reviewed 2026-11-05. References: [2L](../phase2l-simplified-session-review/REPORT.md), [2M](../phase2m-postgresql-session-implementation/REPORT.md), [2N](../phase2n-recovery-invalidation/REPORT.md).

**Decision: NO-GO for public authenticated deployment with the infrastructure and evidence currently available. Use a constrained local demonstration now.** The preferred final hosting target is **one paid Render Flask service, one Supabase PostgreSQL session store, and existing Supabase Auth/Storage**, with controlled maintenance recovery and mandatory reauthentication. Freeze that architecture; do not build another Redis/LMDB/witness chain. Buying hosting does not close the recovery boundary or authorize activation.

There is a finite path below. Its first prerequisite is a concrete, enforceable recovery boundary. If that cannot be established with affordable provider controls, stop the public-release effort and use the local demonstration. Do not keep funding speculative session architectures.

## 1. Recommended final architecture

Select one Render `1c-2g` web instance (1 CPU, 2 GB; formerly Standard), initially two Gunicorn workers, root-mounted Flask and a single public HTTPS origin. Supabase Pro with one Micro project holds business data, the private transactional session schema, Auth and Storage. Use a nearby compatible region; qualify actual latency before selecting it. No Render database, persistent application disk, Redis, LMDB or custom always-running authority service is selected.

Preserve two opaque host-only cookies: User `/`, Admin `/admin`, Secure, HttpOnly, SameSite=Lax. Preserve separate realm credentials/CSRF/recovery state, independent logout/expiry, fresh database Admin membership, and B's bearer/UUID attribution. Encrypt credentials with the existing bounded AES-GCM design. Database session connections use a minimal server-only role; business operations continue through the current scoped user/Admin clients and SQL contracts. Never use the session SQL role as the Admin business actor.

Reuse the inactive PostgreSQL implementation, subject to neutral Flask dependency wiring and release checks. Two worker-local pools of at most two connections give **four session client connections**, plus explicitly budgeted other services and maintenance; this is not a claim about Supabase's available limit. No mutable authentication state on Render disk. No production fallback to memory or signed-cookie authority.

Recovery is deliberately disruptive: uncertain restore, lost authority or incompatible rollback requires maintenance and fresh logins for both realms. Pending recovery/verification must restart; business records and audit history persist according to the separately approved data-recovery policy. Ordinary worker restart can preserve sessions if database/key/recovery freshness is known; otherwise availability yields to reauthentication.

**This is a target, not implemented production wiring.** The current adapter is loopback-only, requires a real trusted `RecoveryAuthority`, and has no production provider. A manual runbook is not a drop-in implementation of that interface. Do not supply a stub that always returns VERIFIED, reinterpret a static epoch as fresh proof, or remove the startup refusal to make it start. Any operational-admission integration must be approved, implemented and tested against the boundary below before activation.

## 2. Which rollback risks are realistic?

| Event | Assessment for Render + Supabase | Required handling |
| --- | --- | --- |
| Render worker restart without database rollback | Expected operation; not itself a rollback of session rows. | Revalidate current authority and deadlines; never reconstruct credentials from cookies. |
| Private session-schema import from an old dump | Realistic operator mistake; exactly the substance of 2M/2N failure A. | Prohibit live imports. Restore only behind independently closed admission; invalidate afterward. |
| Whole Supabase project restore/PITR | Realistic disaster recovery. Session markers and potentially Auth state can return together. | Treat all old sessions as untrusted; no transparent reconnect and acceptance of old authority. |
| Render code/environment rollback alone | Realistic rollback mechanism; old key/epoch/config can return. | Only compatible builds with current recovery authorization may run. |
| Old database plus old Render environment | Plausible coordinated recovery. | Current independent control must reject the predecessor combination. |
| Old database, environment and freshness controller together | No real controller exists today. An epoch placed in the same backup/config boundary makes this realistic rather than hypothetical. | Such control placement is disallowed. If current control cannot be established, remain closed. |
| Cloud provider silently restores older acknowledged state | Not reproduced on hosted Supabase and not established as impossible by the reviewed documentation. | Obtain the supported recovery/durability behavior; reject uncertain recovery. No promise of arbitrary rollback resistance. |
| All independent administrative/secret controls deliberately rolled back by a compromised owner | Outside a reasonable capstone application's sole enforcement power. | State this threat boundary explicitly; never quietly describe correlated rollback as solved. Protect owner access and incident recovery. |

The observed failures are genuine restoration of **application session authority**, not evidence that a real Supabase JWT remained valid: provider calls in the experiments were synthetic. They still matter whenever provider validity and membership also remain current or return with the backup. Expiry limits the window; it does not guarantee immediate revocation.

## 3. Exact trust boundary and recovery decision

The trusted boundary must sit **outside both the restored Supabase database and predecessor Render deployment configuration**. It must retain current release/recovery incarnation, never-reused realm epochs and CLOSED/OPEN authorization, and enforce that old workers/credentials cannot serve when freshness is uncertain.

For the preferred low-complexity model, use independently controlled release/maintenance operations rather than a new session service. A named recovery owner, protected current recovery record and restricted deployment/restore credentials are necessary. They are sufficient only if **every supported restore and rollback is prevented from serving stale authority before its first request**. A signed file or password-manager ledger records intent; neither alone stops requests or detects a database restore under a running worker.

Required operational boundary:

1. Runtime credentials cannot restore/import session history, modify recovery admission, retrieve predecessor secrets or trigger deployments. Routine contributors cannot invoke privileged restore paths.
2. Recovery admission is closed outside the database being restored. Verify that all application origins, including Render's default hostname, old instances, callbacks and direct bypass paths are covered. A DNS change or a maintenance page on only one hostname is insufficient.
3. Stop/drain all old workers and database connections before any uncertain restore; rotate/retire obsolete runtime credentials where needed. Health probes alone are not a lock: existing workers can still receive traffic during health transitions.
4. Current recovery state and permitted release/key set survive the database/config restore. Missing or inconsistent evidence blocks start/reopen. Older environment groups or build artifacts cannot reauthorize themselves.
5. Reopening requires invalidated session state, new epochs and verified current workers. Any provider-managed recovery outside this workflow needs an equivalent pre-use interlock or independently fresh authority; otherwise it is unsupported and public release fails.

**Can PostgreSQL safely operate under this model? Yes, conditionally.** Its transactions can invalidate the entire private session namespace while access stays closed; 2N demonstrated this, including interruption rollback. The procedure does not detect an undeclared restore. Current Render/Supabase documentation and local tests do not demonstrate the required complete admission/restore interlock. No current account controls, plan entitlements or independent protected control storage were inspected. Therefore this boundary remains a mandatory blocker, not a paperwork-only mitigation.

The proposed supported threat model trusts provider control planes and authorized recovery owners, but covers ordinary outages, concurrency and mistakes caught by the enforced workflow. It does not silently weaken the existing arbitrary rollback requirement: accepting this controlled-recovery model requires explicit approval. If all-boundary rollback resistance remains required, independent current authority is still necessary; the proposed budget does not include a qualified implementation of it.

## 4. Supabase Auth: use its authority without overclaiming

Keep Supabase as the credential issuer. Do not build password or refresh-token issuance, provider session tracking or a second account system. Its session ID can support a server-side current-session existence check for protected requests, especially Admin mutations, in addition to JWT subject/expiry and fresh membership checks. Missing session or an unavailable authority check must deny the operation. JWT signature validation, `getClaims` or a user-profile lookup alone is not proof of immediate session revocation. This is a proposed check, not a production grant or SQL change. Supabase documents correlation with `auth.sessions` and the post-sign-out JWT limitation. [Supabase sessions](https://supabase.com/docs/guides/auth/sessions).

For realm logout, invalidate the local realm first and explicitly use provider **local** sign-out scope when terminating its provider session. Avoid the SDK's global default, including when the same account occupies both realms. A failed provider call must not resurrect local authority; report/reconcile an uncertain provider outcome without replaying refresh. [Supabase sign-out scopes](https://supabase.com/docs/guides/auth/signout).

This can detect a restored *application-only* session if its provider session was successfully revoked and Auth remains current. It cannot replace browser state, CSRF, bounded refresh ownership or local tombstones. It also cannot close whole-project rollback when Auth history is restored with the session schema. Checking the same project is useful authoritative provider validation, not a separate rollback boundary. Do not assume `/user` validation alone enforces the exact session-row guarantee without testing it. No blanket `auth` schema access or browser-accessible helper is approved here.

## 5. Hosting, costs and responsibilities

USD public list-price estimates checked 2026-11-05; no account quote, tax, FX conversion, purchased capacity or SLA is implied. Workspace subscription and service compute are distinct. Current Render names replace legacy Starter/Standard. [Render compute specifications](https://render.com/docs/compute-plans).

| Option | Monthly base calculation | Suitability / limits |
| --- | ---: | --- |
| Render Free + Supabase Free | $0 + $0 = **$0** | Preview only: sleep, project pause, small quotas; no qualified recovery boundary. |
| Render Free + Supabase Pro Micro | $0 + $25 = **$25** | Better DB backup capability, same Free application limitations; not preferred for public authenticated release. |
| Render paid `0.5c-512mb` + Supabase Pro Micro | $7 + $25 = **$32** | Cost floor candidate, not sized for RosaGo's loaded Python stack/two workers; must pass memory/load tests before considering. |
| **Preferred: Render paid `1c-2g` + Supabase Pro Micro** | $25 + $25 = **$50** | More practical initial two-worker budget. No HA/SLA or rollback protection is purchased by this total. |
| Preferred compute with Render Pro workspace | $25 workspace + $25 compute + $25 DB = **$75** | Optional additional workspace features; not automatically required or sufficient for the recovery boundary. |
| PythonAnywhere Developer + Supabase Pro Micro | $10 + $25 = **$35** | Practical managed Python alternative; different worker/process model and outbound DB/TLS behavior need qualification; same recovery problem. No reason to migrate solely for security. |

Render's indexed first-party pricing lists $7/512 MB and $25/2 GB web compute; its workspace Hobby/Pro prices are $0/$25 plus compute. Check the final provider order screen before purchase. [Render pricing](https://render.com/pricing?trk=article-ssr-frontend-pulse_little-text-block), [workspace pricing announcement](https://render.com/blog/better-pricing-for-fast-growing-teams).

Supabase lists Free at 500 MB DB, with inactivity pausing, and Pro from $25 with first project included, 8 GB disk, daily backups retained seven days and usage limits. One Micro project is covered by the included compute credit; don't add a second $10 to that first-project estimate. Additional projects/compute are additional charges. [Supabase pricing](https://supabase.com/pricing), [compute billing](https://supabase.com/docs/guides/platform/compute-and-disk).

PythonAnywhere's paid Developer plan lists $10/month, one web app, unrestricted outbound access and SSL support. This is an alternative cost comparison, not evidence of app or PostgreSQL qualification. [PythonAnywhere pricing](https://www.pythonanywhere.com/pricing/).

Render Free sleeps after 15 idle minutes and loses local filesystem changes on sleep/restart/redeploy; Render advises against Free for production applications. Paid compute avoids that Free idle policy but does not make local files a recovery authority. [Render Free limitations](https://render.com/docs/free).

**Additional budget items:** staging project/compute, overage bandwidth/storage/Auth usage, backup-object storage, transactional email, domain registration, monitoring and any required restricted-control plan. Use a provider subdomain if a custom domain is unnecessary. These are not priced at zero by assumption. No custom authority-service cost is selected; if the recovery controls require an additional service or higher-tier governance, obtain its cost before authorizing release. The $50 figure is a hosting baseline, not an all-inclusive secure deployment quote.

Operational responsibilities must be assigned before purchase: release owner controls current build/config; recovery owner closes admission and authorizes restore/reopen; maintainer handles patches, cleanup and connection quotas; incident owner handles alerts, secret rotation and suspected rollback. One capstone operator may hold multiple roles, but root/restore/deploy credentials stay out of the application, with MFA and a protected recovery copy. A second reviewer for recovery is recommended; enforce it if the approved threat model depends on two-party control. No control-plane compromise guarantee or 24-hour support is implied.

## 6. Supported backup, restore and rollback procedure

**Backup policy:** keep provider daily backups and separate encrypted business exports with restore instructions and access logging. Back up Storage objects separately; database backups contain object metadata, not the object contents. Treat session credentials, browser state, recovery grants and CSRF challenges as disposable; do not intentionally reinstate their live authority. Pro daily retention is seven days; a 24-hour data-loss budget and one-business-day manual recovery target are proposed capstone objectives, not measured guarantees. Obtain owner approval or choose a different backup budget. [Supabase backup behavior](https://supabase.com/docs/guides/platform/backups).

**Preferred business restore:** restore a backup to an isolated target for examination, validate business rows/IDs/audit and photo references, then use a reviewed data-specific recovery process. Keep current Auth/session authority when legitimately possible; do not import a stale session schema as a shortcut. Business reconciliation itself needs separate authorization and is not performed here.

**Whole-project or uncertain recovery:**

1. Independent admission CLOSED; disable automatic releases and leaked/obsolete deploy hooks. Confirm no direct origin still serves authenticated traffic.
2. Drain and terminate all predecessor workers/connections; preserve incident evidence without recording bearer tokens. Record affected backups, current release and recovery ID in protected control records.
3. Restore only behind that boundary. Do not reconnect old workers to the recovered project. Validate business schema/data and Storage separately; provider Auth state may also be old.
4. Generate never-reused incarnation and User/Admin epochs. Transactionally clear only private application session/workflow state and install QUALIFYING gate state. Require fresh credentials; don't silently exchange restored refresh tokens. Hard-retire prior session encryption authority if freshness is uncertain, with controlled current secret delivery and no predecessor decrypt-key fallback. Do not rotate Supabase signing keys indiscriminately.
5. Reconcile provider-session invalidation if Auth history was restored; the exact provider-supported method must be tested/approved. Fresh application cookies alone do not revoke stolen existing provider JWTs. Keep protected business access closed until its chosen provider-validity policy passes.
6. Start only a compatible approved build with current secrets and real recovery authorization. Verify both realm readiness, denied predecessor credentials/cookies, membership and actor attribution; restart recovery/verification flows.
7. Reopen only after recorded acceptance passes. If control history or secret retirement is uncertain, remain in maintenance and require incident recovery; never mark VERIFIED merely because SQL is reachable.

**Code rollback:** prefer a forward rebuild of a reviewed compatible commit with current configuration. No automatic restore of the old database, epoch or keyring. Render's rollback can reuse service environment values and start commands; environment-group links can also change. Preserve current recovery configuration and reject incompatible builds. Do not use the dashboard Rollback button as the supported incident procedure until its effects have been rehearsed. [Render rollback behavior](https://render.com/docs/rollbacks).

Health checks help route healthy instances, but are not an instantaneous recovery firewall; a failed new deploy may leave old instances serving. Request-level fail-closed behavior and verified closure of all old origins are mandatory. [Render health checks](https://render.com/docs/health-checks).

## 7. Finite prerequisites, implementation and acceptance checklist

These are **eight bounded work packages**, not authorization to execute them. Complete package 1 before spending on further app integration. If it fails, choose the local demonstration and stop; do not initiate another authority experiment by default. No public release until all eight are signed off and a separate deployment approval is given.

| Package | Exact deliverable | Measurable public-release acceptance criterion |
| --- | --- | --- |
| **1 — Recovery boundary and threat model** | Name the actual admission/restore/release controls, protected current record, authorized operators and provider recovery semantics; obtain entitlements/cost and approve supported threats. | In isolated staging, every *permitted* DB import/restore and predecessor environment/build rollback is closed before first stale-authority use. DB+environment rollback cannot reopen. Missing/inconsistent control remains closed. Unsupported silent/correlated rollback is explicitly rejected, not declared solved. **No feasible enforcement means FAIL and local-only.** |
| **2 — Neutral PostgreSQL integration** | Replace hard-coded Redis adapter selection through explicit neutral interfaces; real production factory/configuration and startup/readiness; restricted additive schema/grants reviewed separately. | Two real Flask workers use PG with no Redis/LMDB/memory authority fallback; missing DB/keys/recovery authorization denies startup or requests. Runtime role cannot edit admission or restore history. Safeguard changes only under separately approved release work. |
| **3 — Concurrency and provider-session policy** | Bounded fresh-CAS logout conflict handling, explicit uncertain-commit behavior, local provider sign-out and reviewed session-validity check. | 100 coordinated logout/refresh races: each logout either confirms revocation with old reference rejected or reports unavailable; zero false-success logouts and zero revoked-reference resurrection. Same-account and different-account realm logout independence; provider outage fails according to explicit policy. No blind refresh retry. |
| **4 — Secrets and HTTPS** | Exact host/proxy/root settings, cookie names/deletion attributes, DB certificate validation, current keyring delivery/retirement and secret access review. | Correct Secure/HttpOnly/Lax/Path/host-only cookies in a real browser; forged host/proxy headers denied; old/duplicate/swapped cookies gain no authority; no exposed DB tables/secrets; current-control/old-key rollback drill rejected. |
| **5 — Capacity and operations** | Selected plan/region, post-fork pools, external cleanup scheduling, expiry/quotas, alerts and retained evidence. | At most four session client connections for the initial two-worker design; no workers share inherited pools. Suggested launch test: 5 requests/s, up to 10 concurrent clients for 15 minutes, p95 protected read under 2 s, no OOM/unbounded backlog, at least 25% RAM headroom. Targets must be explicitly approved; they are not measured hosted results. Quotas/outages deny safely and revocation is available at admission capacity. |
| **6 — Workflow and business regression** | Full local suites plus staging browser/API acceptance, exclusively synthetic data/approved disposable Draft. | Both login orders, independent logout/expiry, CSRF, PKCE/reset/email verification, nonmember denial, Admin B attribution pass across workers. Photo/Environment/publication/audit contracts unchanged; all pre-existing production data preserved. No production mutation test without separate scope approval. |
| **7 — Recovery rehearsal** | One complete supported backup restore and compatible code/config rollback rehearsal, plus expiry/replay, provider/DB outages and worker restart. | All pre-recovery User/Admin cookies/workflow grants rejected after uncertain recovery; new independent logins work; no old worker/origin can serve; provider-validity policy passes; business/Storage restoration checked separately; missed/interrupted step keeps admission closed. Repeat 2N's two unsafe cases with real enforcement, not a mocked always-VERIFIED provider. |
| **8 — Release authorization** | Frozen build/config/schema fingerprints, operator ownership/budget, runbooks, acceptance evidence, compatible rollback artifact and review of all eight gates. | All mandatory criteria PASS with no unresolved security finding. Separate explicit approval before SQL/activation/deployment or any startup-safeguard change. |

**Mandatory blockers now:** package 1's absent independent recovery enforcement; no production recovery provider/integration; incomplete neutral wiring; logout-conflict handling; provider-validity/sign-out semantics; real TLS/host/proxy/secrets/grants; hosted resource/cleanup limits; and no accepted rollout/restore evidence. These are not optional because the site is a capstone.

**Optional unless requirements change:** extra Render workspace features, custom domain, PITR instead of approved daily-backup RPO, multiple app instances/automatic failover, more than two workers, external SIEM, autoscaling and independent custom authority service. MFA for deploy/restore owners, correct CSRF, current Admin membership, encrypted credentials and fail-closed recovery are mandatory. Additional Admin-user MFA is recommended hardening unless the access policy makes it a launch requirement. Do not purchase optional complexity to conceal a failed mandatory gate.

## 8. Updated eight production gates and final decision

| Gate | Status today | Closure evidence |
| --- | --- | --- |
| G04 HTTPS/hosts/proxy | **FAIL** | Package 4 plus actual hosted browser acceptance. |
| G06 Keys/secrets | **FAIL** | Protected current secret delivery, retirement and predecessor-config denial, packages 1/4/7. |
| G12 Startup/readiness | **FAIL** | Real PG/recovery wiring and fail-closed launcher, package 2; existing refusal remains intact. |
| G13 Multiworker/recovery | **FAIL** | Real Flask workers, bounded conflicts, restart/rollout/recovery acceptance, packages 2/3/6/7. |
| G14 Durable revocation | **FAIL** | Neither unsafe recovery scenario is closed by current infrastructure. Package 1 must establish the boundary; packages 3/7 must prove it. |
| G17 Operations | **FAIL** | Actual approved plans/credentials/limits/cleanup/monitoring/recovery owners, packages 1/4/5. |
| G18 Faults/SLOs | **FAIL** | Hosted timeout/resource/outage/commit-uncertainty evidence and supported provider recovery semantics, packages 1/3/5/7. |
| G20 Rollout/rollback | **FAIL** | Compatible current-config rollback, closed restoration and separate release approval, packages 7/8. |

The final architecture choice is **paid Render + Supabase Pro + one PostgreSQL session store + existing Auth/Storage**, conditional on enforceable maintenance recovery. It offers the least additional infrastructure while reusing the working local contracts. It is not yet supportable as a secure public authenticated deployment with the evidence available. The immediately supported recommendation is therefore a **local, loopback-only demonstration using synthetic accounts/data, no production Admin authority or production secrets, and deliberate fresh logins after uncertainty**. No public tunnel is implied.

No new security tests or hosted experiments were needed to reach this decision: 2M/2N already demonstrate the failure and conditional mitigation. This phase reviewed their evidence, current source integration points and official provider documentation, and performed offline preservation checks only. No adapter activation, production SQL/Auth/Storage changes, startup-safeguard changes, staging, commit, push or deployment occurred. Stop pending approval.

Offline verification confirms 22 prior source/test/dependency fingerprints, three SQL contract fingerprints and 35 recorded Phase 2M/2N artifacts remain unchanged. Reviewed report hashes and the eight FAIL gate decisions are recorded in `verification-summary.json`; `verify_evidence.py` reproduces these checks without importing the app or connecting to a database.
