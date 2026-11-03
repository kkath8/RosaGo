# Checkpoint 4: request-driven pre-trip weather review

## What exists and what this checkpoint adds

WeatherService already retrieves and validates a three-day Santa Rosa city forecast
from Open-Meteo. It has one shared public cache: successful results for 300 seconds,
failed requests for 60 seconds, no stale fallback, eight-second HTTP operation
timeouts, no redirects/environment proxies, and a 128 KB response cap. Existing
Alerts are deterministic, derived on page load, and not stored. Settings are signed
browser-session display preferences, not account-persisted notification settings.

Generated Planner Previews remain temporary `preview_ready` drafts. They are not
saved into My Trips. My Trips separately stores manually created dated destination
lists. There is no implemented start-trip/finalize action, background worker,
scheduler, push, email or SMS notification mechanism.

This checkpoint adds deterministic forecast review on the existing Preview renderer
and associates forecast concerns with future dated saved trips on Alerts. There
are no new routes, writes, proposal tokens, persistent alerts or migrations.

## Exact lifecycle and scope

Preview weather review runs after authentication, owned draft read, lifecycle,
expiry, contract and current selected-place fingerprint validation. It runs on GET
and when existing Explain/Adjust actions render a valid Preview. It checks only
dates with selected stops, before the first requested daily start time, in
Asia/Manila. Once that requested start passes, the UI says the pre-trip check is
inactive. This timestamp cutoff is not a claim that RosaGo tracked an actual start.
Dates after that cutoff are not treated as an in-progress-trip monitoring feature.

On Alerts, the existing bounded owner-filtered upcoming-trip read is reused: at
most 50 displayed trips in the existing seven-day reminder window. Saved trips
have a visit date but no start time or started flag. Weather review therefore
includes only dates strictly after today; existing same-day trip reminders remain.
An unavailable trip read does not become a claim of zero trips.

Checks happen when the relevant RosaGo page/request loads, subject to the shared
weather cache. No forecast baseline is persisted: this detects concerns in the
latest available forecast, not a measured change since an earlier observation.
Temporary drafts are not listed or persisted into Alerts; their advisories live
on the Preview page. Alerts links to existing saved-trip details with Review
Itinerary. The Preview review link scrolls to its existing destination cards.

The session's Weather and trip reminders option enables both on Alerts. Trip-only
hides weather and avoids weather-provider calls on both Alerts and Preview.
Weather-only keeps Preview weather enabled and keeps the existing Alerts behavior
of not reading saved trips. Forecast-to-trip reviews on Alerts need both display
options enabled; generic city weather remains visible with weather-only.

## Data and policy

Use the existing city grid location (14.31222, 121.11139), provider timezone,
daily `weather_code`, daily `precipitation_probability_max`, and model/fetch
timestamps. Destination coordinates are not needed: a city-level forecast is
explicitly disclosed. A destination with missing coordinates is still displayed
and no coordinate/weather-suitability inference is made. Current precipitation
does not substitute for a future date's daily forecast.

The centralized review rules are conservative product triggers, not scientific
danger thresholds or official warnings:

- Stronger concern: daily codes 65, 67, 82, 95, 96, 97 or 99 (heavy/freezing rain,
  violent showers, thunderstorms/hail). Show "Severe weather may affect the
  itinerary", even when the reported precipitation probability is low.
- Ordinary concern: existing rain/drizzle/shower codes, or maximum precipitation
  probability at least 60%, reusing Alerts' existing threshold. Show "Rain may
  affect the itinerary". Both exact condition/code and probability are displayed.
- Otherwise no concern is generated. Quiet wording is limited to the checked
  dates and does not promise safe conditions.
- Dates outside today through today+2 are explicitly outside RosaGo's configured
  range, even though Open-Meteo offers other forecast horizons. Missing dates,
  unavailable provider data and unknown codes without a probability trigger are
  unavailable, never converted to a clear-weather conclusion. Partial coverage
  reports both concerns and uncovered dates.
