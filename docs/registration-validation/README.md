# Registration validation polish

The existing application registration policy required at least eight characters and rejected passwords consisting entirely of whitespace. It did not require uppercase, lowercase, numbers or special characters. That policy is unchanged. The checklist displays only the actual requirements, rather than inventing character-class requirements that the backend does not enforce. Supabase configuration was not read or changed for this task.

Consent-only validation now shows exactly one `Please agree to the Terms and Privacy Policy.` message directly beneath the consent row. It uses the existing dark error color, extra spacing and weight, `aria-describedby`, `aria-invalid`, and a polite live region. Checking consent clears its error. Other invalid fields retain their specific messages, and generic duplicate validation summaries are suppressed. Provider/network errors still appear in the existing form-status region.

The password checklist is visible before submission and updates on input and page restoration. Circles/checkmarks and explicit Not met/Met text communicate state without depending on color. Frontend length uses Unicode code points to agree with Python's character count. Confirmation mismatch reads `Passwords do not match.` and is revalidated when either password is corrected. Password values remain absent from server-rendered form values.

Backend changes are limited to returning the existing validation failures by field instead of concatenating them into a form-level message. All original registration validity checks still run before Supabase sign-up. The sign-up request, accepted metadata, pending verification session, OTP redirect, resend behavior, required indicators, provider-error sanitization and auth architecture are unchanged. No Supabase/database/network calls were made by this task; verification used guarded offline fixtures.

Implementation files changed:

- `app.py`: registration field-error presentation; password/consent validation rules and sign-up behavior retained.
- `templates/auth/register.html`: associated inline server errors and the actual-policy checklist.
- `static/js/auth.js`: local checklist, duplicate-message removal, consent correction and confirmation feedback.
- `static/css/auth.css`: registration-scoped consent/checklist rules only.
- `tests/test_registration_validation.py` (new): six server/markup/OTP-continuation tests.
- `tests/test_registration_frontend.js` (new): seven interaction tests against the real controller.

Verification passed:

- 112 focused Python tests across `test_registration_validation`, `test_registration`, `test_email_verification`, `test_login`, `test_password_reset`, `test_forgot_password`, `test_callback`, `test_recovery_callback`, and `test_functional_completion`.
- Seven registration frontend Node tests.
- Three existing verification/resend frontend Node tests.
- Existing recovery frontend assertion script.
- `git diff --check`: exit 0. Existing CRLF notices are informational.

Tests cover consent-only duplication, consent correction, multiple field errors, short/blank/short-Unicode passwords, acceptance without optional character classes, live checklist feedback, confirmation mismatch/correction, and valid registration continuing to the existing OTP page. No real accounts or emails were created.

A starting hash comparison covered 137 application/data/template/JS/CSS files. Only `app.py`, the registration template, registration JavaScript and the registration-scoped auth CSS additions changed; the other 133 files match. OTP/email-verification, login, recovery/PKCE, legal content, database/migrations, recommendation logic, Tourism data, configuration and other page templates remain unchanged.

Work remains on `dev`; nothing was staged or committed and unrelated changes were preserved. The full requested [git status --short --branch](git-status.txt) is saved beside this report. Git reports the pre-existing `.pytest_cache` permission warning.

Manual check: submit otherwise-valid registration details with consent unchecked; confirm a single nearby consent error, then check consent and confirm it disappears. Type a short password and then an eight-character nonblank password; observe checklist state and matching confirmation validation. A valid submission should proceed to the existing verification flow.

ROSAGO REGISTRATION VALIDATION: READY FOR LIVE VERIFICATION
