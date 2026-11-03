# Profile and Settings

Profile manages required first/last names through the existing authenticated own-profile service, plus browser travel defaults and avatar color. Registered Auth email is read-only. Names are trimmed, limited to 100 characters and checked for control/surrogate characters. Ownership, exact-field validation, CSRF and same-origin checks remain protected.

Travel preferences and avatar color use the existing user-scoped RosaGoPersonal browser storage. They never store names, email or credentials and do not sync across devices. New drafts receive defaults only when personalization is enabled; existing draft choices remain intact. Trip refinements no longer overwrite saved Profile defaults.

Settings uses the existing signed session key rosago_ui_preferences, with alerts_display (all/weather/trips/none), personalized (boolean) and location_enabled (boolean). Alerts skips disabled weather/trip reads; no delivery channel is implied. Disabled location prevents explicit geolocation requests. Browser permissions remain browser-controlled. Legacy settings remain supported, and logout clears session settings.

Appearance offers working Light and Dark buttons. The validated presentation value is saved in browser localStorage under rosago.theme.v1 and applied before styles load; it does not change account or Profile preferences. English, PHP and km remain informational. Translation, uploads, device lists, traffic, account deletion and contact/username editing have no pretend controls. Profile can remember Low/Mid-range/High budget intent on this device and show it in a fresh Planner flow. It never filters destinations or guarantees costs, since prices are unverified. Exact budget amounts remain per trip. Change Password uses the existing secure recovery-email entry and unchanged password policy.

No SQL, schema or migration changes were made. See the [live Profile correction report](docs/profile-live/REPORT.md) for current Profile behavior and actual authenticated browser evidence. The [earlier Profile/Settings report](docs/profile-settings/REPORT.md) records the initial isolated-fixture verification.
