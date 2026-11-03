# Signup email OTP setup

Keep Supabase **Confirm Email enabled**. In the project's Authentication email
templates, edit **Confirm signup** and paste `docs/supabase-confirm-signup.html`
as the email body. This is a Supabase Go template, not a Flask/Jinja template.
Use a subject such as `Verify your RosaGo email`. Save the template. Do not
change the Reset Password / recovery template or PKCE redirect configuration.

The app calls `sign_up` for registration, `verify_otp` with `type: email` for
confirmation, and `resend` with `type: signup`. No custom code generator exists.
Supabase controls token length/expiry, delivery, account creation and rate limits.
The app accepts numeric codes of 6–10 digits to accommodate provider settings.
No normal RosaGo login session is established by verification; the user signs
in with their password afterwards. Any transient SDK OTP session is discarded.

Registration redirects to `/verify-email`. A signed cookie contains only an
opaque pending-flow handle. Pending email, CSRF and resend/attempt deadlines
are held in a bounded process-local store, for 30 minutes. No code, password,
access token or refresh token is stored there. Resend has an atomic 60-second
cooldown shared across pending flows for the same email within this process;
verification attempts have a five-second minimum interval. A provider 429 applies
a further 60-second server cooldown to both verify and resend. Provider limits remain
authoritative. Countdown is about resend eligibility, not token expiry.

As with existing process-local auth/recovery state, deploy with one process for
the current capstone setup. Shared atomic state is needed for multiple workers.
Restarting Flask clears pending flows. Account/profile/trip data is unaffected.

External setup is required: local app files cannot update the hosted Supabase
email template. The old link callback is retained without trusting URL tokens
or asserting successful verification. It does not establish a login session.

Manual verification after applying the template: register with an email you
control; receive the numeric code; confirm wrong/expired codes fail; verify with
the delivered code; see the form-free success state; continue to password login.
Check resend cooldown and actual email delivery without repeatedly sending mail.
Automated tests mock provider/email calls and do not create real accounts.

References:
- https://supabase.com/docs/guides/auth/auth-email-templates
- https://supabase.com/docs/reference/python/auth-verifyotp
- https://supabase.com/docs/reference/python/auth-resend

Terms/Privacy describe this academic implementation. Their contact text refers
to the project team's capstone demonstration/submission channel until the team
supplies a public contact. Consent is required server-side at registration;
there is no new persistent consent audit table or legal certification claim.
