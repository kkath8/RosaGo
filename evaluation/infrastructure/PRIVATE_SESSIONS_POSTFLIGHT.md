# Private session SQL — hosted read-only postflight PASS

Evaluation project `jfaufpfzfhysqkhcdsrs`; verified 2026-11-07 using only
`supabase-evaluation`. The owner reported one successful SQL Editor execution.
The verifier executed only SELECT queries, as `supabase_read_only_user` with
`transaction_read_only=on`. Production was not accessed.

Applied file: `sql/private_sessions.review.sql`, approved SHA-256
`59899c43c3d3bfe232b9b91e87b979a3fa3338e2dd8ed7d070768fc6b05555ea`.
Local bytes still match. Do not rerun the file.

## Verified result

- `rosago_session_app`: NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE,
  NOINHERIT, NOREPLICATION, NOBYPASSRLS. It inherits no other roles.
- The sole membership is postgres with ADMIN OPTION and without INHERIT/SET,
  the expected PostgreSQL creator-management grant. No API role or application
  account receives membership or the ability to assume the new role.
- Schema `rosago_session` and sole table `payloads` are owned by postgres.
- Exactly three NOT NULL columns, with no defaults: key/text, ciphertext/bytea,
  expires/double precision.
- Four validated constraints: key primary key, exact scoped/hashed key regex,
  ciphertext size 1..45000, finite positive expiry.
- Two valid, ready indexes: payloads_pkey and payloads_expiry.
- RLS enabled AND forced. Exactly one private policy, session_payload_role:
  PERMISSIVE ALL TO rosago_session_app, USING true, WITH CHECK true.
- Runtime role has schema USAGE and table SELECT/INSERT/UPDATE/DELETE only;
  no schema CREATE, table TRUNCATE or TRIGGER. No table grants in public/Auth/Storage.
- PUBLIC has no private schema/table ACL entries. anon/authenticated/service_role
  all have no schema USAGE/CREATE, no tested table DML/TRUNCATE/TRIGGER access,
  and cannot SET ROLE rosago_session_app. Ordinary Users and application Admins
  therefore have no direct private-session access.
- No private functions or application triggers were created.
- Exactly zero payload rows. The inspector was not filtered by RLS, so this
  count establishes emptiness rather than merely no visible rows. No ciphertext,
  credentials, passwords, tokens or cookies were retrieved. Empty storage does
  not exercise encryption or qualify a running session service.

## Preserved baseline

- Two Auth accounts and two profiles, with the same verified UUIDs.
- Ordinary User 3c572202-c1da-4e5a-aa20-d89be25b2d9f has its profile and no membership.
- Admin 4bc67593-c979-4441-b42a-99b6d3da2885 has its profile and the sole membership.
- Zero provider sessions; no sign-in performed.
- Exactly two destinations. Every field in the approved, hash-verified seed
  payload still matches, including Published Garden and Draft destination.
- All 15 migration versions/names, 20261107000101..20261107000115, match baseline.
- Original 17 public policies remain; the new provider policies count is zero.
- Existing nine definer functions retain their reviewed body hashes, postgres
  owners, empty search paths and execution ACLs, including seven authenticated
  entrypoints and the two private functions.

Account preservation verification covers counts, identities, profile existence
and Admin membership. Auth credential/private account fields were not inspected.
The installed DDL contains no account/profile/membership/destination/migration DML.

## Stage boundary

First script passes. `provider_access_guards.review.sql` is still unapplied:
its helper function and nine restrictive policies are absent. Its owner-operated
application is already separately approved and may now proceed using the existing
hash-verifying clipboard procedure, followed by read-only postflight.

No role login, password, secret, account, seed, Auth/Storage setting, paid service,
deployment, commit or push was created or changed by the verifier. Existing
deployment/security gates remain, including Auth database restore/JWT replay.