- Defense in depth rejects cached snapshots whose first day is not today, fetch
  time is older than five minutes, or model time is older than 90 minutes, with
  the existing five-minute future clock tolerance.

Provider field/code reference: [Open-Meteo Forecast API documentation](https://open-meteo.com/en/docs).
Daily codes describe the day's most severe condition, not exact visit-hour weather.
Code 97 is now labeled Heavy thunderstorm in the existing condition map and is
recognized by the existing rain-code set. No new weather fields are requested.

## Metadata gate and approval

The Place model and current catalog have category, description, address and optional
coordinates, but **no verified indoor/outdoor, covered/uncovered or weather-sensitive
metadata**. Category, names, descriptions, quiz environment preferences and Gemini
are not substitutes. No metadata values were added or guessed for catalog places.

Weather-aware destination replacement is therefore blocked pending verified
destination weather-suitability metadata. There is no suggested itinerary, accept
endpoint, reject operation or comparison pretending to be a replacement feature.
Reviewing weather or keeping the current plan performs no mutations. Existing
Checkpoint 3 manual conversational changes remain explicit and revision-checked;
unsupported indoor/outdoor requests still receive an honest limitation message.

Weather review does not invoke Gemini, rankers, selectors or draft mutation RPCs.
It does not clear a Checkpoint 2 explanation during the same response. A later
explicit conversational update continues clearing transient explanations, and
Explain with AI still maps to the latest validated selection. Existing CSRF,
Origin, revision and owner protections on those mutations are unchanged. No stale
weather proposal can overwrite a revision because no weather proposal exists.

Provider errors leave the itinerary usable. The existing WeatherService sanitizes
provider diagnostics; no account identity, tokens, names, session data or draft IDs
are sent to Open-Meteo. Weather is not sent to Gemini by this workflow. Text uses
Jinja escaping and existing private/no-store responses. No JavaScript is needed.

## Manual checks

Use future dates within today/tomorrow/the next day where possible. Forecast values
are real provider results; do not edit the catalog to force conditions. Synthetic
rain/thunderstorm/timeout cases are covered offline by MockTransport tests.

1. Generate a Preview starting tomorrow. Verify the Pre-trip weather review shows
   date-correlated concerns or a quiet result, provider attribution, city scope and
   the metadata limitation. Rain concerns show Review Itinerary; it scrolls to
   the same destination list. Selection/order/revision must not change on refresh.
2. Select a start at least three days ahead. Verify the explicit out-of-range
   message, usable destination cards and no clear-weather assertion. For a
   multi-day plan spanning the range, verify covered and uncovered dates coexist.
3. Open a Preview whose requested first start time has passed. Verify the inactive
   pre-trip message rather than a claim of actual trip-start tracking.
4. On Alerts, review a saved trip dated tomorrow. Its weather review identifies
   the trip/date and links to its existing detail page. Today's saved trip still
   gets its normal reminder but is not represented as definitely pre-trip.
5. Set Trip reminders only in Settings: both pages hide weather and make no
   weather request. Set Weather only: Preview weather returns; Alerts shows city
   weather without reading saved trips. Restore Weather and trip reminders.
6. Simulate unavailable Open-Meteo in a local provider stub: verify unavailable
   text without hidden cards, fabricated values, private diagnostics or writes.
7. Explain with AI, review weather, submit a supported count/category adjustment,
   then Explain with AI again. Verify normal updates, new revision and correct
   per-place mapping. An indoor/outdoor request must still be unsupported.
8. Keep an older tab open while adjusting in another. A stale conversational
   submission must be rejected. A weather review alone must never write anything.
   Verify a foreign/expired draft is rejected before any weather retrieval.
9. Disable JavaScript and repeat the review links and normal Preview forms.

No migration was created or applied in Checkpoint 4. The user subsequently
confirmed during Checkpoint 4B that 0010 was manually applied successfully. Do not
rerun it. This checkpoint did not change or apply it.
