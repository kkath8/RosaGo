# Provider-session follow-up during local image integration

2026-11-08 — Source review and synthetic tests only; no hosted contact or auth
changes. **Auth restore/replay remains unresolved. Remote deployment is NO-GO.**

The installed evaluation SQL helper checks the caller's session identity against
`auth.sessions`, including `not_after`. Restoring a previously deleted session
row can therefore make a still-unexpired JWT satisfy that database test again.
An independently revoked web session does not, by itself, prevent direct
Supabase Data API replay of that JWT. No image or catalog change addresses this.

The supplied production schema export lacks that evaluation helper/guards.
Do not confuse the projects or install evaluation SQL on production implicitly.

The inactive `server_data_gateway.py` candidate resolves independent session
state for every operation, constrains database roles and fails closed. It is
evaluation-issuer-bound; its current RPC allowlist also does not include the
new location-verification RPC. It is not activated, does not close hosted Data
API access itself, and does not protect Auth endpoints. Activating or repointing
it is not a safe image-integration shortcut.

The 7 existing `test_provider_session_check.py` tests passed as part of the
100-test offline regression run: exact caller/realm checking before access,
revocation on the next request, unknown/outage/malformed failure, unknown handle
rejection, uncertain local revoke handling, no refresh/activity renewal when
provider state is unknown, and closed production startup. These prove admission
behavior using synthetic booleans, not real provider revocation or restore safety.

Next security work must qualify an end-to-end architecture that prevents raw
JWT bypass: either an independently durable authority enforced on every exposed
data/RPC path, or a restricted server-only data path with direct bypass actually
closed. Auth refresh/logout/restore behavior, authority rollback fencing,
credentials, worker/restart handling and HTTPS/proxy configuration must also be
qualified. Any hosted configuration, SQL or infrastructure change requires a
separately reviewed package and explicit approval. Existing guards remain in place.
