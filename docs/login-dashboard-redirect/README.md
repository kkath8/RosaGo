# Login default destination

Previous default after successful normal login: Profile, endpoint `user_index`, `/user`.

New default: the existing authenticated-capable Dashboard, endpoint `index`, `/`. Production code changes exactly one fallback expression in the successful login branch: `url_for('user_index')` becomes `url_for('index')`. Dashboard/Profile functionality, credentials, sessions and auth architecture are unchanged.

The existing single validated `add_place` slug still takes priority and constructs the fixed internal `trips_add_place` route. Slug syntax/length/duplicate checks and destination/ownership checks are unchanged. Malformed/external continuation values fall back to Dashboard. The application does not support generic `next` URLs; those remain ignored, including external URLs and unsupported internal destinations. Other protected pages retain their existing redirect to Login without a continuation hint, then use the new default after login. No new continuation mechanism was added.

Email verification still returns to its verified checkpoint with Continue to Login. It does not create a normal session or redirect directly to Dashboard. After login, the default is now Dashboard. Password-reset completion still returns to `/login?password_updated=1`, consumes its recovery grant and requires normal login; that login now defaults to Dashboard. Profile remains available through its existing navigation and `/user` route. Already-authenticated auth-form guards are outside this post-login change and retain their existing behavior.

Files changed:

- `app.py`: one production-line fallback change.
- `tests/test_login.py`: successful login expects `/`; existing session and Profile assertions retained.
- `tests/test_functional_completion.py`: malformed/duplicate continuation fallback expectations updated; the existing complete Add to Trip continuation test remains.
- `tests/test_login_dashboard_redirect.py` (new): normal login follows to an authenticated Dashboard, Profile access, other protected-page behavior, unsafe/unsupported next values, failed login, verified-email → Login → Dashboard and reset completion → Login → Dashboard.
- `docs/login-dashboard-redirect/`: this report and full Git status.

**130 focused tests passed** across login/Dashboard redirects, login, functional completion/continuation, email verification, password reset, normal-auth login, normal-auth Flask, callback, Dashboard and Profile. External authentication/storage were guarded offline doubles; no real accounts, emails or password/trip updates were performed. A hash comparison found only `app.py` changed among 152 starting implementation/static/data/migration files; the other 151 match. Supabase, CSRF, OTP, password policy, PKCE, database/migrations, Dashboard/Profile implementation, Tourism, recommendations, itinerary and weather remain unchanged.

`git diff --check` passed. Existing Git CRLF notices and the `.pytest_cache` permission warning are informational. The verified local workspace Flask server was reloaded to activate the change and `/login` returned 200 afterward. Its in-memory sessions require fresh login/recovery links after the development-server restart. No live credentials were used to claim a live successful login; the redirect flows above were verified through the real Flask/auth adapter code using isolated providers.

Nothing was staged or committed, and unrelated worktree changes were preserved on `dev`. Full [git status --short --branch](git-status.txt) is saved here.

ROSAGO LOGIN DASHBOARD REDIRECT: READY FOR LIVE VERIFICATION
