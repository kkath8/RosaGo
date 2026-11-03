# Weather and derived Alerts

Alerts remains authenticated and uses the existing page layout. It now shows
city weather, three forecast days, weather reminders, and dated own-trip
reminders. There are no new dependencies, environment variables, migrations,
alert tables, push notifications or database writes.

## Provider and scope

`WeatherService` calls `https://api.open-meteo.com/v1/forecast` from Flask using
the existing httpx dependency. It requests `timezone=Asia/Manila`, Celsius,
millimetres, km/h, the five current fields and four daily fields used by the UI.
No user ID, trip, device location or API key is sent. Templates render validated
immutable values; they do not fetch the provider or contain provider logic.

The fixed city point is **14.31222, 121.11139**, from Open-Meteo's geocoding
result for GeoNames **1687894**, Santa Rosa, Province of Laguna, Philippines
(verified during this implementation, October 22, 2026). It is not a destination
entrance, is never written into place records, and does not imply weather at
each destination. The provider may return a nearby model grid cell.

Current fields: temperature, optional apparent temperature, modelled
precipitation, WMO weather code and wind speed. Daily fields: date, WMO code,
minimum/maximum temperature and maximum precipitation probability. Forecasts
are explicitly labelled. Current conditions are model estimates, not local
sensor observations. Weather code labels follow the provider's WMO table;
unknown integer codes display “Condition unavailable”.

The public forecast endpoint needs no key for this educational/noncommercial
use. Review Open-Meteo's current terms before commercial deployment. Source and
CC BY 4.0 attribution are included on the page.

## Validation, failure and caching

- HTTP timeout: eight seconds per operation. Redirects, environment proxies and
  automatic retries are disabled. Decompressed response size is capped at 128 KB.
- Required objects, array lengths, units, Asia/Manila UTC offset, date order,
  numeric types, finite values, sensible bounds and minimum/maximum order are
  checked. Booleans are not accepted as numbers. Missing apparent temperature
  is allowed; missing required current/forecast fields makes weather unavailable.
- The current model timestamp must be within 90 minutes of the Manila clock,
  allowing at most five minutes of future skew. Three contiguous forecast days
  must start today. Provider errors, malformed JSON and unavailable data never
  become zero-valued fallback weather or “all clear” messages.
- A locked, per-process cache holds only one city's validated public snapshot.
  Success expires after five minutes; failures are held for one minute to avoid
  repeated provider calls. Midnight/freshness checks prevent serving yesterday's
  forecast as today's. Expired successes are not served when a refresh fails.
- Weather and trip failures are shown separately. A provider failure leaves trip
  reminders usable; trip read failure leaves weather usable. Raw provider errors
  and private trip data are neither logged nor exposed in failure messages.

Time comparisons use an explicit UTC+08:00 Manila clock, independent of the host
timezone and without requiring an extra Windows timezone package.

## Deterministic reminder rules

| Type | Rule | Severity |
| --- | --- | --- |
| Weather | Positive modelled current precipitation; show amount, interval and timestamp. | caution |
| Weather | Otherwise a current drizzle/rain/shower/thunderstorm WMO code. | caution |
| Weather | Daily maximum precipitation probability at least 60%, for each returned day. | caution |
| Trip | Saved visit date is today in Manila. | info |
| Trip | Saved visit date is within the following seven days. | info |

Current precipitation and rainy-code reminders are mutually exclusive. There
are no government, disaster, traffic, closure or transport-disruption warnings.
No reminders are persisted, marked read, or delivered outside this page.

`list_upcoming_trips` uses the existing request-owned authenticated client and
RLS, with an explicit owner/date filter and validated rows. It orders by visit
date and ID, not creation date, so older saved plans are eligible. It reads at
most 51 rows to display 50 and disclose any additional matches. Past trips,
undated trips and dates beyond the window do not generate reminders. Users can
review other plans in My Trips. Private trip reminders are never weather-cached.

## Focused checks

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_weather_service.py tests/test_alerts_service.py tests/test_alerts_routes.py tests/test_final_ui.py -q --tb=short -p no:cacheprovider
git diff --check
git status --short
```

Tests use fixed dates, synthetic trip/weather data and mocked HTTP transports.
They do not depend on Open-Meteo availability and do not mutate Supabase.

For manual verification, restart the actual Flask process from this workspace,
sign in, and open Alerts. Check current model timestamps, attribution, forecast
days, trip dates and trip links. Confirm the no-trips state and independently
unavailable-weather/trip states. Outbound HTTPS to `api.open-meteo.com` is needed;
neither destination coordinates nor device location permission is required.

References:

- [Open-Meteo forecast variables, WMO codes and timezone behavior](https://open-meteo.com/en/docs)
- [Open-Meteo geocoding API](https://open-meteo.com/en/docs/geocoding-api)
- [City point lookup](https://geocoding-api.open-meteo.com/v1/search?name=Santa%20Rosa&count=20&countryCode=PH)
- [Open-Meteo terms](https://open-meteo.com/en/terms)
