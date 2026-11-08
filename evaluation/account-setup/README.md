# Synthetic User/Admin setup — preparation only

No account creation or membership grant is authorized by the preparation request.
Do not execute this procedure or the review SQL until the separate approvals below.
Use only evaluation project `jfaufpfzfhysqkhcdsrs`. Keep supabase-evaluation MCP
read-only. The production project is excluded.

## Reviewed authentication and authorization

Both identities are ordinary Supabase password accounts with the authenticated
database role. RosaGo verifies password login, JWT claims/issuer, subject/session
identity and confirmed email before creating a realm-specific local session.
An Admin login additionally checks current database membership before session
installation, then rechecks membership on protected Admin requests.

`public.admin_memberships(user_id)` is the sole Admin membership authority.
The FK points to auth.users; granted_at defaults to now(). Clients have only
own-membership SELECT access and cannot insert/update/delete membership.
`rosago_is_admin()` uses auth.uid(), not user-editable metadata. The audited Admin
mutation RPC also checks/locks current membership internally. User/Admin browser
sessions and logout authority are separate even when the same Auth identity is
used; an Admin using the normal User login still has Admin database membership
and therefore sees Draft rows through direct database access. The ordinary User
test must always use the separate nonmember identity.

## Minimal proposed accounts

| Synthetic label | Inbox | Password | Database membership |
| --- | --- | --- | --- |
| evaluation-user-001 | Owner-controlled unique test alias, selected privately | Unique password-manager-generated value | None |
| evaluation-admin-001 | A different owner-controlled test alias, selected privately | Different generated value | One explicitly approved membership row |

Do not use respondent credentials or example.invalid as a real delivery inbox.
Select two inboxes/aliases you control. Generate long unique passwords privately
(for example 24+ random characters meeting the existing provider policy) in a
password manager; retain them there. No plaintext passwords, JWTs, refresh tokens,
service secrets, recovery URLs or session cookies in chat, SQL, terminal arguments,
PowerShell history, fixtures, .env files, screenshots, HAR files or test reports.
No API secret is needed by the application for owner-dashboard provisioning.

## Approval A — exactly two synthetic Auth accounts

After approval, open the evaluation project dashboard and independently verify
the project reference in the browser URL. Recheck via read-only MCP: zero users,
profiles and memberships; exactly the two approved fictional destinations; the
reviewed Auth profile trigger and schema history still present. Stop on drift.

1. Go to Authentication → Users → Add user/Create user. Use the manual password
   creation path, not Invite user, signup, recovery or a magic link.
2. Create evaluation-user-001 with its privately selected owner-controlled alias
   and password. Individually mark this synthetic user's email confirmed using
   the account creation UI's auto-confirm option. This is part of the proposed
   account action, not a change to global confirmation/signup/SMTP settings.
3. Repeat once for evaluation-admin-001 with a different alias and password.
   Do not add role/admin metadata, assign service_role, disable confirmation
   globally or change provider settings. If manual creation/individual confirmation
   is unavailable under current settings, stop and report; do not send invitations
   or enable other Auth flows as a workaround.
4. Keep the two generated UUIDs and their inbox-to-label mapping in a private
   operator record. UUIDs alone are not secrets, but never mix up which identity
   receives membership. The read-only verifier can inspect UUID/confirmation and
   profile relationships without passwords or tokens. Stop at exactly two users
   and two trigger-created profiles, with zero memberships. Do not insert Auth
   rows or profiles through SQL or restore identity exports.

This pre-created, owner-confirmed test path does not qualify email delivery,
registration, inbox ownership verification, account recovery or a complete website.
Official references: [create a user](https://supabase.com/docs/reference/python/auth-admin-createuser)
and [Auth profile triggers](https://supabase.com/docs/guides/auth/managing-user-data).

## Approval B — membership for the intended Admin UUID only

After account postflight and a separate explicit grant approval, use the owner's
evaluation SQL Editor with trusted postgres authority. The exact elevation is:

```sql
INSERT INTO public.admin_memberships(user_id)
VALUES ('<SYNTHETIC_ADMIN_UUID>'::uuid);
```

Use the guarded transaction in `grant_admin_membership.review.sql`, replacing
only its two UUID placeholders with the dashboard-verified synthetic identities.
That transaction requires distinct, confirmed users, exactly two Auth users and
profiles, and zero existing memberships; it inserts only the Admin row. Do not
put a password/email/token in it or add any SQL GRANT, schema/policy modification,
self-service role assignment, ON CONFLICT override or User membership.

Verify through read-only MCP: exactly one membership for the Admin UUID, none for
the User; both profiles belong to their Auth UUIDs; destinations and schema
history remain unchanged. Stop on any error or unexpected account/membership.

## Focused acceptance after a separately approved live-test window

`ACCEPTANCE.md` defines expected results, allowed side effects and release gates.
Local mock login and disposable-PostgreSQL checks can run now. Hosted password
sign-in creates provider sessions and is not a read-only MCP operation; it needs
explicit test approval. Do not run the application in development/redis-local
mode or expose a listener to bypass the production startup refusal. Real local
User/Admin login through a production profile remains blocked until its session
backend and protected authority are implemented and qualified.

No live test requests, Auth accounts, grants, mail, hosted configuration, new
infrastructure/secrets, deployment, commit or push are included in preparation.
