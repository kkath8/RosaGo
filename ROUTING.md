# Map, routes and transport

The existing Flask public PlacesService, Leaflet 1.9.4, OpenStreetMap tiles,
authenticated Transport endpoint and itinerary preferences are reused. No new
packages, database writes, migrations or style redesign are needed.

## Configuration

Default: OSRM at `https://router.project-osrm.org`, driving only. No key is
required. OSRM profiles depend on the server's preprocessed data: a different
profile name in a URL does not establish walking or cycling support. This app
does not send walking/cycling requests to the default driving endpoint.

Optional server environment variables (keep keys in the ignored `.env`):

| Variable | Meaning |
| --- | --- |
| `ROUTING_PROVIDER` | `osrm` or `ors`. Defaults to `ors` if `ORS_API_KEY` is present; otherwise `osrm`. |
| `ORS_API_KEY` | Required for `ors`; server-only Authorization header. Enables driving-car, foot-walking and cycling-regular profiles. |
| `OSRM_BASE_URL` | Optional HTTPS base URL for an operator-managed OSRM driving server. Defaults to the public demo URL. No embedded credentials, query string or fragment. |

Restart the actual Flask process after changing code or configuration. Verify
the working directory and `.venv`; an older process can keep using the earlier
parser that rejects NULL coordinates and the industrial category.

The OSRM demo is restricted to reasonable noncommercial use and offers no
uptime guarantee. Requests are limited to one per second per RosaGo process,
with no automatic retries. Use one serving process for a demonstration. Use a
managed/own server and a shared rate limiter before deploying multiple workers.
Do not load-test the public demo or send automatic route requests on page load.

## Coordinate prerequisites

Map reads every page of the published catalog. Only complete, valid coordinate
pairs become markers or routing choices. Both NULL values are supported; a
single NULL value remains a parser consistency error. Coordinates stored in the
catalog must be verified by the operator; the schema has no separate verification
flag. This feature neither geocodes nor invents missing coordinates.

The 28 imported Santa Rosa records currently have NULL pairs. They remain
available in Explore and trips, but cannot produce destination routes yet.
Separately verify the exact visitor entrance of each site and update both
coordinates through an authorized database workflow. Avoid using city centers
or guessed points. No SQL import needs to be rerun for this integration.

## Use and failure behavior

1. Open Map, or sign in and open Transport. Both share the same map and form.
2. Select a destination or choose **Route here** in its marker popup.
3. Enter starting latitude/longitude, choose **Select starting point on map**,
   or explicitly choose **Use my location**. Device location requires browser
   permission and localhost/HTTPS; denial has a manual-entry fallback.
4. Select an available mode and choose **Get route**.
5. The provider's GeoJSON road/path line, distance and estimated duration appear.
   These are not straight-line estimates, traffic forecasts or timed itineraries.

Changing inputs clears the previous route and aborts any obsolete browser
request. Tile failures preserve the destination list. Missing coordinates,
invalid inputs, unsupported modes, missing configuration, unavailable/archived
destinations, provider errors, timeouts and no-route results produce fixed
messages without exposing provider response bodies or credentials.

`POST /api/route` accepts only `destination_slug`, `start_latitude`,
`start_longitude`, and `mode` as JSON from the same Origin. The endpoint is
public like Map, does not access account credentials, and resolves the destination
using the ordinary published-only client/RLS. It does not accept a caller-supplied
destination coordinate or provider URL. Requests and responses are not cached;
location coordinates are in the POST body rather than RosaGo request URLs. Only
the two endpoints are sent to the routing provider. API keys never reach Jinja,
JavaScript or API results. Configure reverse-proxy scheme/host correctly so the
browser's Origin matches Flask's external origin; do not disable the Origin check.

Itinerary preference values remain unchanged. Private car maps to driving,
walking to walking, and bicycle to cycling only when the provider supports them.
The Transport link on the preferences page carries the currently saved form
value; unsaved radio changes must be saved first. Motorcycle, public transit,
ride-hailing and mixed travel remain itinerary preferences, with no equivalent
route profile. Public transit routing, booking, fares and schedules are unavailable.

## Focused verification

Run the Python map, routing, transport, parser and quiz tests and the standalone
Node map-routing tests. Provider HTTP calls in tests use mock transports. Test
coordinates and geometry are synthetic fixtures, never inserted in the database.

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_routing_service.py tests/test_routing_routes.py tests/test_map_routes.py tests/test_final_ui.py tests/test_places_service.py tests/test_itinerary_quiz_form.py tests/test_itinerary_quiz_routes.py -q --tb=short -p no:cacheprovider
node tests/map_routing.test.js
git diff --check
git status --short
```

Run the Node test file directly in restricted Windows environments; the
`node --test` child-process runner may be unavailable even when direct execution
works.

Before live verification: restart the correct Flask process, add independently
verified coordinate pairs to the actual destinations, confirm outbound HTTPS to
OSM tiles and the routing provider, and configure an ORS key if walking/cycling
are needed. Verify the real browser map, all enabled modes, manual/device start
selection, permission denial, no-route/network failures and mobile controls.
No live provider success or live destination route is claimed by offline tests.

References:

- [OSRM API](https://project-osrm.org/docs/v5.24.0/api/)
- [OSRM demo policy](https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server)
- [ORS directions requests](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/requests-and-return-types)
- [ORS error codes](https://giscience.github.io/openrouteservice/api-reference/error-codes)
