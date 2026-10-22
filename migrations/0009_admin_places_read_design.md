# 0009: Admin Places reads — not applied

Apply only after separate review and authorization. Keep 0001–0008 immutable.
Deploy this application's all-status dashboard/list only after 0009 is applied:
before that, successful queries can silently return only published rows under
0002. A successful query alone cannot detect whether the new policy exists.

0002 already grants SELECT to authenticated. 0009 adds only one permissive
SELECT policy; no new grants, writes, RPCs, or membership changes are needed.
The existing published-only policy remains in force. Effective policy OR:

| Identity | Published | Draft/archived |
| --- | --- | --- |
| anon | yes | no (new policy does not apply) |
| authenticated non-member | yes | no (predicate false) |
| authenticated member | yes | yes (predicate true) |
| revoked member, subsequent statement | yes | no |

The policy calls 0008's zero-argument SECURITY INVOKER predicate, which reads
admin_memberships with the caller's SELECT grant and own-row RLS. That policy
uses auth.uid() directly and never queries places: there is no recursion.
Membership enumeration and mutation remain forbidden. No application role gets
Places INSERT/UPDATE/DELETE. The Flask Admin boundary additionally denies
non-members access to Admin pages, even though they can read published Places.

Counts use four HEAD requests with Prefer: count=exact, projecting only id and
requesting no row bodies. Missing/invalid counts produce an unavailable state,
not zero. Each count is exact for its own statement; concurrent writes can make
cards momentarily disagree. A snapshot-consistent aggregate would require a
separately reviewed query/RPC design, outside this minimal policy migration.
Listing projects only displayed fields plus slug for ordering/test disclosure;
pages contain at most 25 records, ordered by unique slug. A full last page can
offer Next leading to an empty page. Offset pagination can shift under writes.

Static tests and mocked SDK HTTP tests do not prove live RLS. Before deployment,
run isolated PostgreSQL tests for anon, two normal identities, an Admin, and a
revoked Admin; verify full-table and filtered reads, predicate privileges, no
membership enumeration, and denied INSERT/UPDATE/DELETE for all application
identities. Check actual grants/role inheritance, existing policy names and
schema ownership. Execute the migration as one transaction through the trusted
operator; unexpected existing objects must abort rather than be overwritten.
No such SQL execution or provisioning is performed in this phase.
