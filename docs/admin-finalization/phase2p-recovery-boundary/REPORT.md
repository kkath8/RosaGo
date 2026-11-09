# Phase 2P — Work Package 1: Recovery Boundary Qualification

Reviewed 2026-11-05. Controlling scope: [Phase 2O, Work Package 1](../phase2o-deployment-decision/REPORT.md).

**Work Package 1: FAIL. Work Package 2: NO-GO.** The proposed paid Render/Supabase architecture has a documented public-maintenance control, but no qualified end-to-end recovery authority/interlock. Fresh local qualification reproduced both revoked-session resurrection scenarios. Declared recovery safely forces reauthentication only while the test controller is current and admission is assumed closed. This does not meet Work Package 1's pre-use enforcement requirement.

Stop the public-release path here and recommend the constrained local demonstration. This is an evidence-based qualification failure, not proof that Render/Supabase can never support a controlled solution. No separately authorized hosted qualification was available, and none was provisioned. Packages 2–8 are unchanged and were not started.

## 1. Exact scope and proposed recovery authority

Work Package 1's deliverable is to name the actual admission/restore/release controls, protected current record, authorized operators and provider recovery semantics; obtain entitlements/cost and approve supported threats. Its controlling acceptance criterion is:

> In isolated staging, every *permitted* DB import/restore and predecessor environment/build rollback is closed before first stale-authority use. DB+environment rollback cannot reopen. Missing/inconsistent control remains closed. Unsupported silent/correlated rollback is explicitly rejected, not declared solved. **No feasible enforcement means FAIL and local-only.**

The evaluated mechanism remains **independently controlled maintenance plus transaction-safe global session invalidation**, not another database, Redis/witness stack or custom always-running service:

| Component | Concrete candidate / current status |
| --- | --- |
| Public admission | Native Render **Maintenance Mode** on the paid web service. Documented capability; not enabled or tested on a hosted service. |
| Private admission and request drain | Operator-controlled stop/drain of every predecessor worker, private caller and DB connection. No qualified implementation or complete origin/service inventory. |
| Current recovery authorization | Protected current recovery record outside both Supabase restore and predecessor Render build/environment. Must contain current incarnation, both realm epochs, compatible release/key set and CLOSED/OPEN status. No independently protected production record/source is supplied. |
| State invalidation | Existing isolated PostgreSQL transaction clears private session/workflow state and installs fresh epochs in QUALIFYING state. Tested locally; no production schema or runtime integration. |
| Restore/release permissions | Separate privileged recovery credentials, restricted routine access, explicit reopen authorization. Provider capabilities reviewed; actual accounts, roles and bypass permissions not inspected. |
| Runtime verification | Existing `RecoveryFence` requires a current trusted provider and matching SQL gate. Only a local test controller exists; missing provider fails closed. |

