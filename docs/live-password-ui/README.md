# Live password-policy UI fix

Root cause was confirmed against the actual running app at `http://127.0.0.1:5000/register`, before restarting it. A fresh HTTP request returned the obsolete `Use at least 8 characters.` helper, no checklist, and no shared policy script, despite the current template containing the shared partial. The live `auth.js` and `password-policy.js` static files matched their current workspace contents. The response already had `Cache-Control: no-store`, so this was not merely browser-cached HTML. The verified workspace Flask process started before the template changes and was serving cached old template/code. That paired old HTML without the shared policy script with a newer controller that depends on it, preventing normal JavaScript initialization. CSS was not the cause of the missing markup.

The verified RosaGo dev server was restarted to load the current code/templates. Only the identified workspace Flask launcher and its child on port 5000 were stopped. The replacement server is running on the same address. Its in-memory auth/OTP/recovery sessions were renewed by the restart; use a fresh login/recovery link where needed. No debug server, authentication bypass or recovery endpoint was added.

The existing single shared checklist remains in use; no duplicate checklist or second password policy was introduced. After restart, live Register contains all five requirements and no obsolete helper. Content fingerprints were added to Register/Reset CSS and JavaScript URLs so changes to these auth assets produce new URLs. The helper reads the current asset contents and hashes them; it does not add a build system or alter caching for other pages. Server-side template/Python changes still require the normal application reload/deployment restart.

Confirmation previously remained gated by submission or an existing error. Both controllers now evaluate nonempty confirmation on every confirmation `input` and whenever the password changes. `Passwords do not match.` appears and clears immediately. Registration consent revalidates after interaction: checking clears the local error, and unchecking again restores it. The duplicate generic registration message remains absent. Both Show/Hide controls retain their original behavior and accessible state.

Browser verification used hidden Chrome at 1365×1200 and 390×844:

- **Register:** tested directly against the restarted app on port 5000, using its actual served HTML, CSS and separate JavaScript resources. The browser reports five visible initial Not met rows, `abc` marks only lowercase Met, and `Abcdef1!` marks all five Met.
- **Reset:** tested the actual production reset route/template rendered through the isolated existing recovery test fixture. A temporary GET-only local server served that HTML and the actual static files. This did not authorize recovery on the running app, forward POST requests, contact Supabase, or create a live grant. A real inbox/recovery-link check remains manual.
- Both pages passed confirmation mismatch/match/password-edit checks before submission and both Show/Hide controls. Registration passed consent check/uncheck checks without a generic duplicate message.
- Both page types produced no browser JavaScript exceptions and no phone-width page overflow. Screenshots were inspected. Browser/test profiles and the GET-only fixture server were removed/stopped after capture; the real RosaGo server remains running.

Evidence: [before/after live HTTP and asset hashes](live-http-evidence.json), [browser measurements/interactions](browser-results.json), [live Register desktop](register-initial-1365.png), [live Register phone](register-initial-390.png), [production Reset template desktop fixture](reset-initial-1365.png), [Reset phone fixture](reset-initial-390.png).

Files changed:

- `app.py`: adds the restricted content-fingerprint URL helper for the four auth asset filenames. No route validation/auth/provider logic changed.
- `templates/auth/register.html`, `templates/auth/reset_password.html`: reference current fingerprinted assets; existing shared policy partial retained.
- `static/js/auth.js`: immediate confirmation feedback and consent interaction validation.
- `static/js/reset-password.js`: immediate confirmation feedback.
- `tests/test_strong_password_policy.py`: verifies the actual rendered five-row initial contract, absence of obsolete helper, shared-script order, content versions and served assets.
- `tests/test_registration_frontend.js`: adds pre-submit confirmation, consent reinteraction and both visibility toggles.
- `tests/test_recovery_frontend.js`: adds pre-submit confirmation/password-change behavior while preserving rendered-page, CSRF and no-network assertions.
- `docs/live-password-ui/`: report, browser/HTTP evidence, screenshots and full Git status.

Verification passed:

- **137 focused Python tests** across registration validation, strong policy, registration, password reset, recovery callback, OTP/email verification, forgot password, login, callback, PKCE foundation and normal-auth login.
- **9 registration frontend Node tests**.
- **3 existing verification/resend frontend Node tests**.
- **Recovery frontend assertion script**, including actual Flask-rendered reset HTML and serialized shared rules.
- **Desktop/phone Chrome interactions on both page types**, as distinguished above.
- **`git diff --check`: exit 0**. Existing Git CRLF notices and the pre-existing `.pytest_cache` permission warning are informational.

The strong server policy remains unchanged: eight characters, ASCII uppercase/lowercase/digit/printable punctuation, and matching confirmation. Weak input remains rejected before provider access; valid strong registration and one-use reset behavior remain covered. The shared Python policy, shared policy JavaScript/markup, CSS, Supabase configuration, database/migrations, OTP, PKCE/grant/CSRF/provider architecture, login, Tourism, recommendations, itinerary, weather and other UI are unchanged. Starting hashes covered 152 implementation/static/data/migration files: only the five intended implementation files above changed; the other 147 match. No live accounts, emails or password updates were performed.

Work remains on the existing `dev` branch with its intentional unrelated changes preserved. Nothing was staged or committed. Full [git status --short --branch](git-status.txt) is saved here.

Reload the existing Register tab to fetch the current document. It should show all five rows before typing. For the final real Reset flow, request a fresh recovery link after the server restart, then check the same interactions without submitting until ready to change the password.

ROSAGO LIVE PASSWORD POLICY UI: READY FOR BROWSER VERIFICATION
