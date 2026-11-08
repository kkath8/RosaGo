# Production MCP diagnosis and owner export fallback

> The owner has now supplied the export. Offline validation and the current
> comparison are recorded in [PRODUCTION_CATALOG_CHANGE_SET.md](PRODUCTION_CATALOG_CHANGE_SET.md).
> No MCP reconnection success is implied, and the original export is preserved.

Reviewed 2026-11-08 (Asia/Manila). No hosted destination queries or writes ran
during this diagnosis. Existing CSV review files remain unchanged.

## Confirmed configuration

The existing `supabase` server in the owner's Codex `config.toml` contains:

```toml
[mcp_servers.supabase]
url = "https://mcp.supabase.com/mcp?project_ref=brnkigrrqdrywahvcbvc&read_only=true"
```

There is no explicit `oauth_resource` override. The evaluation server is
separate and remains unchanged. The configured URL matches the endpoint and
combined project/read-only parameters documented by
[Supabase MCP documentation](https://supabase.com/docs/guides/ai-tools/mcp).
Removing those query parameters is not an acceptable fix for this task.

Unauthenticated public discovery checks returned:

- Configured endpoint: HTTP 401 with an OAuth resource-metadata challenge.
- `/.well-known/oauth-protected-resource/mcp`: HTTP 200,
  identifying the resource as `https://mcp.supabase.com/mcp` and authorization
  server as `https://api.supabase.com`.
- The exact project-scoped discovery URL advertised by the challenge also
  returned HTTP 200. Its resource is the complete configured endpoint including
  `project_ref=brnkigrrqdrywahvcbvc&read_only=true`.
- The earlier Codex authorization request used that complete query-bearing MCP
  URL as its resource. It matches the scoped discovery document. The initial
  unscoped metadata lookup alone was insufficient to diagnose the failure.
  The owner-reported rejection is inconsistent with the advertised scoped
  resource; its internal validator cause cannot be established from these
  checks. Treat this as an unresolved OAuth interoperability issue, not a
  proven invalid endpoint or project reference.

The public endpoint responded without any project credentials or database
query. That establishes endpoint reachability, not authenticated MCP access.
The earlier CLI success message did not establish a working connection in the
chat, which subsequently returned authentication required.

[Codex configuration documentation](https://learn.chatgpt.com/docs/config-file/config-reference)
documents `mcp_servers.<id>.oauth_resource`. A one-time override to the base
resource was tested with CLI 0.166.0 without changing saved configuration.
The generated authorization request failed the check for exactly one canonical
base resource parameter. The process was terminated before browser authorization;
the authorization URL and sensitive parameters were suppressed. The override
is therefore not a qualified fix and must not be persisted based on this test.

Reconnect remains blocked on client/provider resource handling. Keep the scoped
read-only URL unchanged. A future client update or supported provider fix must
be verified first; do not switch to an unscoped endpoint, use privileged keys,
manually alter browser authorization URLs or remove read-only restrictions.

## Owner-operated fallback

This procedure reads destinations only. It does not export Auth accounts,
memberships, sessions, credentials, private tables or image bytes.

1. In your own browser, open the Supabase Dashboard and select the original
   production project. Confirm the project reference in Project Settings and
   the Dashboard address is exactly **brnkigrrqdrywahvcbvc**. Stop if it differs.
   Do not select evaluation `jfaufpfzfhysqkhcdsrs`.
2. Open SQL Editor, create a new query, and use its existing `postgres` role.
   Do not change any grants, Auth settings or database configuration.
3. In VS Code open
   `local_catalog/export_production_places.readonly.sql`. Copy the entire file
   into that SQL Editor query. It begins a repeatable-read, read-only
   transaction, selects all 20 expected public destination columns without a
   status filter or LIMIT, produces one JSON cell, and ends with ROLLBACK.
   Run the entire file. It cannot persist data changes.
4. Stop on any error, warning, missing column, unexpected target or unexpected
   output. Do not alter or rerun the query to hide the discrepancy. Report the
   non-sensitive error for review.
5. Select the result from the SELECT statement and copy the complete
   `destination_inventory_json` cell. Save the cell's JSON value as UTF-8 to
   **local_catalog/production-destinations-owner-export.json**. Do not save the
   SQL text, a screenshot, a truncated preview or a CSV-escaped JSON cell. If
   the Dashboard offers Download JSON, it may wrap the cell in a one-row array;
   preserve that output and report the wrapper instead of editing records.
6. Confirm the copied object has `transaction_read_only` equal to `on`,
   `row_security_active_for_export_role` equal to `false`,
   `unexpected_status_count` equal to `0`, and `row_count` equal to the sum of
   published/draft/archived counts and the length of `rows`. Zero rows in a
   status is valid. RLS active for the export role would make completeness
   unqualified: stop rather than exporting only visible published records.
7. Tell Codex the file is saved and that you independently confirmed the
   Dashboard target. Codex must validate the JSON, complete row count, identity
   uniqueness, field inventory and source hashes before comparing with all 98
   CSV places. The target literal in the SQL is an owner attestation, not a
   database-derived project identity check.

The output path is a production review artifact, not an input for the
evaluation-pinned `local_destination_catalog init/plan` commands. Do not change
that manifest or relabel the export to bypass its target checks. No records
will be updated, created, archived or published from this export procedure.

The current [publication review](PUBLICATION_REVIEW.md) and historical
[candidate comparison](production-publication-review-v2.json) remain preserved.
Current match/new/missing counts cannot be finalized until this complete
inventory is validated. Remote deployment remains **NO-GO**.