Render documents that Maintenance Mode applies to paid web services and returns a maintenance response to public requests; the process remains running, reachable privately and through SSH. Consequently it is a credible public gate, but not proof of worker termination or closure of every path. A separate test must verify default/custom hostnames, callbacks, private callers and any old service. [Render Maintenance Mode](https://render.com/docs/maintenance-mode).

A protected offline ledger is useful for recovery ownership, but cannot by itself serve as live `RecoveryAuthority` or detect a restore under a running worker. Do not plug in an always-VERIFIED provider or call a signed predecessor manifest current. Work Package 1 has not established a trustworthy provider/control implementation for Work Package 2 to integrate.

## 2. Trust-boundary analysis

The current recovery decision must survive **outside the joint rollback boundary** of PostgreSQL, Render code/configuration and old session encryption keys. It also must control whether any worker can use restored data. Independence of location without knowledge/enforcement of recovery is insufficient.

| Operation | Qualified local outcome | Missing hosted guarantee |
| --- | --- | --- |
| Database restore while controller remains incorrectly VERIFIED at the same epoch | Revoked authority returns. | Detection/interlock before any restored record is used. |
| Database restore while independent current controller is CLOSED | Requests denied. | Actual provider/control-plane admission, private drain and inability to bypass closure. |
| Current controller advances, SQL epoch rolls back | Old gate rejected. | Protected current controller persistence and fresh delivery across workers. |
| Current controller advances, Render-like old binding/config returns | Old worker rejected. | Real Render rollback behavior, override precedence and compatible-release enforcement. |
| Database + environment + controller/key rollback | Fresh worker accepts revoked authority. | Current recovery control must not roll back with those stores; missing/inconsistent control must remain closed. |

Render rollback reuses the target build, start command and service environment values. Environment-group values are not themselves reverted, but group attachment can change. The reviewed rollback documentation does not establish Maintenance Mode persistence/interlocking across all rollback or Blueprint paths. That interaction is **unqualified**, not assumed unsafe or safe. [Render rollbacks](https://render.com/docs/rollbacks).

Supabase documents project downtime during restoration and replacement with older database state. This does not promise an application invalidation callback or a hold-until-application-approved reopening. Automatic reconnection can read stale authority after the project returns. Daily-backup custom-role password handling is not a universal barrier for logical imports or all recovery methods. [Supabase backups](https://supabase.com/docs/guides/platform/backups).

A failed health check is not equivalent to closed admission: routing/termination has transition periods and existing instances can continue serving. It must not be the sole restore fence. [Render health checks](https://render.com/docs/health-checks).

Supported controlled recovery would trust provider control planes and named recovery owners, while excluding neither ordinary operator mistakes nor accidental old configuration. A compromised owner able to restore every supposedly independent control is beyond what this application alone can distinguish. No unapproved exclusion of the existing rollback cases, or weaker threat-model approval, was used to award PASS.

## 3. Fresh isolated qualification and results

New `qualify_boundary.py` reruns the unchanged Phase 2N drill and writes **fresh Phase 2P evidence** here. It reuses the owned loopback PostgreSQL 17.11 fixture, not Render or Supabase. The underlying test source hash is recorded. No new session architecture or production authority implementation was introduced.

Fixture image: `postgres@sha256:653186fe15006c099d2fb3bc1d8461c1dee9d036c43f2e5fdaf4f22e5e601876`. Only `127.0.0.1:16432` is published. The reused fixture retains its original `rosago-phase2m-postgres` name and phase `2m` ownership label. Generated credentials are temporary; dumps remain in memory. ID/label/port-checked removal deletes its container/anonymous volume and temporary credential directory.

**Results: 30 assertions satisfied, including four deliberate unsafe counterexample assertions. This is not 30 secure recovery gates.** The existing PostgreSQL/Flask regression passed **39 tests and 21 subtests in 31.47 seconds**. Evidence: [security-results.json](security-results.json), [qualification-output.txt](qualification-output.txt), [focused-output.txt](focused-output.txt), [focused-test-results.xml](focused-test-results.xml).

| Test family | Observed outcome / security assessment |
| --- | --- |
| Ordinary logout and old reference replay | Revoked reference rejected. |
| User logout, Admin still active; Admin logout, User still active | Realm isolation preserved. |
| Two-process refresh/logout and subsequent reads | Confirmed revocation rejects User reference; Admin remains valid. Drill-only bounded fresh-CAS revoke retry is used, not a new application correction. |
| Fresh worker restart, unchanged current authority | Both realm sessions remain valid until their deadlines. |
| Missing provider, unavailable provider, stale timestamp, UNKNOWN freshness | Rejected/unavailable; no fallback. |
| **Complete private PostgreSQL schema restore, unchanged old-epoch VERIFIED controller/config/key** | **UNSAFE: previously revoked session resolves. Primary failure 1 reproduced.** |
| Drop predecessor decryption key | Old ciphertext rejected; conditional on that key not returning elsewhere. |
| Change write key but retain predecessor decryption key | **Unsafe invalidation control:** restored authority still resolves. |
| Read overlaps recovery closure | Post-operation recovery check denies the result. Does not recall a business operation already dispatched. |
| Explicit closed recovery and injected interruption before commit | Requests remain closed; SQL invalidation rolls back atomically. |
| Immediate predecessor epoch reuse | Rejected. No durable global never-reuse registry is implemented. |
| Committed invalidation, QUALIFYING gate | All private namespace state cleared; gate not open. |
| New epochs reopened with current controller | Old workers denied; both realms require fresh logins; new independent logins resolve across processes. |
| DB epoch rollback or predecessor environment against current controller | Denied. |
| DB plus predecessor environment against current controller | Denied; matching old SQL/config cannot override current control. |
| **DB/config/key plus test-controller rollback, fresh worker** | **UNSAFE: previously revoked session resolves. Primary failure 2 reproduced.** |
| Lower proof revision with surviving worker | Denied by its memory floor. |
| Restart worker with lowered controller revision | **Unsafe durable-freshness control:** no surviving revision floor. |

The two primary failures require unexpired restored payloads, matching old epochs/configuration and usable old encryption authority. The restored SQL gate/version rows/tombstone history agree internally; a controller incorrectly reporting the old state as VERIFIED answers fresh nonces. No new provider nonce or hash can reconstruct missing revocation history. Full provider Auth validity was not tested by these synthetic credentials; the observed violation is return of revoked application authority.

The regression suite preserves CSRF separation, login orders, expiry, recovery/reset/email flows, unauthorized Admin denial and mocked B-attribution contracts. It repeats inherited store cases, so counts overlap. Separate-process tests qualify backend sharing; the Flask fixture is two app instances, not a hosted multiworker deployment. This is preservation evidence only, **not implementation or completion of Packages 2 or 3**. In particular, the Package 3 100-race criterion was not undertaken, and application logout-conflict handling remains unchanged.

Full Python/JavaScript/browser regressions were not rerun because runtime and existing tests were unchanged. Their historical Phase 2M results are not relabeled as new Phase 2P results.

## 4. Supabase Auth's authoritative contribution and limits

A validated JWT identifies a provider subject/session, but signature validation alone does not prove immediate revocation. Supabase documents checking whether the token's `session_id` remains in `auth.sessions` after sign-out. That can reject an application-only restored session **if provider revocation succeeded and Auth remains current**. Provider unavailability must not be treated as valid. An arbitrary user/profile lookup is not a tested substitute. [Supabase sessions](https://supabase.com/docs/guides/auth/sessions).

For normal independent logout, provider local scope matters; global scope can revoke other sessions of the same account. Supabase also documents that revoked-session access tokens remain valid until expiry unless stronger current-state enforcement is applied. These are provider semantics, not tested live behavior in this phase. [Supabase sign-out scopes](https://supabase.com/docs/guides/auth/signout).

Auth is not an external rollback anchor when its state is restored with the same Supabase project. JWTs, Auth session rows and application rows can all agree on predecessor authority. Nor does closing Render automatically revoke provider tokens usable directly at Supabase endpoints. Work Package 1 must account for that access boundary; exact provider-check enforcement belongs to the existing Package 3, not a new package or an implementation here. No Auth SQL access, grants, policies, signing-key changes or real sign-out calls were performed.

## 5. Required infrastructure and operations; local versus hosted evidence

These are **qualification requirements within Package 1**, not provisioning instructions executed here:

| Control/evidence | Locally testable | Separately authorized isolated infrastructure needed |
| --- | --- | --- |
| Transactional clear/new epochs, closed/qualifying states and interruption | Demonstrated with real PostgreSQL. | Actual Supabase schema/role/transaction compatibility and permitted restore variants. |
| Current/stale/missing recovery proofs | Conditional contract behavior demonstrated. | Name and protect the actual current record/source, recovery owner and release approvals; qualify its restore/rollback behavior. |
| Public admission | Render native paid Maintenance Mode is documented; not simulated as provider evidence. | Verify 503/denial on every default/custom origin/callback before restore, including cached/old deployments; prove recovery cannot inadvertently reopen it. |
| Private callers and old workers | In-flight adapter post-check demonstrated. | Drain/terminate workers and DB connections; restrict private-network/SSH callers and old credentials; verify no late business write. |
| Rollback | Old bindings and complete local SQL restores tested. | Real Render build/env/group/Blueprint interactions, manual/API deploy permissions, disabled unwanted autodeploy/hooks and compatible-release allowlist. |
| Privileges | Existing restricted lab SQL role denial tests pass. | Inventory all Supabase Dashboard/SQL/import/Management API paths and actual authorized operators; no runtime restore/admin credentials. |
| Provider-managed recovery | Not reproducible as managed Supabase behavior locally. | Obtain supported recovery/durability semantics and verify pre-use hold/reopen behavior or equivalent current authorization. No undocumented guarantee. |
| Provider Auth revocation | Documentation review and mocked application workflows only. | Provider session checks/local sign-out, outage behavior and whole-project restore impact with isolated synthetic accounts. |

The proposed layout remains paid Render + Supabase Pro + one PostgreSQL store. Native paid Maintenance Mode is a documented entitlement; the actual service, restrictions and persistent control record are unqualified. No service was ordered and no cost incurred. Do not assume Supabase Pro includes every least-privilege/team control: Read-Only/No-access and project-scoped roles are documented as Team/Enterprise features. A role named Developer is not automatically incapable of importing data; actual SQL/API permissions must be inventoried. [Supabase access control](https://supabase.com/docs/guides/platform/access-control).

A feasible recovery sequence would close native public admission and private use first, verify predecessor workers/connections are retired, restore while closed, issue current never-used epochs, invalidate both realms transactionally, verify current secrets/release/provider authority and then explicitly reopen. The unresolved parts are reliable enforcement of that sequence, protected current authority and detection/handling of operations outside it. A local script's success does not establish the cross-provider interlock.

Do not add a witness/service, purchase a higher tier or alter the eight packages by inference. A future infrastructure qualification would need separately approved scope, entitlements and credentials. This phase makes no claim that platform capabilities are fundamentally insufficient; it establishes that the required boundary **is not qualified with the currently available evidence and authorized infrastructure**.

## 6. Work Package 1 acceptance status

| Controlling requirement | Status | Evidence / blocker |
| --- | --- | --- |
| Name actual admission/restore/release controls, current record and operators | **FAIL** | Native public gate identified; current protected authority, real operator permissions and complete interlock absent. |
| Obtain entitlements/cost and approve supported threats | **FAIL** | Public documentation only; no account-specific verification or approved exclusion of silent/correlated rollback. No paid provisioning permitted. |
| Every permitted import/restore and predecessor build/env rollback closed before first stale-authority use | **FAIL** | Local positive sequence assumes closure. Undeclared restore still returns revoked authority; real pre-use closure not qualified. |
| DB+environment rollback cannot reopen authority | **FAIL** | Current test controller blocks it, but correlated predecessor controller/config accepts it; no independently protected production control. |
| Missing/inconsistent recovery control stays closed | **PASS — local contract only** | Missing/unavailable/stale/UNKNOWN proofs denied. A stale internally consistent controller remains an explicit unsafe case. No production gate closed by this subtest. |
| Revoked sessions never valid after supported recovery | **FAIL** | Conditional declared recovery passes, but proposed platform recovery paths/interlock unqualified and both unsafe cases reproduced. |
| Stale epochs never silently authorize | **FAIL** | Current-controller mismatch rejected; matching restored epoch/controller accepted. |
| Independent User/Admin sessions | **PASS — local behavior only** | Both logout directions and post-recovery fresh logins preserved. |
| Recovery uncertainty denies or requires reauthentication | **FAIL overall; local declared-uncertainty path passes** | Explicit BLOCKED/UNKNOWN rejects and new epochs require login; undetected stale controller still falsely attests freshness. |
| Unsupported silent/correlated rollback explicitly rejected, not declared solved | **FAIL enforcement; reporting satisfied** | Unsafe cases documented as blockers; no platform enforcement demonstrated that keeps them closed. Merely labeling them unsupported is insufficient. |

**Overall Package 1: FAIL.** No local PASS above is promoted to production readiness. Work Package 1's stop condition applies; do not start Work Package 2.

## 7. Updated eight production gates

| Gate | Status | Reason retained |
| --- | --- | --- |
| G04 HTTPS/hosts/proxy | **FAIL** | No hosted origin/proxy/browser or complete admission-path qualification. |
| G06 Keys/secrets | **FAIL** | No protected current authority/secret delivery and predecessor key/config retirement evidence. |
| G12 Startup/readiness | **FAIL** | Existing safeguard intact; no qualified production recovery provider. Package 2 not started. |
| G13 Multiworker/recovery | **FAIL** | Local sharing/isolation pass; real worker drain/recovery consistency unqualified. |
| G14 Durable revocation | **FAIL** | Both resurrection cases reproduced; independent pre-use recovery boundary missing. |
| G17 Operations | **FAIL** | Actual restore permissions, operator ownership and complete interlock/entitlements unqualified. |
| G18 Faults/SLOs | **FAIL** | No hosted provider recovery guarantees or qualified uncertainty boundary. Other package work remains unchanged. |
| G20 Rollout/rollback | **FAIL** | No verified current-config rollback/reopen enforcement across real control planes. |

## 8. Final decision and preservation

**NO-GO for Work Package 2 or public deployment. Recommend the constrained local demonstration path:** loopback-only, synthetic accounts/data, no production Admin authority, no production secrets or public tunnel, and deliberate fresh login after uncertainty. Keep the working RosaGo implementation and the inactive PostgreSQL candidate unchanged. Do not start another experimental architecture or expand Packages 2–8.

Added artifacts only: this report, `qualify_boundary.py`, `verify_evidence.py`, fresh `security-results.json`, qualification/focused output, pytest XML and `verification-summary.json`. Existing source, tests, SQL and prior report/evidence files are preserved. No production request/SQL/Auth/Storage change, paid provisioning, deployment, staging, commit or push occurred. The reused owned fixture and temporary credentials were cleaned up. Stop pending approval.
