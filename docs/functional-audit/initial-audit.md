Initial audit before implementation changes. Statuses below describe code inspection, not live service verification.

| Controls/features | Initial classification | Action |
|---|---|---|
| Header destination search | COMING SOON | Implement published-only catalog search and real GET form/results. |
| All ten navigation items, dashboard quick actions | WORKING (route inspection) | Exercise authenticated/public routes and guards. |
| Explore category/detail actions | WORKING (route inspection) | Test search/filter composition, metadata and visibility. |
| Detail Add to Trip | PARTIALLY WORKING | Clarify signed-out label and preserve destination through restricted login continuation. |
| Detail Open Map | PARTIALLY WORKING | Preserve destination selection rather than open a generic map. |
| Manual new/detail Organize / Preview | UNSUPPORTED | Remove controls and future-feature wording. |
| Login Remember me | PLACEHOLDER | Remove unsupported checkbox and notice. |
| Planner preferences/review/generate, recommendation selection, preview/edit | WORKING (route inspection) | Run lifecycle, revision, validation, expiry and deterministic-selection route tests. |
| AI explanation, conversational adjustment, assistant send/clear | PARTIALLY WORKING (external dependency) | Test provider adapters, failures/context/security; retain honest unavailable states. |
| Weather advisory/proposal Keep Current/Use Suggested | PARTIALLY WORKING (external dependency) | Test applicability, token binding, freshness and atomic decisions. |
| Trips create/read/edit/add/delete/pagination | WORKING (route inspection) | Test owner isolation and mutations. No destination-removal control exists. |
| Map markers/details/route/geolocation/external maps | PARTIALLY WORKING (external dependency) | Run route/API/JS tests including coordinate failures and safe fallbacks. |
| Transport | WORKING (implemented map/routing wrapper) | Check real controls only; no fabricated fares/schedules. |
| Alerts/preferences/profile editing | WORKING (route inspection) | Test request-driven reminders, session-only preference and name validation. |
| Registration/OTP/resend/login/recovery/reset/logout | PARTIALLY WORKING (external dependency) | Preserve security; run auth adapters/route/JS tests. No live accounts or emails created. |
| Terms/Privacy/back links | WORKING (local routes) | Exercise routes and links; no content changes. |
| Transient disabled submit/resend controls | WORKING (safety state) | Keep in-flight guards and server cooldown. |
| Disabled AI when provider unconfigured | WORKING (safe unavailable state) | Preserve safe disable/error behavior, never fake replies. |
| Input placeholder hints and synthetic-data disclosures | WORKING (honest guidance) | Keep; these are not unfinished actions. |

Full per-template control inventory: initial-controls.json. Static inventory includes conditional and macro-generated controls; dynamic cases require route/JS tests.
