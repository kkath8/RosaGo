"""Server-only road/path routing. Never fabricates geometry or travel estimates."""
import math
import re
import threading
import time
from urllib.parse import urlsplit

import httpx

from transport_modes import ORS_PROFILES

DEFAULT_OSRM_URL = 'https://router.project-osrm.org'
MAX_RESPONSE_BYTES = 2_000_000


class RoutingError(Exception):
    def __init__(self, code, message, status):
        self.code, self.status = code, status
        super().__init__(message)


def coordinate(value, maximum):
    if (type(value) not in (int, float) or not -maximum <= value <= maximum
            or not math.isfinite(value)):
        raise RoutingError('invalid_coordinates', 'Provide valid latitude and longitude values.', 400)
    return float(value)


def validate_request(data, supported_modes):
    fields = {'destination_slug', 'start_latitude', 'start_longitude', 'mode'}
    if type(data) is not dict or set(data) != fields:
        raise RoutingError('invalid_request', 'Provide a destination, starting point and transport mode.', 400)
    slug = data['destination_slug']
    if (type(slug) is not str or not 1 <= len(slug) <= 120
            or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug)):
        raise RoutingError('invalid_destination', 'Choose a valid published destination.', 400)
    mode = data['mode']
    if type(mode) is not str or mode not in supported_modes:
        raise RoutingError('unsupported_mode', 'This transportation mode is unavailable for routing.', 400)
    return (slug, coordinate(data['start_latitude'], 90),
            coordinate(data['start_longitude'], 180), mode)


def _https_base(value):
    try:
        parsed = urlsplit(value)
        parsed.port  # Validate configured ports before constructing any request.
        return bool(value == value.strip() and parsed.scheme == 'https' and parsed.hostname
                    and not parsed.username and not parsed.password and not parsed.query
                    and not parsed.fragment and not any(c.isspace() for c in value))
    except (TypeError, ValueError):
        return False


def _unavailable():
    return RoutingError('provider_unavailable', 'Routing is temporarily unavailable. Please try again later.', 503)


def _no_route():
    return RoutingError('no_route', 'No route was found for these points and this mode. Try a nearby starting point.', 422)


def _summary(value):
    if type(value) not in (int, float) or not 0 <= value < 1e12 or not math.isfinite(value):
        raise _unavailable()
    return float(value)


def _geometry(value):
    if (type(value) is not dict or value.get('type') != 'LineString'
            or type(value.get('coordinates')) is not list
            or not 2 <= len(value['coordinates']) <= 100_000):
        raise _unavailable()
    points = []
    for pair in value['coordinates']:
        if type(pair) is not list or len(pair) != 2:
            raise _unavailable()
        try:
            points.append([coordinate(pair[0], 180), coordinate(pair[1], 90)])
        except RoutingError:
            raise _unavailable() from None
    return {'type': 'LineString', 'coordinates': points}


class RoutingService:
    def __init__(self, provider='osrm', *, ors_key=None, osrm_url=DEFAULT_OSRM_URL,
                 http_factory=httpx.Client, clock=time.monotonic):
        self._provider = provider
        self._key = ors_key
        self._osrm_url = osrm_url.rstrip('/') if type(osrm_url) is str else ''
        self._http_factory, self._clock = http_factory, clock
        self._lock = threading.Lock()
        self._last_request = None
        key_valid = (type(ors_key) is str and 1 <= len(ors_key) <= 4096
                     and not any(c.isspace() for c in ors_key))
        self.configured = ((provider == 'osrm' and _https_base(self._osrm_url))
                           or (provider == 'ors' and key_valid))

    def __repr__(self):
        return '<RoutingService redacted>'

    @classmethod
    def from_environment(cls, environment):
        key = environment.get('ORS_API_KEY')
        provider = environment.get('ROUTING_PROVIDER', 'ors' if key else 'osrm')
        return cls(provider, ors_key=key,
                   osrm_url=environment.get('OSRM_BASE_URL', DEFAULT_OSRM_URL))

    @property
    def modes(self):
        if not self.configured:
            return ()
        return tuple(ORS_PROFILES) if self._provider == 'ors' else ('driving',)

    @property
    def label(self):
        return {'osrm': 'OSRM', 'ors': 'OpenRouteService'}.get(self._provider, 'Unavailable')

    def route(self, *, start_latitude, start_longitude, end_latitude, end_longitude, mode):
        if not self.configured:
            raise _unavailable()
        if type(mode) is not str or mode not in self.modes:
            raise RoutingError('unsupported_mode', 'This transportation mode is unavailable for routing.', 400)
        start = [coordinate(start_longitude, 180), coordinate(start_latitude, 90)]
        end = [coordinate(end_longitude, 180), coordinate(end_latitude, 90)]
        # At most one outgoing request per second per application process, including
        # the public OSRM demonstration server. No automatic retries or fallbacks.
        with self._lock:
            now = self._clock()
            if self._last_request is not None and now - self._last_request < 1:
                raise RoutingError('rate_limited', 'Please wait a moment before requesting another route.', 429)
            self._last_request = now
        failure = None
        try:
            with self._http_factory(timeout=12, follow_redirects=False, trust_env=False) as client:
                if self._provider == 'ors':
                    url = 'https://api.heigit.org/openrouteservice/v2/directions/' + ORS_PROFILES[mode] + '/geojson'
                    response = client.post(url, headers={'Authorization': self._key},
                        json={'coordinates': [start, end], 'instructions': False})
                else:
                    locations = ';'.join(','.join(str(v) for v in point) for point in (start, end))
                    response = client.get(self._osrm_url + '/route/v1/driving/' + locations,
                        params={'overview': 'full', 'geometries': 'geojson', 'steps': 'false',
                                'alternatives': 'false', 'radiuses': '100;100'},
                        headers={'User-Agent': 'RosaGo/1.0 (interactive route planner)'})
                if len(response.content) > MAX_RESPONSE_BYTES:
                    raise _unavailable()
                data = response.json()
                if type(data) is not dict:
                    raise _unavailable()
                if self._provider == 'osrm':
                    if data.get('code') in ('NoRoute', 'NoSegment'):
                        raise _no_route()
                    if response.status_code != 200 or data.get('code') != 'Ok':
                        raise _unavailable()
                    routes = data.get('routes')
                    if type(routes) is not list or not routes:
                        raise _no_route()
                    route = routes[0]
                    geometry, summary = route['geometry'], route
                else:
                    error = data.get('error')
                    if type(error) is dict and error.get('code') in (2009, 2010):
                        raise _no_route()
                    if response.status_code != 200:
                        raise _unavailable()
                    features = data.get('features')
                    if type(features) is not list or not features:
                        raise _no_route()
                    geometry = features[0]['geometry']
                    summary = features[0]['properties']['summary']
                return dict(geometry=_geometry(geometry), distance_m=_summary(summary['distance']),
                            duration_s=_summary(summary['duration']), mode=mode,
                            provider=self.label, estimated=True)
        except httpx.TimeoutException:
            failure = RoutingError('provider_timeout', 'The routing provider timed out. Please try again.', 504)
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, IndexError, TypeError):
            failure = _unavailable()
        # Never pass provider exceptions, URLs, headers or response bodies to Flask.
        raise failure from None
