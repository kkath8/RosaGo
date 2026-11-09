# Owner/provider recovery capability questions — not sent

Evaluation project jfaufpfzfhysqkhcdsrs only. This text contains no credentials
and requests clarification, not execution or a plan/billing change.

1. Can this project's Auth, REST/RPC, GraphQL, Storage, Realtime and token issuance
   be kept unavailable throughout an Auth/database/PITR restore, including before
   automatic service reopening? Please describe the supported mechanism and any
   tier limits. Database IP restrictions do not cover these HTTPS endpoints.
2. Can restored session/refresh state be invalidated and all prior JWT signing
   trust revoked while the services remain quarantined? Can this be verified
   before any request can mint or use a new token?
3. Does Data API disable persist across physical/logical/PITR restores, and which
   exact REST/RPC/GraphQL endpoints remain reachable while it is disabled?
4. Is there a supported synchronous session-liveness/revocation hook covering
   every authenticated Auth API request, including user/account mutation endpoints?
5. If same-project quarantine cannot be guaranteed, what supported procedure
   makes the old origin inaccessible during clean-project recovery? Paid-project
   pausing is documented as unavailable; do not assume pausing is possible.
6. What residual caches/propagation windows and API paths must be included in a
   separately approved synthetic acceptance test? Rotation without revocation
   and restored refresh tokens are part of the threat model.

No support message was sent by the assistant. No resource or credential action
is authorized by these questions, and no provider guarantee has been established.
