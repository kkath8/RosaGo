# User login CSRF regression — fixed locally

The User login failure was reproduced before the application change, using the
current Flask application in a synthetic fixture and installed Edge in a fresh
temporary profile. No existing running application, real account credentials,
hosted project, live Supabase authentication or database operation was used.

## Exact cause and stage

The message is rendered by the POST `/login` branch in app.py after
`validate_user_login_csrf()` returns false. The validator in user_csrf.py requires
the exact same-origin Origin header before checking/consuming the challenge.

The shared security-header code applied `Referrer-Policy: no-referrer` to `/login`.
Browsers consequently send `Origin: null` for its native HTML form POST, even
with a correct CSRF cookie and hidden form token. That request fails before
email/password validation or the Supabase password-login adapter.

There was already a same-origin response-policy exception for password reset,
email verification and profile-edit forms, with a comment explaining this browser
behavior. Login, registration and forgot-password forms were missing from it.
This was a regression in the shared response-header hardening, not a provider
authentication failure or a missing session-service prerequisite.

Browser evidence before the fix:

- GET/login initialized and login.js client validation worked.
- An empty UI submission was stopped by JavaScript without making a POST.
- An intentionally empty native form submission, bypassing JS only to examine
  HTTP admission, had a matching cookie/token but Origin:null and received 403
  with the exact reported message.
- Provider calls: zero.

After the fix, the same native submission sends the exact Origin, passes CSRF,
and receives the expected 400 missing-fields validation response. It does not
authenticate or call a provider. Actual account sign-in was not exercised.

[Fetch Origin algorithm](https://fetch.spec.whatwg.org/#append-a-request-origin-header),
[MDN referrer policy/Origin behavior](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy).

## Frontend, Admin and configuration findings

- User login loads static/js/login.js. It performs field validation and a native
  form submission. It neither creates this backend error nor sends a Supabase
  authentication request directly.
- static/js/auth.js is the registration script, not the User login script.
- Admin login uses separate template/script/session state, and already sends
  same-origin referrer policy. Its empty native form posts passed CSRF and
  reached 400 field validation before and after the fix. It shares the bounded,
  purpose-bound challenge infrastructure but not the User Origin failure.
- The workspace's non-secret mode flags are unset, selecting local development;
  required Flask/Supabase settings are present. No settings or values were changed.
  A missing required secret/backend setting or an enabled production-session
  startup guard would fail initialization, not produce this particular 403.
  No keys, URLs containing credentials, passwords, cookies or CSRF values were logged.

## Minimal change and safeguards

Only application behavior changed: app.py adds `/login`, `/register` and
`/forgot-password` to the existing same-origin referrer-policy exception.

- Exact Origin checks still reject missing, null and foreign Origin.
- Cookie binding, single-use/purpose-bound CSRF challenges, rate limits, realm
  separation, session revocation and recovery/authorization rules are unchanged.
- Callback URLs `/auth/callback` and `/auth/reset-callback` retain no-referrer.
- Existing password-reset/verification form policies are unchanged.
- same-origin continues to suppress cross-origin referrers.
- Existing security SQL sources and original Linux evidence retain their hashes.
  No SQL/security scripts, hosted changes, deployment preparation, live sign-ins,
  commits or pushes were performed.

Support files added:

- tests/test_login_referrer_policy.py: header scope, cookie binding, origin
  rejection and single-use challenge regressions, with providers/network mocked.
- tools/check_login_browser.py: isolated real-browser fixture, empty forms only,
  with a deny-only proxy for non-loopback traffic and forbidden provider methods.
- broken-browser-results.json and fixed-browser-results.json: sanitized evidence;
  no credentials, cookies or tokens.

## Validation and local action

Focused offline suite: **183 tests and 259 subtests pass** across User/Admin login,
mocked authentication request handling, independent sessions, CSRF, registration,
recovery/password reset, deployment refusal and evaluation isolation.

The real-browser before/after checks both pass their expected assertions. The
new regression file passes four tests and ten subtests. No live account sign-in
is necessary to demonstrate the repaired browser/CSRF boundary; it remains untested.

Restart Flask using the existing local launch command, then reload `/login` in a
fresh GET before submitting anything. Existing documents retain the old policy,
and process-local challenges reset on restart. No .env or database changes are
required for this fix. Remote deployment remains NO-GO.
