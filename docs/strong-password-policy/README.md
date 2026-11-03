# Strong password policy

Previous application policy: at least eight characters and not entirely whitespace.

New policy for both registration and password reset:

- At least eight Unicode characters.
- At least one ASCII uppercase letter A–Z.
- At least one ASCII lowercase letter a–z.
- At least one ASCII digit 0–9.
- At least one printable ASCII punctuation character, including `! @ # $ %`, quotes, underscore, brackets, backslash and other normal punctuation. Spaces and emoji do not satisfy this requirement.
- Password and confirmation must match.

Passwords are validated without trimming, normalizing or changing the value sent to Supabase. Login remains unchanged, so existing credentials are not rejected by the new-password creation policy.

`password_policy.py` defines the ordered requirements, user-facing labels and messages. Both Flask routes call its validator before a provider request. The same public rules are serialized into a shared Jinja partial and evaluated by `static/js/password-policy.js` on both pages. This avoids independently maintained registration/reset policies. Length is counted as Unicode code points in both runtimes.

The shared five-row checklist is visible before submission and updates each requirement independently while typing or submitting. Circles/checkmarks and Not met/Met text communicate state without relying on color. Existing layout is retained; checklist CSS is scoped to registration/reset forms. Both server routes render policy and confirmation failures beside the appropriate field. Confirmation mismatch reads exactly `Passwords do not match.` Registration consent-only behavior remains a single local error without a generic duplicate message. Provider/security errors retain the existing status area.

Reset policy validation runs after the existing recovery authorization, CSRF and origin checks, and before reserving the one-use grant or constructing a Supabase client. A weak password does not consume the grant. A valid successful reset still performs the existing `set_session`/`update_user`, consumes the grant, and redirects to login. PKCE, authorization, concurrency, replay handling and ambiguous-write protections were not rewritten.

Implementation files changed/added:

- `password_policy.py` (new): canonical local policy and server validator.
- `app.py`: policy access in templates, registration enforcement and reset enforcement/local field errors.
- `templates/auth/password_policy.html` (new): shared checklist and serialized public rules.
- `templates/auth/register.html`, `templates/auth/reset_password.html`: shared partial/script and associated reset field errors.
- `static/js/password-policy.js` (new): shared local rule evaluation and checklist state.
- `static/js/auth.js`, `static/js/reset-password.js`: invoke the shared policy and preserve existing submission paths.
- `static/css/auth.css`: extend existing checklist styling to the reset form.

Test files changed/added:

- `tests/test_registration_validation.py`
- `tests/test_password_reset.py`
- `tests/test_strong_password_policy.py` (new)
- `tests/test_registration_frontend.js`
- `tests/test_recovery_frontend.js`
- `tests/password_policy_fixture.js` (new)

The existing reset success fixture was updated to a policy-compliant password so the original security, race, failure and one-use assertions still reach the provider branch. Tests that previously accepted missing character classes now require rejection as explicitly requested. The rendered-form browser harness gained the browser focus method needed to exercise invalid submissions; its original initialization, CSRF and no-network checks remain.

Verification passed:

- **136 focused Python tests**: registration validation, shared policy, registration/OTP, password reset, recovery callback, email verification, forgot password, login, callback, PKCE foundation and normal-auth login.
- **7 registration frontend Node tests** covering consent behavior, all required character classes, valid submission, independent checklist states, Unicode length and confirmation correction.
- **3 existing verification/resend frontend Node tests**.
- **Recovery frontend assertion script**, including the full weak-password matrix and live checklist states.
- **Actual Flask-rendered reset-page JavaScript test**, using the serialized production policy, rejects all requested weak examples and displays all Met states for `Abcdef1!`, with CSRF unchanged and no submission/network APIs.
- **`git diff --check`: exit 0**. Existing CRLF notices and the pre-existing `.pytest_cache` permission warning are environmental messages.

Tests verify `abcdefgh`, `Abcdefgh`, `Abcdefg1`, `abcdefg1!`, `ABCDEFG1!` and short passwords are rejected by both flows. `Abcdef1!` is accepted by local policy, registration continues to the existing OTP page, and a valid reset consumes its grant exactly once. Mismatched confirmation blocks provider access. Every printable ASCII punctuation character is covered by the policy test.

All tests used isolated offline providers. No live account, email or password was created/changed. Supabase configuration, database/schema, migrations, Tourism data, recommendations, itinerary behavior, OTP/email verification/resend, login, and recovery architecture are unchanged. A hash comparison of 149 starting application/template/static/data/migration files found only the six intended existing implementation files changed; 143 match. Three implementation files were added. The substantial existing `dev` worktree was preserved; nothing was staged or committed. Full [git status --short --branch](git-status.txt) is saved alongside this report.

For live verification, try the requested weak examples on Register and on Reset Password reached through a real recovery flow; each must remain on its form with the appropriate local message. Confirm independent checklist updates, consent-only behavior, exact mismatch text, and successful strong-password registration/reset through their existing OTP/login flows.

ROSAGO STRONG PASSWORD POLICY: READY FOR LIVE VERIFICATION
